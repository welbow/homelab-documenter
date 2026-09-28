global logging
import logging
import ipaddress
import re

import snmp
import vars
from Plugin import Plugin, device_key

# MIB objects read, by name. Standard MIBs where Cisco supports them,
# Cisco's own where it doesn't (per-VLAN bridge tables, CDP, VTP, PAgP).
OID = {
    'sysName': '1.3.6.1.2.1.1.5.0',
    'sysDescr': '1.3.6.1.2.1.1.1.0',
    # IF-MIB
    'ifType': '1.3.6.1.2.1.2.2.1.3',
    'ifPhysAddress': '1.3.6.1.2.1.2.2.1.6',
    'ifAdminStatus': '1.3.6.1.2.1.2.2.1.7',
    'ifOperStatus': '1.3.6.1.2.1.2.2.1.8',
    'ifName': '1.3.6.1.2.1.31.1.1.1.1',
    'ifHighSpeed': '1.3.6.1.2.1.31.1.1.1.15',
    'ifAlias': '1.3.6.1.2.1.31.1.1.1.18',
    # IP-MIB (the switch's own addresses)
    'ipAdEntIfIndex': '1.3.6.1.2.1.4.20.1.2',
    'ipAdEntNetMask': '1.3.6.1.2.1.4.20.1.3',
    # BRIDGE-MIB and Q-BRIDGE-MIB (MAC address tables)
    'dot1dBasePortIfIndex': '1.3.6.1.2.1.17.1.4.1.2',
    'dot1dTpFdbPort': '1.3.6.1.2.1.17.4.3.1.2',
    'dot1dTpFdbStatus': '1.3.6.1.2.1.17.4.3.1.3',
    'dot1qTpFdbPort': '1.3.6.1.2.1.17.7.1.2.2.1.2',
    'dot1qTpFdbStatus': '1.3.6.1.2.1.17.7.1.2.2.1.3',
    'dot1qPvid': '1.3.6.1.2.1.17.7.1.4.5.1.1',
    # Port-channels: LACP (IEEE8023-LAG-MIB) and PAgP (CISCO-PAGP-MIB)
    'dot3adAggPortAttachedAggID': '1.2.840.10006.300.43.1.2.1.1.13',
    'pagpGroupIfIndex': '1.3.6.1.4.1.9.9.98.1.1.1.1.8',
    # VLANs: CISCO-VTP-MIB, CISCO-VLAN-MEMBERSHIP-MIB
    'vtpVlanState': '1.3.6.1.4.1.9.9.46.1.3.1.1.2',
    'vlanTrunkPortDynamicStatus': '1.3.6.1.4.1.9.9.46.1.6.1.1.14',
    'vmVlan': '1.3.6.1.4.1.9.9.68.1.2.2.1.2',
    # Neighbours: CISCO-CDP-MIB and LLDP-MIB
    'cdpCacheAddress': '1.3.6.1.4.1.9.9.23.1.2.1.1.4',
    'cdpCacheDeviceId': '1.3.6.1.4.1.9.9.23.1.2.1.1.6',
    'cdpCacheDevicePort': '1.3.6.1.4.1.9.9.23.1.2.1.1.7',
    'lldpLocPortId': '1.0.8802.1.1.2.1.3.7.1.3',
    'lldpRemChassisIdSubtype': '1.0.8802.1.1.2.1.4.1.1.4',
    'lldpRemChassisId': '1.0.8802.1.1.2.1.4.1.1.5',
    'lldpRemPortId': '1.0.8802.1.1.2.1.4.1.1.7',
    'lldpRemPortDesc': '1.0.8802.1.1.2.1.4.1.1.8',
    'lldpRemSysName': '1.0.8802.1.1.2.1.4.1.1.9',
}

ETHERNET, GIGABIT, SVI, LAG = 6, 117, 53, 161
UP, NOT_PRESENT = 1, 6
STATUS = {1: 'up', 2: 'down', 3: 'testing', 5: 'dormant',
          6: 'not present', 7: 'down'}
LLDP_MAC_CHASSIS = 4    # lldpRemChassisIdSubtype macAddress
# Addresses that aren't the switch's on the network: internal ones (a
# CBS350 has 169.254.0.1 and an unset out-of-band port in 0.0.0.0/8)
NOT_REAL = [ipaddress.ip_network(n) for n in
            ('0.0.0.0/8', '127.0.0.0/8', '169.254.0.0/16')]
MAC_LIKE = re.compile(r'^[0-9a-f]{12}$|^([0-9a-f]{4}\.){2}[0-9a-f]{4}$|'
                      r'^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$', re.IGNORECASE)
LEARNED = 3             # dot1dTpFdbStatus / dot1qTpFdbStatus
TRUNKING = 1            # vlanTrunkPortDynamicStatus
RESERVED_VLANS = range(1002, 1006)
SECRET_PREFIX = 'cisco_switches'


def speed(mbps):
    if not mbps:
        return ''
    if mbps >= 1000 and mbps % 1000 == 0:
        return '{0}G'.format(mbps // 1000)
    return '{0}M'.format(mbps)


def short_name(name):
    name = re.sub(r'\s+', '', (name or '').lower())
    for long, short in (('tengigabitethernet', 'te'),
                        ('gigabitethernet', 'gi'), ('fastethernet', 'fa'),
                        ('port-channel', 'po')):
        if name.startswith(long):
            return short + name[len(long):]
    return name


class CiscoSwitches (Plugin):
    """Cisco switches over SNMP (#19): each switch as a device (type
    switch) with its L3 interfaces (VLAN interfaces with an address) and
    address rows, and its ports (description, status, speed, VLAN, mode,
    port-channel membership, CDP/LLDP neighbour, learned MAC addresses) for
    the port map and the Switch Ports section. Cisco only: tested with a
    Catalyst 2960 (classic IOS: MAC tables per VLAN) and a CBS350
    (Q-BRIDGE-MIB). Shown as "CiscoSwitches" in the Seen by column."""
    expensive = True

    def __init__(self):
        super().__init__()

    def run(self):
        if not self.getConfig():
            return
        switches = self._config.get('switches') or []
        if not switches:
            self._logger.warning('No switches listed in "switches"')
            return
        for entry in switches:
            if isinstance(entry, str):
                entry = {'host': entry}
            if not entry.get('host'):
                raise snmp.SNMPError('CiscoSwitches: each switch needs a '
                                     '"host"')
            try:
                with snmp.session(SECRET_PREFIX, self._config,
                                  entry) as session:
                    self._read(session, entry)
            except snmp.SNMPError as e:
                raise snmp.SNMPError('CiscoSwitches: {0}'.format(e)) from None

    # --- reading one switch -------------------------------------------------

    def _table(self, session, name, **context):
        """{first index part (e.g. ifIndex): value} for a simple table."""
        return {index[0]: value
                for index, value in session.walk(OID[name], **context)
                if len(index) == 1}

    def _read(self, session, entry):
        sys_name = snmp.text(session.get(OID['sysName']))
        device = device_key(sys_name or entry['host'])
        self._logger.info('Reading {0} ({1})'.format(
            device, session.describe()))

        names = {i: snmp.text(v) for i, v in
                 self._table(session, 'ifName').items()}
        types = self._table(session, 'ifType')
        aliases = {i: snmp.text(v) for i, v in
                   self._table(session, 'ifAlias').items()}
        admin = self._table(session, 'ifAdminStatus')
        oper = self._table(session, 'ifOperStatus')
        speeds = self._table(session, 'ifHighSpeed')
        macs = {i: snmp.mac(v) for i, v in
                self._table(session, 'ifPhysAddress').items()}

        description = snmp.text(session.get(OID['sysDescr']))
        self.addDevice(device, source='CiscoSwitches', type='switch',
                       hostname=sys_name,
                       model=description.splitlines()[0] if description
                       else '')

        # The switch's own addresses: its L3 interfaces and address rows
        masks = {'.'.join(map(str, index)): value for index, value in
                 session.walk(OID['ipAdEntNetMask'])}
        for index, if_index in session.walk(OID['ipAdEntIfIndex']):
            ip = '.'.join(map(str, index))
            if any(ipaddress.ip_address(ip) in n for n in NOT_REAL):
                continue
            name = names.get(if_index, str(if_index))
            # A CBS350 names its VLAN interfaces by number ("1")
            if types.get(if_index) == SVI and name.isdigit():
                name = 'vlan ' + name
            subnet = ''
            if masks.get(ip):
                subnet = str(ipaddress.ip_interface(
                    '{0}/{1}'.format(ip, masks[ip])).network)
            self.addInterface(device, name, source='CiscoSwitches',
                              addresses=ip, subnet=subnet,
                              mac=macs.get(if_index, ''),
                              description=aliases.get(if_index, ''),
                              status=STATUS.get(oper.get(if_index), ''))
            self.addHost(ip, source='CiscoSwitches', device=device,
                         type='switch', hostname=sys_name,
                         mac=macs.get(if_index, ''), subnet=subnet)

        # Port-channel membership: member ifIndex -> channel ifIndex
        channel_of = {}
        for table in ('dot3adAggPortAttachedAggID', 'pagpGroupIfIndex'):
            for member, channel in self._table(session, table).items():
                if channel and channel != member and channel in names:
                    channel_of.setdefault(member, channel)

        bridge = self._table(session, 'dot1dBasePortIfIndex')
        ports = {i for i in names if types.get(i) in (ETHERNET, GIGABIT, LAG)
                 or short_name(names[i]).startswith('po')}
        ports |= set(bridge.values()) | set(channel_of) | \
            set(channel_of.values())
        channels = set(channel_of.values())
        ports = {i for i in ports if i in names
                 # Stack slots a switch reports but doesn't have
                 and (oper.get(i) != NOT_PRESENT or i in channel_of)
                 # Port-channels that aren't set up
                 and not (self._is_channel(types, names, i)
                          and i not in channels and oper.get(i) != UP)}

        # VLAN and mode: Cisco's own MIBs (2960), else the Q-BRIDGE PVID
        access_vlan = self._table(session, 'vmVlan')
        trunking = self._table(session, 'vlanTrunkPortDynamicStatus')
        pvid = {bridge[port]: vlan for port, vlan in
                self._table(session, 'dot1qPvid').items() if port in bridge}

        neighbours = self._neighbours(session, names)

        for if_index in ports:
            status = STATUS.get(oper.get(if_index), '')
            if admin.get(if_index) == 2:
                status = 'disabled'
            fields = {
                'description': aliases.get(if_index, ''),
                'status': status,
                'speed': speed(speeds.get(if_index)) if status == 'up'
                else '',
                'channel': names.get(channel_of.get(if_index), ''),
            }
            if if_index in trunking:
                fields['mode'] = 'trunk' if trunking[if_index] == TRUNKING \
                    else 'access'
            vlan = access_vlan.get(if_index) or pvid.get(if_index)
            if vlan and fields.get('mode') != 'trunk':
                fields['vlan'] = str(vlan)
            if if_index in neighbours:
                fields.update(neighbours[if_index])
            self.addPort(device, names[if_index], source='CiscoSwitches',
                         **fields)

        count = 0
        for if_index, mac, vlan in self._mac_table(session, bridge):
            if if_index in names:
                self.addPortMac(device, names[if_index], mac, vlan,
                                source='CiscoSwitches')
                count += 1
        self._logger.info('{0}: {1} ports, {2} learned MAC addresses'.format(
            device, len(ports), count))

    @staticmethod
    def _is_channel(types, names, if_index):
        return types.get(if_index) == LAG or \
            short_name(names.get(if_index, '')).startswith('po')

    def _neighbours(self, session, names):
        """{ifIndex: {neighbor_device, neighbor_port, and neighbor_address
        or neighbor_mac when known}} from CDP, then LLDP. The port map uses
        the address or MAC to find the device when the name isn't its own
        (a CBS350 sends its MAC as its CDP device ID; OPNsense says
        "OPNsense" over LLDP)."""
        found = {}
        ports = {index: snmp.text(v) for index, v in
                 session.walk(OID['cdpCacheDevicePort'])}
        addresses = {index: v for index, v in
                     session.walk(OID['cdpCacheAddress'])}
        for index, value in session.walk(OID['cdpCacheDeviceId']):
            name = snmp.text(value)
            # CDP device IDs can carry a serial: "sw1.example.com(FOC123)"
            name = re.sub(r'\(.*\)$', '', name)
            if not name:
                continue
            entry = {'neighbor_device': name if MAC_LIKE.match(name)
                     else device_key(name),
                     'neighbor_port': ports.get(index, '')}
            address = addresses.get(index)
            if isinstance(address, bytes) and len(address) == 4:
                entry['neighbor_address'] = '.'.join(map(str, address))
            found.setdefault(index[0], entry)

        # LLDP numbers ports its own way: match its port IDs to ifNames
        by_name = {short_name(n): i for i, n in names.items()}
        local = {index[0]: by_name.get(short_name(snmp.text(v)))
                 for index, v in session.walk(OID['lldpLocPortId'])
                 if len(index) == 1}
        port_ids = dict(session.walk(OID['lldpRemPortId']))
        port_descs = dict(session.walk(OID['lldpRemPortDesc']))
        chassis = dict(session.walk(OID['lldpRemChassisId']))
        chassis_kind = dict(session.walk(OID['lldpRemChassisIdSubtype']))
        for index, value in session.walk(OID['lldpRemSysName']):
            if len(index) < 3:
                continue
            if_index = local.get(index[1]) or \
                (index[1] if index[1] in names else None)
            name = snmp.text(value)
            if not if_index or not name:
                continue
            port = port_ids.get(index)
            # A port ID that's a MAC address says less than the description
            port = snmp.text(port) if port and not snmp.mac(port) else \
                snmp.text(port_descs.get(index))
            entry = {'neighbor_device': device_key(name),
                     'neighbor_port': port}
            if chassis_kind.get(index) == LLDP_MAC_CHASSIS:
                entry['neighbor_mac'] = snmp.mac(chassis.get(index))
            # LLDP's name beats a CDP device ID that's only a MAC address
            if if_index not in found or \
                    MAC_LIKE.match(found[if_index]['neighbor_device']):
                found[if_index] = dict(found.get(if_index, {}), **entry)
        return found

    def _mac_table(self, session, bridge):
        """[(ifIndex, mac, vlan)] of learned addresses: Q-BRIDGE-MIB where
        the switch has it (CBS350), else BRIDGE-MIB per VLAN (Catalyst
        classic IOS: community@vlan, or context vlan-N on SNMP v3)."""
        found = []
        status = dict(session.walk(OID['dot1qTpFdbStatus']))
        for index, port in session.walk(OID['dot1qTpFdbPort']):
            if status.get(index, LEARNED) == LEARNED and port in bridge:
                found.append((bridge[port], snmp.index_mac(index), index[0]))
        if found:
            return found

        vlans = sorted(index[-1] for index, state in
                       session.walk(OID['vtpVlanState'])
                       if state == 1 and index[-1] not in RESERVED_VLANS)
        contexts = [(v, {'community_suffix': '@{0}'.format(v),
                         'context_name': 'vlan-{0}'.format(v)})
                    for v in vlans] or [('', {})]
        for vlan, context in contexts:
            ports = self._table(session, 'dot1dBasePortIfIndex', **context) \
                or bridge
            status = dict(session.walk(OID['dot1dTpFdbStatus'], **context))
            for index, port in session.walk(OID['dot1dTpFdbPort'], **context):
                if status.get(index, LEARNED) == LEARNED and port in ports:
                    found.append((ports[port], snmp.index_mac(index),
                                  vlan))
        return found


def getPlugin():
    return CiscoSwitches()
