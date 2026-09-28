global logging
import logging
import re

import vars
from Plugin import Plugin

# Long interface names as CDP/LLDP often report them, and the short forms
# switches show in their own lists, so "GigabitEthernet1/0/5" and "Gi1/0/5"
# are the same port
ABBREVIATIONS = (
    ('tengigabitethernet', 'te'), ('twentyfivegige', 'twe'),
    ('fortygigabitethernet', 'fo'), ('hundredgige', 'hu'),
    ('gigabitethernet', 'gi'), ('fastethernet', 'fa'),
    ('ethernet', 'eth'), ('port-channel', 'po'),
)


def short_name(name):
    """An interface name in a form both spellings share."""
    name = re.sub(r'\s+', '', (name or '').lower())
    for long, short in ABBREVIATIONS:
        if name.startswith(long):
            return short + name[len(long):]
    return name


class PortMap (Plugin):
    """Joins up what the discovery plugins found about devices and their
    interfaces (#19): links each interface to the interface it's connected
    to (from CDP/LLDP neighbours, both ways), and matches the MAC addresses
    a switch learned on each port with the hosts' MAC addresses, so a
    host's row says which switch port it's plugged into ("Connected to"),
    and a port knows which hosts are behind it.

    A MAC is placed on the port where it was learned with the fewest other
    MACs: the port it's actually plugged into, not the uplinks it was also
    seen on. With several devices on that port (an access point or an
    unmanaged switch behind it), each gets "(shared)". A port's description
    becomes a host's friendly Name when the host is alone on the port and
    nothing else named it (a host override still wins). Runs on every
    rebuild, after all discovery."""
    always_run = True

    def __init__(self):
        super().__init__()

    def run(self):
        # On unless config.json turns it off; it has nothing to do until a
        # plugin reports interfaces
        config = vars.config.get('plugins', {}).get('PortMap', {})
        if config.get('enabled', 1) != 1 or not vars.devices:
            return
        self._link_neighbours()
        self._place_hosts()

    def _find(self, device, name):
        record = vars.devices.get(device)
        if not record:
            return None
        interfaces = record['interfaces']
        if name in interfaces:
            return interfaces[name]
        wanted = short_name(name)
        for iface in interfaces.values():
            if short_name(iface['name']) == wanted:
                return iface
        return None

    def _link_neighbours(self):
        """A neighbour reported on one side is linked on the other side too,
        if that device is known."""
        for device, record in vars.devices.items():
            for iface in record['interfaces'].values():
                peer = iface.get('peer_device')
                if not peer:
                    continue
                other = self._find(peer, iface.get('peer_interface', ''))
                if other is not None and not other.get('peer_device'):
                    other['peer_device'] = device
                    other['peer_interface'] = iface['name']

    def _place_hosts(self):
        # MAC -> host IPs, and MAC -> the ports it was learned on
        by_mac = {}
        for ip, host in vars.hosts.items():
            if host.get('mac'):
                by_mac.setdefault(host['mac'].lower(), []).append(ip)
        learned = {}
        for device, record in vars.devices.items():
            for iface in record['interfaces'].values():
                iface['connected_hosts'] = []
                # A port facing another known device is an uplink, not
                # where hosts are plugged in
                if iface.get('peer_device') in vars.devices:
                    continue
                for mac in iface['macs']:
                    learned.setdefault(mac, []).append((device, iface))

        for mac, ports in learned.items():
            ips = by_mac.get(mac)
            if not ips:
                continue
            device, iface = min(ports, key=lambda p: len(p[1]['macs']))
            alone = len(iface['macs']) == 1
            where = '{0} {1}'.format(device, iface['name'])
            if not alone:
                where += ' (shared)'
            for ip in ips:
                host = vars.hosts[ip]
                if host.get('device') == device:
                    continue    # the switch's own address
                iface['connected_hosts'].append(ip)
                if not host.get('connected_to'):
                    host['connected_to'] = where
                if alone and iface.get('description') and not host.get('name'):
                    host['name'] = iface['description']


def getPlugin():
    return PortMap()
