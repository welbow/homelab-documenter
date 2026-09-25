global logging
import logging
import os
import os.path
import bitwarden_keyring as bwkr
import json

import vars
from Plugin import Plugin

ITEM_TYPES = {
    1: 'Login',
    2: 'Secure Note',
    3: 'Card',
    4: 'Identity',
    5: 'SSH Key'
}

class BitwardenPasswords (Plugin):
    def __init__(self):
        super().__init__()

    def _bw(self, *args, **kwargs):
        # A failing bw call raises ValueError chained to a
        # CalledProcessError whose command line holds `--session <token>`;
        # drop that chain so a traceback can't print the session token.
        try:
            return bwkr.bw(*args, **kwargs)
        except ValueError as exc:
            raise RuntimeError('bw {0} failed: {1}'.format(
                args[0], exc)) from None
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Starting Bitwarden queries')

        # The API key comes only from the environment (the gitignored .env,
        # passed through by docker-compose.yml) - never from config.json.
        # `bw login --apikey` reads BW_CLIENTID / BW_CLIENTSECRET itself.
        # To regenerate: see .env.example.
        if 'client_id' in self._config or 'client_secret' in self._config:
            self._logger.warning('client_id/client_secret in config.json are '
                                 'ignored; remove them and use .env instead')

        missing = [v for v in ('BW_CLIENTID', 'BW_CLIENTSECRET')
                   if not os.environ.get(v)]
        if missing:
            raise RuntimeError('{0} not set - copy .env.example to .env and '
                               'fill in your Bitwarden API key'.format(
                                   ', '.join(missing)))

        self._logger.debug('Setting BW server from config')
        self._bw('config', 'server', '{0}'.format(self._config['server_url']))

        status = json.loads(self._bw('status'))
        
        if status['status'] == 'locked':
            self._logger.info('Logged in already; skipping...')
        else:
            self._logger.info('Logging in with apikey')
            self._bw('login', '--apikey')

        self._logger.debug('Getting BW session')
        session = bwkr.get_session(os.environ)

        self._logger.info('Syncing BW vault')
        self._bw("sync", session=session)

        self._logger.info('Getting BW folders')
        folders = json.loads(self._bw('list', 'folders', session=session))

        self._logger.info('Runnig BW query')
        results = json.loads(self._bw("list", "items", session=session))

        for item in results:
            folder = next( f for f in folders if f["id"] == item['folderId'] )
            item['folder_name'] = folder['name']

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

        if self._config.get('logout', 1) == 1:
            self._logger.debug('Logging out')
            self._bw('logout')

            self._logger.debug('Clearing environment variables')
            os.environ["BW_CLIENTID"] = ''
            os.environ["BW_CLIENTSECRET"] = ''

            self._logger.info('Cleaning up cached vault data')
            vaultfile = os.path.expanduser('~/.config/Bitwarden CLI/data.json')
            if os.path.exists(vaultfile):
                os.remove(vaultfile)

        self._logger.info('Finished Bitwarden queries')

def getPlugin():
    return BitwardenPasswords()