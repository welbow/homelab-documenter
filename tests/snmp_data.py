"""Recorded-style SNMP data for a Catalyst 2960 (classic IOS: MAC tables
per VLAN context) and a CBS350 (Q-BRIDGE-MIB), made up but shaped like
what they return. Used by FakeSession in the tests, and writable as
snmpsim .snmprec files to try the real SNMP code against a simulator."""
import importlib

cisco = importlib.import_module('plugins.120-cisco-switches')
OID = cisco.OID


class IP(str):
    """An IpAddress value (a plain str is an OctetString)."""


def mac(text):
    return bytes(int(b, 16) for b in text.split(':'))


def oid(name, *index):
    base = tuple(int(p) for p in OID[name].split('.'))
    if name in ('sysName', 'sysDescr'):
        return base
    return base + tuple(index)


def mac_index(text):
    return tuple(int(b, 16) for b in text.split(':'))


def ip_index(text):
    return tuple(int(p) for p in text.split('.'))


def catalyst_2960():
    """{context: {oid: value}}; '' is the default context, '1' and '10' the
    per-VLAN ones (community@1, community@10)."""
    d = {}
    d[oid('sysName')] = b'access-sw.example.com'
    d[oid('sysDescr')] = (b'Cisco IOS Software, C2960 Software '
                          b'(C2960-LANBASEK9-M), Version 15.0(2)SE11\r\n'
                          b'Technical Support: http://www.cisco.com')
    ifs = {1: ('Vl1', 53), 10101: ('Gi0/1', 6), 10102: ('Gi0/2', 6),
           10103: ('Gi0/3', 6), 10104: ('Gi0/4', 6), 5001: ('Po1', 53)}
    for i, (name, kind) in ifs.items():
        d[oid('ifName', i)] = name.encode()
        d[oid('ifType', i)] = kind
        d[oid('ifAdminStatus', i)] = 1
        d[oid('ifOperStatus', i)] = 2 if i == 10104 else 1
        d[oid('ifHighSpeed', i)] = 1000
        d[oid('ifAlias', i)] = b''
        d[oid('ifPhysAddress', i)] = mac('00:11:22:33:44:{0:02x}'.format(
            i % 256))
    d[oid('ifAlias', 10101)] = b'Living room TV'
    d[oid('ipAdEntIfIndex', *ip_index('192.0.2.12'))] = 1
    d[oid('ipAdEntNetMask', *ip_index('192.0.2.12'))] = IP('255.255.255.0')
    d[oid('ipAdEntIfIndex', *ip_index('127.0.0.1'))] = 1
    # PAgP: Gi0/3-4 in Po1, the rest in their own group
    for i in ifs:
        d[oid('pagpGroupIfIndex', i)] = 5001 if i in (10103, 10104) else i
    for i, vlan in ((1, 1), (10, 1), (1002, 1)):
        d[oid('vtpVlanState', 1, i)] = vlan
    d[oid('vmVlan', 10101)] = 1
    d[oid('vmVlan', 10102)] = 10
    d[oid('vlanTrunkPortDynamicStatus', 10101)] = 2
    d[oid('vlanTrunkPortDynamicStatus', 10102)] = 2
    d[oid('vlanTrunkPortDynamicStatus', 5001)] = 1
    d[oid('cdpCacheDeviceId', 10103, 1)] = b'core-sw(FOC1234X5YZ)'
    d[oid('cdpCacheDevicePort', 10103, 1)] = b'GigabitEthernet1/0/47'

    bridge = {1: 10101, 2: 10102, 56: 5001}
    per_vlan = {'1': [('aa:bb:cc:00:00:05', 1), ('aa:bb:cc:ff:ff:01', 56),
                      ('00:11:22:33:44:01', 56)],
                '10': [('aa:bb:cc:00:00:10', 2)]}
    contexts = {'': d}
    for vlan, entries in per_vlan.items():
        c = {}
        for port, if_index in bridge.items():
            c[oid('dot1dBasePortIfIndex', port)] = if_index
        for address, port in entries:
            c[oid('dot1dTpFdbPort', *mac_index(address))] = port
            c[oid('dot1dTpFdbStatus', *mac_index(address))] = 3
        contexts[vlan] = c
    # The default context has the bridge ports but no Q-BRIDGE table
    for port, if_index in bridge.items():
        d[oid('dot1dBasePortIfIndex', port)] = if_index
    return contexts


def cbs350():
    d = {}
    d[oid('sysName')] = b'core-sw'
    d[oid('sysDescr')] = b'CBS350-24P-4G 24-Port Gigabit PoE Managed Switch'
    ifs = {1: ('gi1/0/1', 6), 2: ('gi1/0/2', 6), 47: ('gi1/0/47', 6),
           48: ('gi1/0/48', 6), 1000: ('Po1', 161),
           100000: ('vlan 1', 136)}
    for i, (name, kind) in ifs.items():
        d[oid('ifName', i)] = name.encode()
        d[oid('ifType', i)] = kind
        d[oid('ifAdminStatus', i)] = 2 if i == 2 else 1
        d[oid('ifOperStatus', i)] = 2 if i == 2 else 1
        d[oid('ifHighSpeed', i)] = 2000 if i == 1000 else 1000
        d[oid('ifAlias', i)] = b'Firewall LAN' if i == 1 else b''
        d[oid('ifPhysAddress', i)] = mac('00:aa:bb:cc:dd:{0:02x}'.format(
            i % 256))
    d[oid('ipAdEntIfIndex', *ip_index('192.0.2.11'))] = 100000
    d[oid('ipAdEntNetMask', *ip_index('192.0.2.11'))] = IP('255.255.255.0')
    for i in (1, 2, 47, 48):
        d[oid('dot3adAggPortAttachedAggID', i)] = 1000 if i >= 47 else 0
        d[oid('dot1dBasePortIfIndex', i)] = i
    d[oid('dot1dBasePortIfIndex', 1000)] = 1000
    d[oid('dot1qPvid', 1)] = 1
    d[oid('dot1qPvid', 2)] = 20
    d[oid('dot1qPvid', 1000)] = 1
    for vlan, address, port, status in (
            (1, 'aa:bb:cc:ff:ff:01', 1, 3), (1, 'aa:bb:cc:00:00:05', 1000, 3),
            (10, 'aa:bb:cc:00:00:10', 1000, 3),
            (1, '00:aa:bb:cc:dd:e8', 0, 4)):          # its own: not learned
        d[oid('dot1qTpFdbPort', vlan, *mac_index(address))] = port
        d[oid('dot1qTpFdbStatus', vlan, *mac_index(address))] = status
    d[oid('lldpLocPortId', 47)] = b'gi1/0/47'
    d[oid('lldpRemSysName', 0, 47, 1)] = b'access-sw.example.com'
    d[oid('lldpRemPortId', 0, 47, 1)] = b'Gi0/3'
    d[oid('lldpRemPortDesc', 0, 47, 1)] = b'GigabitEthernet0/3'
    return {'': d}


class FakeSession:
    """Serves one of the data sets like snmp.Session does."""

    def __init__(self, host, contexts, found=None):
        self.host = host
        self.contexts = contexts
        self.found = found or {'version': '2c', 'port': 161}
        self.walked = []

    def describe(self):
        return '{0} (fake)'.format(self.host)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def _data(self, community_suffix, context_name):
        if self.found['version'] == '3':
            name = (context_name or '').replace('vlan-', '')
        else:
            name = (community_suffix or '').lstrip('@')
        return self.contexts.get(name, {})

    @staticmethod
    def _value(value):
        return str(value) if isinstance(value, IP) else value

    def get(self, oid_text, community_suffix=None, context_name=None):
        key = tuple(int(p) for p in oid_text.split('.'))
        value = self._data(community_suffix, context_name).get(key)
        return None if value is None else self._value(value)

    def walk(self, oid_text, community_suffix=None, context_name=None):
        self.walked.append((oid_text, community_suffix, context_name))
        prefix = tuple(int(p) for p in oid_text.split('.'))
        data = self._data(community_suffix, context_name)
        return [(key[len(prefix):], self._value(value))
                for key, value in sorted(data.items())
                if key[:len(prefix)] == prefix and len(key) > len(prefix)]


def snmprec(data):
    """One context as snmpsim .snmprec text."""
    lines = []
    for key, value in sorted(data.items()):
        name = '.'.join(map(str, key))
        if isinstance(value, IP):
            lines.append('{0}|64|{1}'.format(name, value))
        elif isinstance(value, bytes):
            lines.append('{0}|4x|{1}'.format(name, value.hex()))
        else:
            lines.append('{0}|2|{1}'.format(name, value))
    return '\n'.join(lines) + '\n'
