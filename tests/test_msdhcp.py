import importlib
import json
import logging
import sys
import types

import pytest
import requests

import credentials
import vars
from Plugin import Plugin

msdhcp = importlib.import_module('plugins.110-msdhcp')
opnsense = importlib.import_module('plugins.150-opnsense')

USERNAME = 'EXAMPLE\\svc-docs'
PASSWORD = 'test-password-CCCC'

# What msdhcp-export.ps1 returns (trimmed)
EXPORT = {
    'version': 1, 'server': 'dc1.example.com',
    'generated': '2026-09-25T23:00:00.0000000Z',
    'scopes': [
        {'ScopeId': '192.0.2.0', 'SubnetMask': '255.255.255.0',
         'Name': 'LAN', 'Description': 'Computers and servers',
         'State': 'Active'},
        {'ScopeId': '198.51.100.0', 'SubnetMask': '255.255.255.0',
         'Name': 'IoT', 'Description': '', 'State': 'Active'},
    ],
    'leases': [
        {'IPAddress': '192.0.2.50', 'ScopeId': '192.0.2.0',
         'ClientId': 'AA-BB-CC-00-00-50', 'HostName': 'laptop.example.com',
         'AddressState': 'Active'},
        {'IPAddress': '192.0.2.51', 'ScopeId': '192.0.2.0',
         'ClientId': 'aa-bb-cc-00-00-51', 'HostName': 'old-phone',
         'AddressState': 'Expired'},
        {'IPAddress': '198.51.100.20', 'ScopeId': '198.51.100.0',
         'ClientId': 'aa-bb-cc-00-00-20', 'HostName': None,
         'AddressState': 'ActiveReservation'},
        {'IPAddress': '198.51.100.21', 'ScopeId': '198.51.100.0',
         'ClientId': '01-02-03', 'HostName': 'odd-client',
         'AddressState': 'Active'},
    ],
    'reservations': [
        {'IPAddress': '198.51.100.20', 'ScopeId': '198.51.100.0',
         'ClientId': 'aa-bb-cc-00-00-20', 'Name': 'Printer',
         'Description': 'Upstairs office'},
        {'IPAddress': '192.0.2.30', 'ScopeId': '192.0.2.0',
         'ClientId': 'aa-bb-cc-00-00-30', 'Name': 'Camera',
         'Description': None},
    ],
}


@pytest.fixture
def content(tmp_path):
    vars.reset(str(tmp_path))
    (tmp_path / 'conf').mkdir()
    vars.config = {'plugins': {'MSDHCP': {'enabled': 1, 'mode': 'file'}}}
    folder = tmp_path / 'input' / 'MSDHCP'
    folder.mkdir(parents=True)
    return folder


def config():
    return vars.config['plugins']['MSDHCP']


def export_file(folder, data=EXPORT, bom=False):
    text = json.dumps(data)
    (folder / 'msdhcp-export.json').write_text(
        ('﻿' if bom else '') + text, encoding='utf-8')


def run():
    msdhcp.getPlugin().run()


# --- what it adds ------------------------------------------------------------

def test_active_leases_become_hosts(content):
    export_file(content, bom=True)   # Windows PowerShell writes a BOM

    run()

    assert vars.hosts['192.0.2.50'] == {
        'ipaddress': '192.0.2.50', 'sources': ['MSDHCP'],
        'mac': 'aa:bb:cc:00:00:50', 'hostname': 'laptop.example.com',
        'subnet': '192.0.2.0/24'}
    assert '192.0.2.51' not in vars.hosts            # expired
    # a client id that isn't a MAC address is left out, the lease isn't
    assert vars.hosts['198.51.100.21'].get('mac') is None


def test_reservations_with_notes(content):
    export_file(content)

    run()

    printer = vars.hosts['198.51.100.20']
    assert printer['notes'] == 'DHCP reservation: Printer - Upstairs office'
    assert printer['mac'] == 'aa:bb:cc:00:00:20'
    # a reserved device shows up even when it's offline (no lease)
    assert vars.hosts['192.0.2.30']['notes'] == 'DHCP reservation: Camera'


def test_reservation_notes_can_be_turned_off(content):
    export_file(content)
    config()['reservation_notes'] = 0

    run()

    assert 'notes' not in vars.hosts['198.51.100.20']


def test_scopes_filter(content):
    export_file(content)
    config()['scopes'] = ['198.51.100.0']

    run()

    assert all(ip.startswith('198.51.100.') for ip in vars.hosts)
    assert list(vars.networks) == ['198.51.100.0/24']


def test_scopes_become_networks(content):
    export_file(content)

    run()

    assert vars.networks['192.0.2.0/24'] == {
        'subnet': '192.0.2.0/24', 'sources': ['MSDHCP'], 'name': 'LAN',
        'purpose': 'Computers and servers'}
    assert 'purpose' not in vars.networks['198.51.100.0/24']


def test_host_overrides_still_win(content):
    export_file(content)

    class Manual(Plugin):
        pass
    Manual().addHost('198.51.100.20', source='manual', name='Printer',
                     notes='Refill toner in the hall cupboard')

    run()

    host = vars.hosts['198.51.100.20']
    assert host['sources'] == ['manual', 'MSDHCP']
    assert host['notes'] == 'Refill toner in the hall cupboard'


def test_scope_descriptions_fill_the_opnsense_purpose(content, monkeypatch):
    """A DHCP scope's description is the network's purpose in the OPNsense
    Networks section, unless config.json gives one."""
    export_file(content)
    run()

    vars.config['plugins']['OPNsense'] = {
        'enabled': 1, 'url': 'https://192.0.2.1', 'network_section': {
            'seq_number': '040', 'purposes': {}}}
    credentials.put('opnsense_api_key', 'k')
    credentials.put('opnsense_api_secret', 's')
    responses = {
        'interfaces/overview/interfaces_info': {'rows': [
            {'identifier': 'lan', 'description': 'LAN', 'device': 'igb1',
             'enabled': True, 'addr4': '192.0.2.1/24'},
            {'identifier': 'opt1', 'description': 'IoT', 'device': 'igb2',
             'enabled': True, 'addr4': '198.51.100.1/24'}]},
        'diagnostics/interface/get_arp': [],
    }

    class Response:
        def __init__(self, body):
            self.body = json.dumps(body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return self.body

    def urlopen(request, context=None, timeout=None):
        endpoint = request.full_url.split('/api/', 1)[1].split('?')[0]
        return Response(responses[endpoint])
    monkeypatch.setattr(opnsense.urllib.request, 'urlopen', urlopen)

    opnsense.getPlugin().run()

    html = vars.output['040-opnsense-networks']['output'].render()
    assert '<th>Purpose</th>' in html
    assert '<td>Computers and servers</td>' in html

    # config.json wins
    vars.output.clear()
    vars.config['plugins']['OPNsense']['network_section']['purposes'] = {
        'LAN': 'Family computers'}
    opnsense.getPlugin().run()
    html = vars.output['040-opnsense-networks']['output'].render()
    assert 'Family computers' in html and 'Computers and servers' not in html


# --- file mode ---------------------------------------------------------------

def test_missing_export_says_how_to_make_one(content):
    with pytest.raises(msdhcp.MSDHCPError, match='msdhcp-export.ps1'):
        run()


def test_bad_json(content):
    (content / 'msdhcp-export.json').write_text('{not json')

    with pytest.raises(msdhcp.MSDHCPError, match='not valid JSON'):
        run()


def test_old_export_is_warned(content, caplog):
    export_file(content, dict(EXPORT, generated='2020-01-01T00:00:00Z'))

    with caplog.at_level(logging.WARNING):
        run()

    assert 'days old' in caplog.text
    assert '192.0.2.50' in vars.hosts    # still used


def test_unknown_mode(content):
    config()['mode'] = 'ldap'

    with pytest.raises(msdhcp.MSDHCPError, match='"winrm" or "file"'):
        run()


# --- WinRM mode --------------------------------------------------------------

class FakeResult:
    def __init__(self, status_code=0, std_out=b'', std_err=b''):
        self.status_code = status_code
        self.std_out = std_out
        self.std_err = std_err


@pytest.fixture
def winrm(content, monkeypatch):
    """A fake pywinrm: Session records how it was made and what it ran,
    and answers with fake.result (or raises fake.error)."""
    import winrm.exceptions as exceptions
    fake = types.SimpleNamespace(
        result=FakeResult(std_out=json.dumps(EXPORT).encode()), error=None,
        sessions=[], exceptions=exceptions)

    class Session:
        def __init__(self, target, auth, **options):
            fake.sessions.append({'target': target, 'auth': auth,
                                  'options': options})

        def run_ps(self, script):
            fake.sessions[-1]['script'] = script
            if fake.error:
                raise fake.error
            return fake.result

    module = types.ModuleType('winrm')
    module.Session = Session
    module.exceptions = exceptions
    monkeypatch.setitem(sys.modules, 'winrm', module)
    monkeypatch.setitem(sys.modules, 'winrm.exceptions', exceptions)
    config().update({'mode': 'winrm', 'server': 'dc1.example.com'})
    credentials.put('msdhcp_username', USERNAME)
    credentials.put('msdhcp_password', PASSWORD)
    return fake


def test_winrm_runs_the_export_script(winrm):
    run()

    session = winrm.sessions[0]
    assert session['target'] == 'http://dc1.example.com:5985/wsman'
    assert session['auth'] == (USERNAME, PASSWORD)
    assert session['options']['transport'] == 'ntlm'
    assert session['options']['message_encryption'] == 'always'
    assert 'Get-DhcpServerv4Lease' in session['script']
    assert '.SYNOPSIS' not in session['script']   # help comment stripped
    assert vars.hosts['192.0.2.50']['hostname'] == 'laptop.example.com'


def test_winrm_over_https(winrm, content):
    config().update({'transport': 'https', 'verify_tls': 0})

    run()

    session = winrm.sessions[0]
    assert session['target'] == 'https://dc1.example.com:5986/wsman'
    assert session['options']['server_cert_validation'] == 'ignore'


def test_missing_credentials(winrm, tmp_path):
    (tmp_path / 'secrets' / 'msdhcp_password.enc').unlink()

    with pytest.raises(msdhcp.MSDHCPError,
                       match='secrets set msdhcp_password'):
        run()
    assert winrm.sessions == []


def test_missing_server(winrm):
    del config()['server']

    with pytest.raises(msdhcp.MSDHCPError, match='set "server"'):
        run()


def test_rejected_login(winrm, caplog):
    winrm.error = winrm.exceptions.InvalidCredentialsError('401')

    with caplog.at_level(logging.DEBUG), \
            pytest.raises(msdhcp.MSDHCPError) as error:
        run()

    assert 'rejected the login' in str(error.value)
    assert 'Remote Management Users' in str(error.value)
    for text in (str(error.value), caplog.text):
        assert PASSWORD not in text


def test_not_in_dhcp_users(winrm):
    winrm.result = FakeResult(status_code=1, std_err=(
        b'Get-DhcpServerv4Scope : Failed to enumerate scopes on DHCP server '
        b'DC1. Access is denied.'))

    with pytest.raises(msdhcp.MSDHCPError, match='DHCP Users'):
        run()


def test_other_script_error(winrm):
    winrm.result = FakeResult(status_code=1, std_err=(
        b'Get-DhcpServerv4Scope : The term is not recognized\r\nmore'))

    with pytest.raises(msdhcp.MSDHCPError,
                       match='export failed on dc1.example.com: '
                             'Get-DhcpServerv4Scope : The term'):
        run()


def test_winrm_not_listening(winrm):
    winrm.error = requests.exceptions.ConnectionError('Connection refused')

    with pytest.raises(msdhcp.MSDHCPError,
                       match="can't reach WinRM on dc1.example.com "
                             r"\(port 5985\).*Test-WSMan"):
        run()


def test_untrusted_certificate(winrm):
    config()['transport'] = 'https'
    winrm.error = requests.exceptions.SSLError('certificate verify failed')

    with pytest.raises(msdhcp.MSDHCPError, match='"ca_file"'):
        run()


def test_timeout(winrm):
    winrm.error = requests.exceptions.ReadTimeout('timed out')

    with pytest.raises(msdhcp.MSDHCPError, match='no answer .* 30s'):
        run()
