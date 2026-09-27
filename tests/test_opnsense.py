import base64
import importlib
import io
import json
import logging
import ssl
import urllib.error
import urllib.parse

import pytest

import credentials
import vars
from Plugin import Plugin

opnsense = importlib.import_module('plugins.150-opnsense')

KEY = 'test-key-AAAA'
SECRET = 'test-secret-BBBB'

# Trimmed responses in the shape OPNsense returns them
INTERFACES = {'total': 3, 'rows': [
    {'identifier': 'lan', 'description': 'LAN', 'device': 'igb1',
     'enabled': True, 'status': 'up', 'macaddr': '00:0D:B9:00:00:01',
     'addr4': '192.0.2.1/24', 'vlan_tag': None},
    {'identifier': 'opt1', 'description': 'IoT', 'device': 'vlan01',
     'enabled': True, 'status': 'up', 'macaddr': '00:0d:b9:00:00:01',
     'addr4': '198.51.100.1/24', 'vlan_tag': '30'},
    {'identifier': 'opt2', 'description': 'Spare', 'device': 'igb3',
     'enabled': False, 'status': 'no carrier', 'addr4': ''},
    {'identifier': 'wan', 'description': 'WAN', 'device': 'igb0',
     'enabled': True, 'status': 'up', 'macaddr': '00:0d:b9:00:00:00',
     'addr4': '203.0.113.5/24', 'vlan_tag': None},
    {'identifier': 'lo0', 'description': 'Loopback', 'device': 'lo0',
     'enabled': True, 'status': 'up', 'addr4': '127.0.0.1/8'},
    {'identifier': 'opt3', 'description': 'Backup', 'device': 'em2',
     'enabled': True, 'status': 'no carrier', 'addr4': ''},
    {'identifier': '', 'description': 'Unassigned Interface',
     'device': 'pflog0', 'status': 'up', 'addr4': ''},
]}
ARP = [
    {'mac': 'aa:bb:cc:00:00:10', 'ip': '192.0.2.10', 'intf': 'igb1',
     'expired': False, 'permanent': False, 'type': 'ethernet',
     'manufacturer': 'Example Corp', 'hostname': 'nas',
     'intf_description': 'LAN'},
    {'mac': 'aa:bb:cc:00:00:20', 'ip': '198.51.100.20', 'intf': 'vlan01',
     'expired': False, 'manufacturer': '', 'hostname': '',
     'intf_description': 'IoT'},
    {'mac': 'aa:bb:cc:00:00:30', 'ip': '192.0.2.30', 'intf': 'igb1',
     'expired': True, 'manufacturer': 'Gone Inc', 'hostname': ''},
    {'mac': '(incomplete)', 'ip': '192.0.2.40', 'intf': 'igb1'},
    {'mac': 'aa:bb:cc:00:00:99', 'ip': '203.0.113.1', 'intf': 'igb0',
     'expired': False, 'manufacturer': 'ISP Router Co', 'hostname': ''},
]
DNSMASQ_LEASES = {'total': 1, 'rows': [
    {'address': '198.51.100.50', 'hwaddr': 'aa:bb:cc:00:00:50',
     'hostname': 'thermostat', 'if_descr': 'IoT'},
]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeFirewall:
    """Stands in for urllib.request.urlopen: answers /api/<endpoint> from
    self.responses (a dict, list, or an HTTP status code to fail with)."""

    def __init__(self):
        self.responses = {
            'diagnostics/interface/get_arp': ARP,
            'interfaces/overview/interfaces_info': INTERFACES,
        }
        self.requests = []
        self.error = None

    def __call__(self, request, context=None, timeout=None):
        self.requests.append(request)
        self.context = context
        if self.error:
            raise self.error
        path = urllib.parse.urlsplit(request.full_url).path
        endpoint = path.split('/api/', 1)[1]
        answer = self.responses.get(endpoint, 404)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(request.full_url, answer, 'error',
                                         {}, None)
        return FakeResponse(json.dumps(answer).encode())

    def endpoints(self):
        return [urllib.parse.urlsplit(r.full_url).path.split('/api/', 1)[1]
                for r in self.requests]


@pytest.fixture
def firewall(tmp_path, monkeypatch):
    vars.reset(str(tmp_path))
    (tmp_path / 'conf').mkdir()
    vars.config = {'plugins': {'OPNsense': {
        'enabled': 1, 'url': 'https://192.0.2.1/'}}}
    credentials.put('opnsense_api_key', KEY)
    credentials.put('opnsense_api_secret', SECRET)
    fake = FakeFirewall()
    monkeypatch.setattr(opnsense.urllib.request, 'urlopen', fake)
    return fake


def config():
    return vars.config['plugins']['OPNsense']


def run():
    opnsense.getPlugin().run()


def test_arp_entries_become_hosts(firewall):
    run()

    assert vars.hosts['192.0.2.10'] == {
        'ipaddress': '192.0.2.10', 'sources': ['OPNsense'],
        'mac': 'aa:bb:cc:00:00:10', 'vendor': 'Example Corp',
        'hostname': 'nas', 'subnet': '192.0.2.0/24', 'interface': 'LAN'}
    assert vars.hosts['198.51.100.20']['interface'] == 'IoT'
    assert vars.hosts['198.51.100.20']['subnet'] == '198.51.100.0/24'
    # expired and incomplete entries are left out
    assert '192.0.2.30' not in vars.hosts
    assert '192.0.2.40' not in vars.hosts


def test_the_firewall_is_a_router_on_each_interface(firewall):
    config()['hostname'] = 'firewall'

    run()

    for ip, name in (('192.0.2.1', 'LAN'), ('198.51.100.1', 'IoT')):
        assert vars.hosts[ip]['type'] == 'router'
        assert vars.hosts[ip]['hostname'] == 'firewall'
        assert vars.hosts[ip]['interface'] == name
        assert vars.hosts[ip]['mac'] == '00:0d:b9:00:00:01'


def test_host_overrides_still_win(firewall):
    class Manual(Plugin):
        pass
    Manual().addHost('192.0.2.10', source='manual', name='File server',
                     hostname='files', type='server')

    run()

    host = vars.hosts['192.0.2.10']
    assert host['sources'] == ['manual', 'OPNsense']
    assert host['hostname'] == 'files'
    assert host['type'] == 'server'
    assert host['mac'] == 'aa:bb:cc:00:00:10'   # filled in by OPNsense


def test_basic_auth_and_tls_verification_by_default(firewall):
    run()

    request = firewall.requests[0]
    expected = base64.b64encode('{0}:{1}'.format(KEY, SECRET).encode())
    assert request.get_header('Authorization') == \
        'Basic ' + expected.decode()
    assert request.full_url.startswith('https://192.0.2.1/api/')
    assert firewall.context.verify_mode == ssl.CERT_REQUIRED
    assert firewall.context.check_hostname


def test_verify_tls_off_is_warned(firewall, caplog):
    config()['verify_tls'] = 0

    with caplog.at_level(logging.WARNING):
        run()

    assert firewall.context.verify_mode == ssl.CERT_NONE
    assert 'verify_tls is off' in caplog.text


def test_missing_ca_file_is_an_error(firewall):
    config()['ca_file'] = 'firewall-ca.pem'

    with pytest.raises(opnsense.OPNsenseError, match='ca_file'):
        run()


def test_missing_credentials_say_how_to_store_them(firewall, tmp_path):
    (tmp_path / 'secrets' / 'opnsense_api_secret.enc').unlink()

    with pytest.raises(opnsense.OPNsenseError) as error:
        run()

    assert 'docker compose run --rm secrets set opnsense_api_secret' \
        in str(error.value)
    assert firewall.requests == []


def test_missing_url_is_an_error(firewall):
    del config()['url']

    with pytest.raises(opnsense.OPNsenseError, match='set "url"'):
        run()


def test_rejected_key(firewall, caplog):
    firewall.responses['interfaces/overview/interfaces_info'] = 401

    with caplog.at_level(logging.DEBUG), \
            pytest.raises(opnsense.OPNsenseError) as error:
        run()

    assert 'rejected the API key (401)' in str(error.value)
    for text in (str(error.value), caplog.text):
        assert KEY not in text and SECRET not in text


def test_missing_privilege_is_named(firewall):
    firewall.responses['diagnostics/interface/get_arp'] = 403

    with pytest.raises(opnsense.OPNsenseError) as error:
        run()

    assert 'privilege "Diagnostics: ARP Table"' in str(error.value)


def test_untrusted_certificate_points_at_ca_file(firewall):
    reason = ssl.SSLCertVerificationError('certificate verify failed')
    reason.verify_message = 'self-signed certificate'
    firewall.error = urllib.error.URLError(reason)

    with pytest.raises(opnsense.OPNsenseError) as error:
        run()

    assert 'self-signed certificate' in str(error.value)
    assert '"ca_file"' in str(error.value)


def test_unreachable_firewall(firewall):
    firewall.error = urllib.error.URLError(ConnectionRefusedError(
        'Connection refused'))

    with pytest.raises(opnsense.OPNsenseError,
                       match="can't reach https://192.0.2.1"):
        run()


def test_timeout(firewall):
    firewall.error = urllib.error.URLError(TimeoutError('timed out'))

    with pytest.raises(opnsense.OPNsenseError, match='no answer .* 15s'):
        run()


def test_no_interface_overview_still_reads_arp(firewall, caplog):
    del firewall.responses['interfaces/overview/interfaces_info']

    with caplog.at_level(logging.WARNING):
        run()

    assert vars.hosts['192.0.2.10']['mac'] == 'aa:bb:cc:00:00:10'
    assert 'subnet' not in vars.hosts['192.0.2.10']
    assert 'No interface overview' in caplog.text


def test_leases_are_off_by_default(firewall):
    run()

    assert not any('leases' in e for e in firewall.endpoints())


def test_leases_from_whichever_dhcp_server_answers(firewall, caplog):
    config()['leases'] = 1
    firewall.responses['dnsmasq/leases/search'] = DNSMASQ_LEASES
    firewall.responses['kea/leases4/search'] = 403

    with caplog.at_level(logging.WARNING):
        run()

    assert vars.hosts['198.51.100.50'] == {
        'ipaddress': '198.51.100.50', 'sources': ['OPNsense'],
        'mac': 'aa:bb:cc:00:00:50', 'hostname': 'thermostat',
        'subnet': '198.51.100.0/24', 'interface': 'IoT'}
    # the Kea privilege is only warned about, in case Kea is in use
    assert 'Services: DHCP: Kea(v4)' in caplog.text


def test_leases_warn_when_no_dhcp_server_answers(firewall, caplog):
    config()['leases'] = 1

    with caplog.at_level(logging.WARNING):
        run()

    assert 'no DHCP server on OPNsense answered' in caplog.text


def test_network_section(firewall):
    config()['network_section'] = {'title': 'Networks', 'seq_number': '040',
                                   'header': 'What the firewall routes'}

    run()

    section = vars.output['040-opnsense-networks']
    assert section['title'] == 'Networks'
    html = section['output'].render()
    assert 'What the firewall routes' in html
    assert '<td>IoT</td>' in html and '<td>30</td>' in html
    assert '198.51.100.0/24' in html and '<td>198.51.100.1</td>' in html
    assert 'Purpose' not in html   # no purposes configured
    assert 'Spare' not in html     # disabled interface
    assert 'Loopback' not in html
    assert 'Backup' not in html     # no network on it
    assert 'Unassigned' not in html


def test_network_purposes(firewall, caplog):
    config()['network_section'] = {'seq_number': '040', 'purposes': {
        'iot': 'Smart plugs and TVs', 'Guest': 'Visitors'}}

    with caplog.at_level(logging.WARNING):
        run()

    html = vars.output['040-opnsense-networks']['output'].render()
    assert '<th>Purpose</th>' in html
    assert '<td>Smart plugs and TVs</td>' in html
    assert "no interface named 'Guest'" in caplog.text


def test_disabled_does_nothing(firewall):
    config()['enabled'] = 0

    run()

    assert firewall.requests == []
    assert vars.hosts == {}


def test_loopback_is_left_out(firewall):
    run()

    assert '127.0.0.1' not in vars.hosts


def test_excluded_interfaces_are_left_out(firewall):
    config()['exclude_interfaces'] = ['wan']
    config()['network_section'] = {'title': 'Networks', 'seq_number': '040'}
    config()['leases'] = 1
    firewall.responses['dnsmasq/leases/search'] = {'rows': [
        {'address': '203.0.113.7', 'hwaddr': 'aa:bb:cc:00:00:77'}]}

    run()

    assert not any(ip.startswith('203.0.113.') for ip in vars.hosts)
    assert 'WAN' not in vars.output['040-opnsense-networks']['output'].render()
    assert '192.0.2.10' in vars.hosts


def test_all_interfaces_are_included_by_default(firewall):
    run()

    assert vars.hosts['203.0.113.5']['type'] == 'router'
    assert vars.hosts['203.0.113.1']['vendor'] == 'ISP Router Co'


def test_network_section_can_be_just_switched_on(firewall):
    config()['network_section'] = 1

    run()

    section = vars.output['150-opnsense-networks']
    assert section['title'] == 'Networks'
