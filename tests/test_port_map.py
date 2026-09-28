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
    point and two clients behind it, and an uplink to the firewall; the
    hosts as the firewall's ARP table would report them."""
    vars.reset()
    s = Source()
    s.addDevice('core-sw.example.com', type='switch')
    s.addHost('192.0.2.11', source='snmp', device='core-sw', type='switch')
    s.addInterface('core-sw', 'Gi1/0/5', description='Living room TV')
    s.addInterfaceMac('core-sw', 'Gi1/0/5', 'AA:BB:CC:00:00:05', 1)
    s.addInterface('core-sw', 'Gi1/0/7', description='Office AP')
    for mac in ('aa:bb:cc:00:00:70', 'aa:bb:cc:00:00:71',
                'aa:bb:cc:00:00:72'):
        s.addInterfaceMac('core-sw', 'Gi1/0/7', mac, 1)
    s.addInterface('core-sw', 'Gi1/0/48', peer_device='fw',
                   peer_interface='igb1')
    for mac in ('aa:bb:cc:00:00:05', 'aa:bb:cc:00:00:70', 'fw:mac'):
        s.addInterfaceMac('core-sw', 'Gi1/0/48', mac, 1)
    s.addDevice('fw', type='router')
    s.addInterface('fw', 'igb1', mac='aa:bb:cc:ff:ff:01')
    s.addHost('192.0.2.5', source='OPNsense', mac='aa:bb:cc:00:00:05')
    s.addHost('192.0.2.70', source='OPNsense', mac='aa:bb:cc:00:00:70')
    s.addHost('192.0.2.71', source='OPNsense', mac='aa:bb:cc:00:00:71')
    s.addHost('192.0.2.99', source='OPNsense', mac='aa:bb:cc:00:00:99')
    return s


def run():
    port_map.getPlugin().run()


def test_device_key():
    assert device_key('Core-SW.example.com') == 'core-sw'
    assert device_key('192.0.2.1') == '192.0.2.1'


def test_host_alone_on_a_port(switch):
    run()

    host = vars.hosts['192.0.2.5']
    assert host['connected_to'] == 'core-sw Gi1/0/5'
    # the port's description names the host
    assert host['name'] == 'Living room TV'
    port = vars.devices['core-sw']['interfaces']['Gi1/0/5']
    assert port['connected_hosts'] == ['192.0.2.5']


def test_several_hosts_on_a_port_are_shared(switch):
    run()

    for ip in ('192.0.2.70', '192.0.2.71'):
        assert vars.hosts[ip]['connected_to'] == 'core-sw Gi1/0/7 (shared)'
        assert 'name' not in vars.hosts[ip]   # not everyone is "Office AP"
    port = vars.devices['core-sw']['interfaces']['Gi1/0/7']
    assert sorted(port['connected_hosts']) == ['192.0.2.70', '192.0.2.71']


def test_uplinks_are_not_where_hosts_are(switch):
    run()

    uplink = vars.devices['core-sw']['interfaces']['Gi1/0/48']
    assert uplink['connected_hosts'] == []
    # ...and the neighbour is linked back from the firewall's side
    igb1 = vars.devices['fw']['interfaces']['igb1']
    assert (igb1['peer_device'], igb1['peer_interface']) == \
        ('core-sw', 'Gi1/0/48')


def test_long_and_short_interface_names_match(switch):
    switch.addInterface('fw', 'igb2', peer_device='core-sw',
                        peer_interface='GigabitEthernet1/0/9')
    switch.addInterface('core-sw', 'Gi1/0/9')

    run()

    port = vars.devices['core-sw']['interfaces']['Gi1/0/9']
    assert (port['peer_device'], port['peer_interface']) == ('fw', 'igb2')


def test_host_override_name_wins(switch):
    vars.hosts['192.0.2.5']['name'] = 'TV'

    run()

    assert vars.hosts['192.0.2.5']['name'] == 'TV'


def test_hosts_without_a_port_are_untouched(switch):
    run()

    assert 'connected_to' not in vars.hosts['192.0.2.99']
    assert 'connected_to' not in vars.hosts['192.0.2.11']


def test_turned_off_in_config(switch):
    vars.config = {'plugins': {'PortMap': {'enabled': 0}}}

    run()

    assert 'connected_to' not in vars.hosts['192.0.2.5']


def test_runs_on_every_rebuild():
    assert pipeline.always_runs(port_map.getPlugin())


def test_device_records_survive_a_partial_rebuild(monkeypatch):
    vars.reset()

    class Switches(Plugin):
        def run(self):
            self.addDevice('sw', type='switch')
            self.addInterface('sw', 'Gi1/0/1', description='Printer')
            self.addInterfaceMac('sw', 'Gi1/0/1', 'aa:bb:cc:00:00:01', 10)

    plugin = Switches()
    monkeypatch.setattr(pipeline, 'directory', lambda p: 'x-switches')
    monkeypatch.setattr(pipeline, 'config_section', lambda p: None)
    monkeypatch.setattr(pipeline, 'source_mtime', lambda p: 0)
    monkeypatch.setattr(vars, 'plugin_cache', {})
    pipeline.run_recorded(plugin)
    before = vars.devices['sw']
    vars.devices = {}

    pipeline.replay(plugin)

    assert vars.devices['sw'] == before
    assert vars.devices['sw']['interfaces']['Gi1/0/1']['macs'] == \
        {'aa:bb:cc:00:00:01': '10'}
