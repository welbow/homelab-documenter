global logging
import logging
import ipaddress

import nmap

import vars
from Plugin import Plugin

# ICMP echo only. A plain -sn also sends TCP probes to ports 80/443, which
# Docker Desktop's network proxy answers for every address, so every
# address would look up; real pings pass through honestly. Without ARP
# (which can't leave the Docker VM) there are no MAC addresses. Hostnames
# come from reverse DNS via the system resolver; in Docker that needs the
# container pointed at the LAN's DNS servers (see the compose override
# example), since Docker's own resolver doesn't know the LAN's names.
SCAN_ARGUMENTS = '-sn -PE --disable-arp-ping'

class NmapPingScan (Plugin):
    def __init__(self):
        super().__init__()

    def run(self):
        if not self.getConfig():
            return

        self._logger.info('Starting nmap ping scans')

        for subnet in self._config['subnets']:
            self._logger.info('Scanning subnet {0}'.format(subnet))
            network = ipaddress.ip_network(subnet, strict=False)
            # Some devices answer pings to the network or broadcast address
            skip = set()
            if network.num_addresses > 2:
                skip = {str(network.network_address),
                        str(network.broadcast_address)}

            nm = nmap.PortScanner()
            nm.scan(hosts=subnet, arguments=SCAN_ARGUMENTS)

            for host in nm.all_hosts():
                if host in skip:
                    continue
                names = [h.get('name') for h in nm[host].get('hostnames', [])
                         if h.get('name')]
                self.addHost(host, source='nmap',
                             hostname=names[0] if names else '',
                             subnet=subnet)

        self._logger.info('Finished nmap ping scans')

def getPlugin():
    return NmapPingScan()
