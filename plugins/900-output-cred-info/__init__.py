global logging
import logging

from dominate.tags import *
from dominate.util import raw

import vars
from Plugin import Plugin

class OutputCredInfo (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Building credential output')

        for query in vars.creds.keys():
            q = vars.creds[query]

            with div() as d:
                p(q['header'])

                with table():
                    with tr():
                        for key in vars.creds_keys.keys():
                            th(key)

                    for cred in q['items']:
                        with tr():
                            for key in vars.creds_keys.keys():
                                lookup_key = vars.creds_keys[key]
                                v = cred.get(lookup_key,'None')
                                if v is None:
                                    v = 'None'
                                td(v)
            
            self.addOutput(
                output=d,
                title=q['title'],
                seq=q['seq'],
                keyname="output-cred-info"
            )

def getPlugin():
    return OutputCredInfo()