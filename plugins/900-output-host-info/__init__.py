global logging
import logging

from dominate.tags import *
from dominate.util import raw

import vars
from Plugin import Plugin

class OutputHostInfo (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Building host output')

        with div() as d:
            p(self._config['header'])

            with table():
                with tr():
                    for key in vars.hosts_keys.keys():
                        th(key)

                for host in vars.hosts:
                    with tr():
                        for key in vars.hosts_keys.keys():
                            lookup_key = vars.hosts_keys[key]
                            td(vars.hosts[host][lookup_key])
        
        self.addOutput(
            output=d,
            title=self._config['title'],
            seq=self._config['seq_number'],
            keyname="output-host-info"
        )

def getPlugin():
    return OutputHostInfo()