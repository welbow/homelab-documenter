import importlib
import logging
import re

import pytest

import vars
from Plugin import Plugin

nmapmod = importlib.import_module('plugins.100-nmap-ping-scan')


class Source(Plugin):
    pass


def test_addHost_merges_sources_and_fields(caplog):
    a, b = Source(), Source()

    a.addHost('192.168.2.1', source='nmap', hostname='router.lan',
              subnet='192.168.2.0/24')
    b.addHost('192.168.2.1', source='dhcp', hostname='', mac='AA:BB')
    with caplog.at_level(logging.INFO):
        b.addHost('192.168.2.1', source='switch', hostname='other.lan')
    b.addHost('192.168.2.1', source='dhcp')

    assert vars.hosts['192.168.2.1'] == {
        'ipaddress': '192.168.2.1', 'hostname': 'router.lan',
        'subnet': '192.168.2.0/24', 'mac': 'AA:BB',
        'sources': ['nmap', 'dhcp', 'switch']}
    assert "keeping hostname 'router.lan', switch reported 'other.lan'" \
        in caplog.text


def test_addHost_default_source_is_class_name():
    Source().addHost('10.0.0.5')

    assert vars.hosts['10.0.0.5']['sources'] == ['Source']


class FakeScanner:
    """Stands in for nmap.PortScanner; records the arguments it got."""
    calls = []
    results = {}

    def scan(self, hosts, arguments):
        FakeScanner.calls.append((hosts, arguments))
        self._hosts = FakeScanner.results[hosts]

    def all_hosts(self):
        return list(self._hosts)

    def __getitem__(self, host):
        return self._hosts[host]


@pytest.fixture
def scan(monkeypatch):
    FakeScanner.calls = []
    monkeypatch.setattr(nmapmod.nmap, 'PortScanner', FakeScanner)
    plugin = nmapmod.getPlugin()
    vars.config = {'plugins': {'NmapPingScan': {
        'enabled': 1, 'subnets': ['192.168.2.0/24']}}}
    return plugin


def test_nmap_pings_only_with_system_resolver(scan):
    FakeScanner.results = {'192.168.2.0/24': {}}

    scan.run()

    assert FakeScanner.calls[0][1] == '-sn -PE --disable-arp-ping'


def test_nmap_skips_broadcast_and_handles_missing_names(scan):
    FakeScanner.results = {'192.168.2.0/24': {
        '192.168.2.1': {'hostnames': [{'name': 'router.lan'}]},
        '192.168.2.20': {'hostnames': [{'name': '', 'type': ''}]},
        '192.168.2.30': {'hostnames': []},
        '192.168.2.255': {'hostnames': []},
        '192.168.2.0': {'hostnames': []},
    }}

    scan.run()

    assert sorted(vars.hosts) == ['192.168.2.1', '192.168.2.20',
                                  '192.168.2.30']
    assert vars.hosts['192.168.2.1']['hostname'] == 'router.lan'
    assert 'hostname' not in vars.hosts['192.168.2.20']
    assert vars.hosts['192.168.2.30']['subnet'] == '192.168.2.0/24'
    assert vars.hosts['192.168.2.30']['sources'] == ['nmap']


def test_host_table_shows_only_filled_columns_in_ip_order():
    Source().addHost('192.168.2.20', source='nmap', subnet='192.168.2.0/24')
    Source().addHost('192.168.2.3', source='nmap', hostname='desktop.lan',
                     subnet='192.168.2.0/24')
    Source().addHost('192.168.2.3', source='dhcp')
    vars.config = {'plugins': {'OutputHostInfo': {
        'enabled': 1, 'title': 'Hosts', 'header': 'All hosts',
        'seq_number': 950}}}

    importlib.import_module('plugins.900-output-host-info').getPlugin().run()
    html = str(vars.output['950-output-host-info']['output'])

    assert re.findall(r'<th>([^<]*)</th>', html) \
        == ['Hostname', 'IP Address', 'Type', 'Subnet', 'Seen by']
    assert re.findall(r'<td>([^<]*)</td>', html) == [
        'desktop.lan', '192.168.2.3', 'Unknown', '192.168.2.0/24',
        'nmap, dhcp',
        '', '192.168.2.20', 'Unknown', '192.168.2.0/24', 'nmap']


def test_type_from_a_source_replaces_unknown():
    Source().addHost('192.168.2.1', source='nmap')
    Source().addHost('192.168.2.2', source='nmap')
    Source().addHost('192.168.2.1', source='switch', type='router')
    vars.config = {'plugins': {'OutputHostInfo': {
        'enabled': 1, 'title': 'Hosts', 'header': 'All hosts',
        'seq_number': 950}}}

    importlib.import_module('plugins.900-output-host-info').getPlugin().run()
    html = str(vars.output['950-output-host-info']['output'])

    assert re.findall(r'<th>([^<]*)</th>', html) \
        == ['IP Address', 'Type', 'Seen by']
    assert re.findall(r'<td>([^<]*)</td>', html) \
        == ['192.168.2.1', 'router', 'nmap, switch',
            '192.168.2.2', 'Unknown', 'nmap']
