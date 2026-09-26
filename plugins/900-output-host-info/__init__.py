global logging
import logging
import ipaddress

from dominate.tags import *
from dominate.util import raw

import vars
from Plugin import Plugin

# Columns shown even when no source filled them, with the value shown for
# a blank cell
ALWAYS_SHOWN = {'type': 'Unknown'}

class OutputHostInfo (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Building host output')

        # Only the columns some source filled in (Type always shows, with
        # "Unknown" where no source knows it), hosts in IP order
        columns = [(title, key) for title, key in vars.hosts_keys.items()
                   if key in ALWAYS_SHOWN
                   or any(h.get(key) for h in vars.hosts.values())]
        hosts = sorted(vars.hosts.values(),
                       key=lambda h: ipaddress.ip_address(h['ipaddress']))

        with div() as d:
            p(self._config['header'])

            # thead: the header row repeats on every printed page
            with table():
                with thead(), tr():
                    for title, key in columns:
                        th(title)

                with tbody():
                    for host in hosts:
                        with tr():
                            for title, key in columns:
                                value = host.get(key) or \
                                    ALWAYS_SHOWN.get(key, '')
                                if isinstance(value, list):
                                    value = ', '.join(value)
                                td(value)
        
        self.addOutput(
            output=d,
            title=self._config['title'],
            seq=self._config['seq_number'],
            keyname="output-host-info"
        )

def getPlugin():
    return OutputHostInfo()