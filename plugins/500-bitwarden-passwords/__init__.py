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
    4: 'Identity'
}

class BitwardenPasswords (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Starting Bitwarden queries')

        self._logger.debug('Setting apikey environment variables')
        os.environ["BW_CLIENTID"] = self._config['client_id']
        os.environ["BW_CLIENTSECRET"] = self._config['client_secret']

        self._logger.debug('Setting BW server from config')
        bwkr.bw('config', 'server', '{0}'.format(self._config['server_url']))

        status = json.loads(bwkr.bw('status'))
        
        if status['status'] == 'locked':
            self._logger.info('Logged in already; skipping...')
        else:
            self._logger.info('Logging in with apikey')
            bwkr.bw('login', '--apikey')

        self._logger.debug('Getting BW session')
        session = bwkr.get_session(os.environ)

        self._logger.info('Syncing BW vault')
        bwkr.bw("sync", session=session)

        self._logger.info('Getting BW folders')
        folders = json.loads(bwkr.bw('list', 'folders', session=session))

        self._logger.info('Runnig BW query')
        results = json.loads(bwkr.bw("list", "items", session=session))

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
                    'type': ITEM_TYPES[item['type']],
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
            bwkr.bw('logout')

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