global logging
import logging
import re

from dominate.tags import *

import vars
from Plugin import Plugin, device_key

# Long interface names as CDP/LLDP often report them, and the short forms
# switches show in their own lists, so "GigabitEthernet1/0/5" and "Gi1/0/5"
# are the same port
ABBREVIATIONS = (
    ('tengigabitethernet', 'te'), ('twentyfivegige', 'twe'),
    ('fortygigabitethernet', 'fo'), ('hundredgige', 'hu'),
    ('gigabitethernet', 'gi'), ('fastethernet', 'fa'),
    ('port-channel', 'po'), ('ethernet', 'eth'),
)


def short_name(name):
    """An interface name in a form both spellings share."""
    name = re.sub(r'\s+', '', (name or '').lower())
    for long, short in ABBREVIATIONS:
        if name.startswith(long):
            return short + name[len(long):]
    return name


def port_order(name):
    """Sort key: Gi1/0/2 before Gi1/0/10, port-channels last."""
    parts = re.split(r'(\d+)', name)
    return (name.lower().startswith(('po', 'port-channel')),
            [int(p) if p.isdigit() else p.lower() for p in parts])


class PortMap (Plugin):
    """Joins up what the discovery plugins found about switch ports and
    devices (#19), and adds the Switch ports section: which host or device
    interface is on each port.

    - Port-channels: a member port's neighbour counts for its channel, and
      the channel is listed with its members.
    - Uplinks (a port whose CDP/LLDP neighbour is a device we know: a
      switch, the firewall) show the neighbour; if it's a device interface
      we know (the firewall's igb1), the interface says which switch port
      it's connected to. Other neighbours (an IP phone, an access point)
      are shown, and what's behind them is still placed on the port.
    - Every other MAC a switch learned is placed on the port where it was
      learned with the fewest other MACs (the port it's plugged into, not
      the uplinks it was also seen on), and matched with the hosts' and the
      devices' interfaces' MAC addresses.
    - A host's row says where it's plugged in ("Connected to"), with
      "(shared)" if several devices are on that port (an access point or an
      unmanaged switch behind it). A host alone on a port gets the port's
      description as its Name, if nothing else named it.

    Runs on every rebuild, after all discovery. On by default."""
    always_run = True

    def __init__(self):
        super().__init__()

    def run(self):
        self._config = vars.config.get('plugins', {}).get('PortMap', {})
        if self._config.get('enabled', 1) != 1 or not vars.ports:
            return
        self._roll_up_channels()
        self._uplinks()
        self._place_macs()
        self._add_section()

    def _ports_of(self, switch):
        return {port: record for (sw, port), record in vars.ports.items()
                if sw == switch}

    def _find_port(self, switch, name):
        wanted = short_name(name)
        for (sw, port), record in vars.ports.items():
            if sw == switch and short_name(port) == wanted:
                return record
        return None

    def _find_interface(self, device, name):
        record = vars.devices.get(device)
        if not record:
            return None
        wanted = short_name(name)
        for iface in record['interfaces'].values():
            if short_name(iface['name']) == wanted:
                return iface
        return None

    def _roll_up_channels(self):
        """Members of a port-channel: listed under it, and their neighbour
        and learned MACs count for the channel."""
        for record in vars.ports.values():
            record['connected'] = []
            record['members'] = []
        for (switch, port), record in list(vars.ports.items()):
            channel = record.get('channel')
            if not channel:
                continue
            parent = self._find_port(switch, channel)
            if parent is None:
                parent = self._port(switch, channel)
                parent.update(connected=[], members=[])
            parent['members'].append(port)
            if record.get('neighbor_device') and \
                    not parent.get('neighbor_device'):
                parent['neighbor_device'] = record['neighbor_device']
                parent['neighbor_port'] = record.get('neighbor_port', '')
            for mac, vlan in record['macs'].items():
                parent['macs'].setdefault(mac, vlan)
        for record in vars.ports.values():
            record['members'].sort(key=port_order)

    def _is_member(self, record):
        return bool(record.get('channel'))

    def _resolve(self, record):
        """The device key of a port's neighbour. Neighbours don't always
        send their own hostname (a CBS350's CDP ID is its MAC; OPNsense
        says "OPNsense" over LLDP), so an unknown name is looked up by the
        neighbour's MAC address or IP address among the devices'
        interfaces and the hosts."""
        name = record['neighbor_device']
        key = device_key(name)
        if key in vars.devices:
            return key
        macs = [m for m in (record.get('neighbor_mac'),
                            self._as_mac(name)) if m]
        for mac in macs:
            for device, info in vars.devices.items():
                if any((i.get('mac') or '').lower() == mac
                       for i in info['interfaces'].values()):
                    return device
            for host in vars.hosts.values():
                if (host.get('mac') or '').lower() == mac and \
                        host.get('device'):
                    return host['device']
        host = vars.hosts.get(record.get('neighbor_address') or '')
        if host and host.get('device'):
            return host['device']
        return key

    @staticmethod
    def _as_mac(name):
        digits = re.sub(r'[^0-9a-f]', '', (name or '').lower())
        if len(digits) == 12 and len(digits) >= len(name) - 5:
            return ':'.join(digits[i:i + 2] for i in range(0, 12, 2))
        return ''

    def _uplinks(self):
        for record in vars.ports.values():
            if record.get('neighbor_device'):
                record['neighbor_device'] = self._resolve(record)
        for (switch, port), record in vars.ports.items():
            neighbor = record.get('neighbor_device')
            if not neighbor or self._is_member(record):
                continue
            where = '{0} {1}'.format(switch, port)
            other = self._find_port(neighbor, record.get('neighbor_port', ''))
            iface = self._find_interface(neighbor,
                                         record.get('neighbor_port', ''))
            if iface is not None and not iface.get('connected_to'):
                iface['connected_to'] = where
            label = '{0} {1}'.format(
                neighbor, record.get('neighbor_port', '')).strip()
            # A neighbour we know as a device (a switch, the firewall) makes
            # this an uplink; any other (an IP phone, an access point) is
            # just shown, and what's behind it is still placed on the port
            record['connected'].append(
                ('Uplink: ' if neighbor in vars.devices else 'Neighbour: ')
                + label)
            if other is not None and not other.get('neighbor_device'):
                other['neighbor_device'] = switch
                other['neighbor_port'] = port

    def _place_macs(self):
        hosts_by_mac = {}
        for ip, host in vars.hosts.items():
            if host.get('mac'):
                hosts_by_mac.setdefault(host['mac'].lower(), []).append(ip)
        ifaces_by_mac = {}
        for device, record in vars.devices.items():
            for iface in record['interfaces'].values():
                if iface.get('mac'):
                    ifaces_by_mac.setdefault(iface['mac'].lower(), []).append(
                        (device, iface))

        learned = {}
        for (switch, port), record in vars.ports.items():
            if self._is_member(record) or                     record.get('neighbor_device') in vars.devices:
                continue
            for mac in record['macs']:
                learned.setdefault(mac, []).append((switch, port, record))

        for mac, places in learned.items():
            ips = hosts_by_mac.get(mac, [])
            ifaces = ifaces_by_mac.get(mac, [])
            if not ips and not ifaces:
                continue
            switch, port, record = min(places,
                                       key=lambda p: len(p[2]['macs']))
            alone = len(record['macs']) == 1
            where = '{0} {1}'.format(switch, port)
            for device, iface in ifaces:
                if device == switch:
                    continue            # the switch's own interface
                record['connected'].append('{0} {1}'.format(device,
                                                            iface['name']))
                iface.setdefault('connected_to', where)
            for ip in ips:
                host = vars.hosts[ip]
                if host.get('device') == switch:
                    continue            # the switch's own address
                if ifaces and host.get('device') in [d for d, _ in ifaces]:
                    continue            # already listed as its interface
                if not host.get('connected_to'):
                    host['connected_to'] = where + ('' if alone
                                                    else ' (shared)')
                if alone and record.get('description') and \
                        not host.get('name'):
                    host['name'] = record['description']
                record['connected'].append(self._host_label(ip, host))

    def _host_label(self, ip, host):
        name = host.get('name') or host.get('hostname')
        return '{0} ({1})'.format(name, ip) if name else ip

    def _add_section(self):
        section = self._config.get('section', {})
        if section == 0:
            return
        if not isinstance(section, dict):
            section = {}
        switches = sorted({switch for switch, _ in vars.ports})
        with div() as d:
            if section.get('header'):
                p(section['header'])
            for switch in switches:
                h2(switch)
                self._switch_table(switch)
        self.addOutput(d, title=section.get('title', 'Switch ports'),
                       seq=section.get('seq_number', '970'),
                       keyname='switch-ports')

    def _switch_table(self, switch):
        ports = self._ports_of(switch)
        # Member ports are listed with their channel
        shown = sorted((name for name, r in ports.items()
                        if not self._is_member(r)), key=port_order)
        with table():
            with thead(), tr():
                for title in ('Port', 'Description', 'Status', 'Speed',
                              'VLAN', 'Mode', 'Connected to'):
                    th(title)
            with tbody():
                for name in shown:
                    record = ports[name]
                    label = name
                    if record['members']:
                        label += ' ({0})'.format(', '.join(record['members']))
                    with tr():
                        td(label)
                        td(record.get('description', ''))
                        td(record.get('status', ''))
                        td(record.get('speed', ''))
                        td(record.get('vlan', ''))
                        td(record.get('mode', ''))
                        td(', '.join(record['connected']))


def getPlugin():
    return PortMap()
