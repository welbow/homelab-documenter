global logging
import logging
import os
import os.path
import json
import shutil
import subprocess
import sys

import credentials
import vars
from Plugin import Plugin

ITEM_TYPES = {
    1: 'Login',
    2: 'Secure Note',
    3: 'Card',
    4: 'Identity',
    5: 'SSH Key'
}

# Where the bw CLI keeps its login and cached (encrypted) vault
BW_DATA_DIR = os.path.expanduser('~/.config/Bitwarden CLI')

class BitwardenPasswords (Plugin):
    def __init__(self):
        super().__init__()
        self._session = None
        # BW_CLIENTID / BW_CLIENTSECRET for `bw login --apikey`, from the
        # encrypted credentials
        self._api_key = {}

    def _bw(self, *args, interactive=False):
        """Run the bw CLI and return its output. The session and API key
        are passed in bw's environment only, never on the command line, so
        they can't show up in the process list or an error message. With
        interactive, bw may prompt on the terminal (master password)."""
        env = dict(os.environ)
        env.update(self._api_key)
        if self._session:
            env['BW_SESSION'] = self._session
        result = subprocess.run(
            ['bw'] + list(args), env=env, text=True,
            stdout=subprocess.PIPE,
            stderr=None if interactive else subprocess.PIPE)
        if result.returncode != 0:
            error = (result.stderr or result.stdout or '').strip()
            raise RuntimeError('bw {0} failed: {1}'.format(
                args[0], error or 'exit code {0}'.format(result.returncode)))
        return result.stdout

    def _unlock_with(self, password):
        """Unlock with a known password. bw reads it from a file: a private
        one in the build dir (a tmpfs in the container), deleted straight
        away."""
        os.makedirs(vars.build_dir, exist_ok=True)
        path = os.path.join(vars.build_dir, '.bw-password')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(password)
            return self._bw('unlock', '--passwordfile', path, '--raw').strip()
        finally:
            os.remove(path)

    def _unlock(self):
        """Unlock the vault with the encrypted bw_master_password
        credential (#22), or else by asking on the terminal. The password
        never goes in the environment or on a command line."""
        password = credentials.get('bw_master_password')
        if password:
            self._logger.info('Unlocking vault with the encrypted '
                              'bw_master_password credential')
            return self._unlock_with(password)

        if not sys.stdin.isatty():
            raise RuntimeError(
                'The vault is locked, the bw_master_password credential is '
                'not set, and there is no terminal to ask for it. Store it '
                'with: docker compose run --rm secrets set bw_master_password')
        self._logger.info('Unlocking vault; enter your master password (or '
                          'store it: docker compose run --rm secrets set '
                          'bw_master_password)')
        return self._bw('unlock', '--raw', interactive=True).strip()

    def _login_and_unlock(self):
        """Get an unlocked session from whatever state bw is in. Returns
        True if an existing session (BW_SESSION) is being reused."""
        status = json.loads(self._bw('status'))

        # A session unlocked earlier in this dev shell: reuse it
        if os.environ.get('BW_SESSION') and status.get('status') == 'unlocked':
            self._logger.info('Reusing unlocked vault session (BW_SESSION)')
            self._session = os.environ['BW_SESSION']
            return True

        server = self._config['server_url']
        if status.get('status') != 'unauthenticated' and \
                status.get('serverUrl') not in (None, server):
            self._logger.info('Logged in to another server; logging out')
            self._bw('logout')
            status['status'] = 'unauthenticated'

        if status.get('status') == 'unauthenticated':
            self._logger.debug('Setting BW server from config')
            self._bw('config', 'server', server)
            self._logger.info('Logging in with apikey')
            self._bw('login', '--apikey')

        self._session = self._unlock()
        if not self._session:
            raise RuntimeError('bw unlock returned no session')
        return False

    def _clean_up(self):
        """Lock, log out and remove the CLI's data, whatever happened."""
        for args in (('lock',), ('logout',)):
            try:
                self._bw(*args)
            except (RuntimeError, OSError) as exc:
                self._logger.debug('Ignoring: {0}'.format(exc))
        self._session = None
        self._api_key = {}

        self._logger.info('Removing the Bitwarden CLI data')
        shutil.rmtree(BW_DATA_DIR, ignore_errors=True)

    def run(self):
        if not self.getConfig():
            return

        self._logger.info('Starting Bitwarden queries')

        # The API key comes only from the encrypted credentials (#22), never
        # config.json or .env. `bw login --apikey` reads BW_CLIENTID /
        # BW_CLIENTSECRET from its environment. To regenerate the key: see
        # .env.example.
        if 'client_id' in self._config or 'client_secret' in self._config:
            self._logger.warning('client_id/client_secret in config.json are '
                                 'ignored; remove them and store the key with '
                                 '`docker compose run --rm secrets set '
                                 'bw_clientid` / bw_clientsecret')
        if os.environ.get('BW_CLIENTID') or os.environ.get('BW_CLIENTSECRET'):
            self._logger.warning('BW_CLIENTID/BW_CLIENTSECRET in the '
                                 'environment are ignored; the encrypted '
                                 'credentials are used')
        if 'logout' in self._config:
            self._logger.warning('"logout" in config.json is ignored: runs '
                                 'always log out, except when reusing a '
                                 'BW_SESSION')

        self._api_key = {}
        missing = []
        for var in ('BW_CLIENTID', 'BW_CLIENTSECRET'):
            value = credentials.get(var.lower())
            if value:
                self._api_key[var] = value
            else:
                missing.append(var.lower())
        if missing:
            raise RuntimeError(
                'Bitwarden API key not stored ({0}). Store it with: {1} '
                '(see .env.example for where to find the key)'.format(
                    ', '.join(missing),
                    ' and '.join('docker compose run --rm secrets set ' + n
                                 for n in missing)))

        reusing = False
        try:
            reusing = self._login_and_unlock()
            self._query()
        finally:
            # A reused dev session stays open for the next run in that shell
            if not reusing:
                self._clean_up()

        self._logger.info('Finished Bitwarden queries')

    def _query(self):
        self._logger.info('Syncing BW vault')
        self._bw('sync')

        self._logger.info('Getting BW folders')
        folders = {f['id']: f['name']
                   for f in json.loads(self._bw('list', 'folders'))}

        self._logger.info('Running BW query')
        results = json.loads(self._bw('list', 'items'))

        for item in results:
            # Items without a (known) folder go under "No Folder"
            item['folder_name'] = folders.get(item.get('folderId')) \
                or 'No Folder'

        for query in self._config['queries']:
            creds = []

            for item in sorted(results, key=lambda d: d['folder_name']):
                if query.get('exclude_folders', None):
                    if type(query['exclude_folders']) is str:
                        if query['exclude_folders'] == item['folder_name']:
                            continue

                    if type(query['exclude_folders']) is list:
                        if item['folder_name'] in query['exclude_folders']:
                            continue

                if query.get('include_folders', None):
                    if type(query['include_folders']) is str:
                        if query['include_folders'] != item['folder_name']:
                            continue

                    if type(query['include_folders']) is list:
                        if item['folder_name'] not in query['include_folders']:
                            continue

                o = {
                    'folder': item['folder_name'],
                    # Don't crash on item types newer Bitwarden releases add
                    'type': ITEM_TYPES.get(item['type'],
                                           'Unknown ({0})'.format(item['type'])),
                    'name': item['name']
                }

                if item.get('login', None):
                    url = ''
                    uris = item['login'].get('uris',None)
                    if uris is not None:
                        url = ', '.join([k['uri'] for k in uris ])

                    o.update({
                        'url': url,
                        'username': item['login'].get('username','None'),
                        'password': item['login'].get('password','None'),
                        'mfa': item['login'].get('totp', None) is not None
                    })

                creds.append(o)

            key = '{1}-{0}'.format(query.get('title'),
                                    query.get('seq_number'))

            vars.creds[key] = {
                'title': query.get('title'),
                'seq': query.get('seq_number'),
                'header': query.get('header'),
                'items': creds
            }

def getPlugin():
    return BitwardenPasswords()
