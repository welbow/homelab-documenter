import importlib

import pytest

import pipeline
import vars
from Plugin import Plugin, device_key

port_map = importlib.import_module('plugins.800-port-map')


class Source(Plugin):
    pass


@pytest.fixture
def switch():
    """A switch with an access port (one device), a port with an access
    point and two clients behind it, a port-channel uplink to another
    switch, and a port to the firewall; hosts as the firewall's ARP table
    would report them."""
    vars.reset()
    s = Source()
    s.addDevice('core-sw.example.com', type='switch')
    s.addInterface('core-sw', 'Vlan1', addresses='192.0.2.11',
                   mac='aa:bb:cc:11:11:11')
    s.addHost('192.0.2.11', source='SNMP', device='core-sw', type='switch',
              mac='aa:bb:cc:11:11:11')
    s.addPort('core-sw', 'Gi1/0/5', description='Living room TV',
              status='up', speed='1G', vlan='1', mode='access')
    s.addPortMac('core-sw', 'Gi1/0/5', 'AA:BB:CC:00:00:05', 1)
    s.addPort('core-sw', 'Gi1/0/7', description='Office AP')
    for mac in ('aa:bb:cc:00:00:70', 'aa:bb:cc:00:00:71',
                'aa:bb:cc:00:00:72'):
        s.addPortMac('core-sw', 'Gi1/0/7', mac, 1)
    s.addPort('core-sw', 'Gi1/0/9')                     # nothing on it
    # Po1 to the access switch, members Gi1/0/47-48; CDP on a member
    s.addPort('core-sw', 'Po1', mode='trunk')
    s.addPort('core-sw', 'Gi1/0/47', channel='Po1',
              neighbor_device='access-sw.example.com',
              neighbor_port='GigabitEthernet0/1')
    s.addPort('core-sw', 'Gi1/0/48', channel='Po1')
    for mac in ('aa:bb:cc:00:00:05', 'aa:bb:cc:00:00:70',
                'aa:bb:cc:00:00:99'):
        s.addPortMac('core-sw', 'Po1', mac, 1)
    s.addPort('access-sw', 'Gi0/1')
    s.addPortMac('access-sw', 'Gi0/2', 'aa:bb:cc:00:00:99', 1)
    # The firewall's LAN interface on Gi1/0/1 (no CDP/LLDP from it)
    s.addDevice('fw', type='router')
    s.addInterface('fw', 'igb1', mac='aa:bb:cc:ff:ff:01',
                   addresses='192.0.2.1')
    s.addHost('192.0.2.1', source='OPNsense', device='fw',
              mac='aa:bb:cc:ff:ff:01')
    s.addPortMac('core-sw', 'Gi1/0/1', 'aa:bb:cc:ff:ff:01', 1)
    s.addHost('192.0.2.5', source='OPNsense', mac='aa:bb:cc:00:00:05')
    s.addHost('192.0.2.70', source='OPNsense', mac='aa:bb:cc:00:00:70',
              hostname='laptop')
    s.addHost('192.0.2.71', source='OPNsense', mac='aa:bb:cc:00:00:71')
    s.addHost('192.0.2.99', source='OPNsense', mac='aa:bb:cc:00:00:99')
    s.addHost('192.0.2.200', source='OPNsense', mac='aa:bb:cc:00:02:00')
    return s


def run():
    port_map.getPlugin().run()


def port(switch, name):
    return vars.ports[(switch, name)]


def test_device_key():
    assert device_key('Core-SW.example.com') == 'core-sw'
    assert device_key('192.0.2.1') == '192.0.2.1'


def test_host_alone_on_a_port(switch):
    run()

    host = vars.hosts['192.0.2.5']
    assert host['connected_to'] == 'core-sw Gi1/0/5'
    assert host['name'] == 'Living room TV'     # from the port description
    assert port('core-sw', 'Gi1/0/5')['connected'] == \
        ['Living room TV (192.0.2.5)']


def test_several_hosts_on_a_port_are_shared(switch):
    run()

    for ip in ('192.0.2.70', '192.0.2.71'):
        assert vars.hosts[ip]['connected_to'] == 'core-sw Gi1/0/7 (shared)'
        assert 'name' not in vars.hosts[ip]   # not everyone is "Office AP"
    assert sorted(port('core-sw', 'Gi1/0/7')['connected']) == \
        ['192.0.2.71', 'laptop (192.0.2.70)']


def test_port_channel_rolls_up_members(switch):
    run()

    po1 = port('core-sw', 'Po1')
    assert po1['members'] == ['Gi1/0/47', 'Gi1/0/48']
    # the member's CDP neighbour counts for the channel
    assert po1['connected'] == ['Uplink: access-sw GigabitEthernet0/1']
    # MACs seen on the uplink belong where they're plugged in
    assert vars.hosts['192.0.2.99']['connected_to'] == 'access-sw Gi0/2'
    # and the other side learns the neighbour too
    assert port('access-sw', 'Gi0/1')['neighbor_device'] == 'core-sw'


def test_device_interface_on_a_port(switch):
    run()

    assert port('core-sw', 'Gi1/0/1')['connected'] == ['fw igb1']
    igb1 = vars.devices['fw']['interfaces']['igb1']
    assert igb1['connected_to'] == 'core-sw Gi1/0/1'
    # the firewall's row isn't listed again as a host
    assert 'connected_to' not in vars.hosts['192.0.2.1']


def test_long_and_short_names_match(switch):
    switch.addInterface('fw', 'igb2')
    switch.addPort('core-sw', 'Gi1/0/2', neighbor_device='fw',
                   neighbor_port='igb2')
    switch.addPort('access-sw', 'Gi0/3', neighbor_device='core-sw',
                   neighbor_port='GigabitEthernet1/0/9')

    run()

    assert vars.devices['fw']['interfaces']['igb2']['connected_to'] == \
        'core-sw Gi1/0/2'
    assert port('core-sw', 'Gi1/0/9')['neighbor_device'] == 'access-sw'


def test_switch_ports_section(switch):
    vars.config = {'plugins': {'PortMap': {
        'section': {'title': 'Switch ports', 'seq_number': '956'}}}}

    run()

    html = vars.output['956-switch-ports']['output'].render()
    assert '<h2>access-sw</h2>' in html and '<h2>core-sw</h2>' in html
    assert '<td>Po1 (Gi1/0/47, Gi1/0/48)</td>' in html
    assert '<td>Gi1/0/47</td>' not in html      # listed with its channel
    assert html.index('Gi1/0/5<') < html.index('Gi1/0/9<') < \
        html.index('Po1 (')                     # port order
    assert '<td>Living room TV (192.0.2.5)</td>' in html


def test_section_can_be_left_out(switch):
    vars.config = {'plugins': {'PortMap': {'section': 0}}}

    run()

    assert not any(k.endswith('switch-ports') for k in vars.output)
    assert vars.hosts['192.0.2.5']['connected_to'] == 'core-sw Gi1/0/5'


def test_host_override_name_wins(switch):
    vars.hosts['192.0.2.5']['name'] = 'TV'

    run()

    assert vars.hosts['192.0.2.5']['name'] == 'TV'


def test_hosts_not_on_any_port_are_untouched(switch):
    run()

    assert 'connected_to' not in vars.hosts['192.0.2.200']
    assert 'connected_to' not in vars.hosts['192.0.2.11']   # the switch


def test_nothing_to_do_without_ports():
    vars.reset()
    Source().addHost('192.0.2.5', source='x', mac='aa:bb:cc:00:00:05')

    run()

    assert vars.output == {}


def test_turned_off_in_config(switch):
    vars.config = {'plugins': {'PortMap': {'enabled': 0}}}

    run()

    assert 'connected_to' not in vars.hosts['192.0.2.5']


def test_runs_on_every_rebuild():
    assert pipeline.always_runs(port_map.getPlugin())


def test_devices_and_ports_survive_a_partial_rebuild(monkeypatch):
    vars.reset()

    class Switches(Plugin):
        def run(self):
            self.addDevice('sw', type='switch')
            self.addInterface('sw', 'Vlan1', addresses='192.0.2.11')
            self.addPort('sw', 'Gi1/0/1', description='Printer')
            self.addPortMac('sw', 'Gi1/0/1', 'aa:bb:cc:00:00:01', 10)

    plugin = Switches()
    monkeypatch.setattr(pipeline, 'directory', lambda p: 'x-switches')
    monkeypatch.setattr(pipeline, 'config_section', lambda p: None)
    monkeypatch.setattr(pipeline, 'source_mtime', lambda p: 0)
    monkeypatch.setattr(vars, 'plugin_cache', {})
    pipeline.run_recorded(plugin)
    devices, ports = vars.devices, vars.ports
    vars.devices, vars.ports = {}, {}

    pipeline.replay(plugin)

    assert vars.devices == devices and vars.ports == ports
    assert vars.ports[('sw', 'Gi1/0/1')]['macs'] == \
        {'aa:bb:cc:00:00:01': '10'}
