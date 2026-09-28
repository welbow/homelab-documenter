import importlib

import pytest

import credentials
import snmp
import vars
from Plugin import Plugin
from snmp_data import FakeSession, catalyst_2960, cbs350

cisco = importlib.import_module('plugins.120-cisco-switches')
port_map = importlib.import_module('plugins.800-port-map')

DATA = {'192.0.2.12': catalyst_2960, '192.0.2.11': cbs350}


@pytest.fixture
def switches(tmp_path, monkeypatch):
    vars.reset(str(tmp_path))
    vars.config = {'plugins': {'CiscoSwitches': {
        'enabled': 1, 'switches': [{'host': '192.0.2.11'},
                                   {'host': '192.0.2.12'}]}}}
    sessions = {}

    def session(prefix, config, device):
        found = snmp.settings(prefix, config, device)
        sessions[device['host']] = FakeSession(
            device['host'], DATA[device['host']](), found)
        return sessions[device['host']]
    monkeypatch.setattr(cisco.snmp, 'session', session)
    return sessions


def config():
    return vars.config['plugins']['CiscoSwitches']


def run():
    cisco.getPlugin().run()


def port(switch, name):
    return vars.ports[(switch, name)]


# --- Catalyst 2960 (classic IOS) --------------------------------------------

def test_2960_device_address_and_l3_interface(switches):
    run()

    sw = vars.devices['access-sw']
    assert sw['type'] == 'switch'
    assert sw['model'].startswith('Cisco IOS Software, C2960')
    vl1 = sw['interfaces']['Vl1']
    assert vl1['addresses'] == '192.0.2.12'
    assert vl1['subnet'] == '192.0.2.0/24'
    assert list(sw['interfaces']) == ['Vl1']        # ports aren't interfaces
    host = vars.hosts['192.0.2.12']
    assert host['device'] == 'access-sw' and host['type'] == 'switch'
    assert host['hostname'] == 'access-sw.example.com'
    assert host['sources'] == ['CiscoSwitches']
    assert '127.0.0.1' not in vars.hosts


def test_2960_ports(switches):
    run()

    gi1 = port('access-sw', 'Gi0/1')
    assert (gi1['description'], gi1['status'], gi1['speed'], gi1['vlan'],
            gi1['mode']) == ('Living room TV', 'up', '1G', '1', 'access')
    assert port('access-sw', 'Gi0/2')['vlan'] == '10'
    gi4 = port('access-sw', 'Gi0/4')
    assert gi4['status'] == 'down' and 'speed' not in gi4
    assert gi4['channel'] == 'Po1'
    gi3 = port('access-sw', 'Gi0/3')
    assert gi3['channel'] == 'Po1'
    # CDP from a CBS350: its ID is a MAC, so its address comes along for
    # the port map to find it by
    assert (gi3['neighbor_device'], gi3['neighbor_port'],
            gi3['neighbor_address']) == ('00aabbccdda0', 'gi1/0/47',
                                         '192.0.2.11')
    # CDP from a Catalyst: the serial number is trimmed off
    assert port('access-sw', 'Gi0/1')['neighbor_device'] == 'phone'
    po1 = port('access-sw', 'Po1')
    assert po1['mode'] == 'trunk' and 'vlan' not in po1
    assert ('access-sw', 'Vl1') not in vars.ports


def test_2960_mac_tables_per_vlan(switches):
    run()

    assert port('access-sw', 'Gi0/1')['macs'] == {'aa:bb:cc:00:00:05': '1'}
    assert port('access-sw', 'Gi0/2')['macs'] == {'aa:bb:cc:00:00:10': '10'}
    assert 'aa:bb:cc:ff:ff:01' in port('access-sw', 'Po1')['macs']
    suffixes = {s for oid, s, _ in switches['192.0.2.12'].walked if s}
    assert suffixes == {'@1', '@10'}          # 1002-1005 are skipped


# --- CBS350 (Q-BRIDGE-MIB) ----------------------------------------------------

def test_cbs350(switches):
    run()

    sw = vars.devices['core-sw']
    # the VLAN interface named by number gets a readable name; internal
    # addresses (oob, 169.254.x) are left out
    assert list(sw['interfaces']) == ['vlan 1']
    assert sw['interfaces']['vlan 1']['addresses'] == '192.0.2.11'
    assert '169.254.0.1' not in vars.hosts and '0.0.4.26' not in vars.hosts
    # stack slots that aren't there, and unused port-channels, aren't ports
    assert ('core-sw', 'te2/0/1') not in vars.ports
    assert ('core-sw', 'Po2') not in vars.ports
    gi1 = port('core-sw', 'gi1/0/1')
    assert (gi1['neighbor_device'], gi1['neighbor_port'],
            gi1['neighbor_mac']) == ('opnsense', 'igb1', 'aa:bb:cc:ff:ff:01')
    assert port('core-sw', 'gi1/0/1')['description'] == 'Firewall LAN'
    assert port('core-sw', 'gi1/0/1')['macs'] == {'aa:bb:cc:ff:ff:01': '1'}
    assert port('core-sw', 'gi1/0/2')['status'] == 'disabled'
    assert port('core-sw', 'gi1/0/2')['vlan'] == '20'
    for member in ('gi1/0/47', 'gi1/0/48'):
        assert port('core-sw', member)['channel'] == 'Po1'
    # LLDP on a member port
    gi47 = port('core-sw', 'gi1/0/47')
    assert (gi47['neighbor_device'], gi47['neighbor_port']) == \
        ('access-sw', 'Gi0/3')
    assert port('core-sw', 'Po1')['speed'] == '2G'
    # the switch's own MAC (status "self") isn't a learned address
    assert all('00:aa:bb:cc:dd:e8' not in p['macs']
               for p in vars.ports.values())
    # the Q-BRIDGE table answered, so no per-VLAN walks
    assert not any(s for _, s, _ in switches['192.0.2.11'].walked)


# --- together, with the port map --------------------------------------------

def test_hosts_are_placed_on_their_ports(switches):
    run()
    fw = Plugin()
    fw.addDevice('fw', type='router')
    fw.addInterface('fw', 'igb1', mac='aa:bb:cc:ff:ff:01',
                    addresses='192.0.2.1')
    fw.addHost('192.0.2.1', source='OPNsense', device='fw',
               mac='aa:bb:cc:ff:ff:01')
    fw.addHost('192.0.2.5', source='OPNsense', mac='aa:bb:cc:00:00:05')
    fw.addHost('192.0.2.10', source='OPNsense', mac='aa:bb:cc:00:00:10')

    port_map.getPlugin().run()

    assert vars.hosts['192.0.2.5']['connected_to'] == 'access-sw Gi0/1'
    assert vars.hosts['192.0.2.5']['name'] == 'Living room TV'
    assert vars.hosts['192.0.2.10']['connected_to'] == 'access-sw Gi0/2'
    # the firewall said "OPNsense" over LLDP: found by its MAC instead
    assert port('core-sw', 'gi1/0/1')['connected'] == ['Uplink: fw igb1']
    assert vars.devices['fw']['interfaces']['igb1']['connected_to'] == \
        'core-sw gi1/0/1'
    # the port-channels face each other; the CBS350's MAC-like CDP ID is
    # resolved to its device
    assert port('core-sw', 'Po1')['connected'] == \
        ['Uplink: access-sw Gi0/3']
    assert port('access-sw', 'Po1')['connected'] == \
        ['Uplink: core-sw gi1/0/47']
    html = vars.output['970-switch-ports']['output'].render()
    assert '<td>Po1 (gi1/0/47, gi1/0/48)</td>' in html
    assert '<td>Po1 (Gi0/3, Gi0/4)</td>' in html


# --- SNMP v3 and settings -------------------------------------------------------

def test_v3_uses_vlan_contexts(switches):
    config().update({'version': '3', 'user': 'docs'})

    run()

    walked = switches['192.0.2.12'].walked
    assert {c for _, _, c in walked if c} == {'vlan-1', 'vlan-10'}
    assert port('access-sw', 'Gi0/2')['macs'] == {'aa:bb:cc:00:00:10': '10'}


def test_settings_default_secret_names():
    found = snmp.settings('cisco_switches', {}, {'host': 'sw'})
    assert found['version'] == '2c'
    assert found['community_secret'] == 'cisco_switches_snmp_community'
    found = snmp.settings('cisco_switches', {'version': 3, 'user': 'u'},
                          {'host': 'sw'})
    assert found['auth_secret'] == 'cisco_switches_snmp_auth_password'
    assert found['priv_secret'] == 'cisco_switches_snmp_priv_password'


def test_settings_overrides():
    plugin = {'community_secret': 'shared_snmp', 'timeout': 2}
    assert snmp.settings('p', plugin, {'host': 'a'})['community_secret'] == \
        'shared_snmp'
    one = snmp.settings('p', plugin, {'host': 'b', 'community_secret':
                                      'b_community', 'version': '3',
                                      'user': 'x'})
    assert one['version'] == '3' and one['user'] == 'x'
    assert snmp.settings('p', plugin, {'host': 'a'})['timeout'] == 2


def test_bad_version():
    with pytest.raises(snmp.SNMPError, match='use "2c" or "3"'):
        snmp.settings('p', {'version': '1'}, {'host': 'a'})


def test_missing_community_says_how_to_store_it(tmp_path):
    vars.reset(str(tmp_path))
    with pytest.raises(snmp.SNMPError,
                       match='hd secret set cisco_switches_snmp_community'):
        snmp.session('cisco_switches', {}, {'host': '192.0.2.11'})


def test_stored_community_is_used(tmp_path):
    vars.reset(str(tmp_path))
    credentials.put('cisco_switches_snmp_community', 'public-test')
    with snmp.session('cisco_switches', {}, {'host': '192.0.2.11'}) as s:
        assert s._secrets['community'] == 'public-test'
        assert s.describe() == '192.0.2.11 (SNMP v2c, port 161)'


def test_plugin_errors_name_the_plugin(tmp_path):
    vars.reset(str(tmp_path))
    vars.config = {'plugins': {'CiscoSwitches': {
        'enabled': 1, 'switches': ['192.0.2.11']}}}

    with pytest.raises(snmp.SNMPError, match='^CiscoSwitches: credential'):
        run()


def test_values():
    assert snmp.text(b'core-sw\x00') == 'core-sw'
    assert snmp.mac(bytes([0, 17, 34, 51, 68, 85])) == '00:11:22:33:44:55'
    assert snmp.mac(b'short') == ''
    assert snmp.index_mac((10, 170, 187, 204, 0, 0, 5)) == \
        'aa:bb:cc:00:00:05'
    assert cisco.speed(100) == '100M' and cisco.speed(10000) == '10G'
