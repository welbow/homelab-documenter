global logging
import logging
import nmap

import vars
from Plugin import Plugin

class NmapPingScan (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Starting nmap ping scans')

        for subnet in self._config['subnets']:
            self._logger.info('Scanning subnet {0}'.format(subnet))
            nm = nmap.PortScanner()
            nm.scan(hosts=subnet, arguments='-sn')

            for host in nm.all_hosts():
                vars.hosts[host] = { 
                    'hostname': nm[host]['hostnames'][0]['name'],
                    'ipaddress': host
                    }

        self._logger.info('Finished nmap ping scans')

def getPlugin():
    return NmapPingScan()