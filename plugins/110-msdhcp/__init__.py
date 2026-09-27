global logging
import logging
import datetime
import ipaddress
import json
import os
import re

import credentials
import vars
from Plugin import Plugin

# The script that reads the DHCP server, run over WinRM ("mode": "winrm")
# or on the server by you ("mode": "file"); both give the same JSON
EXPORT_SCRIPT = os.path.join(os.path.dirname(__file__), 'msdhcp-export.ps1')
EXPORT_FILE = 'msdhcp-export.json'

# Lease states that mean the address is in use now
ACTIVE = ('Active', 'ActiveReservation')

MAC = re.compile(r'^[0-9a-f]{2}([-:][0-9a-f]{2}){5}$', re.IGNORECASE)


class MSDHCPError(RuntimeError):
    pass


class MSDHCP (Plugin):
    """Hosts from a Microsoft (Windows Server) DHCP server: active leases
    (IP, MAC address, the name the device gave) and reservations, with the
    scopes' names and descriptions for the networks. Read live over WinRM,
    or from a JSON export the bundled script writes on the server. Shown as
    "MSDHCP" in the Seen by column."""
    expensive = True

    def __init__(self):
        super().__init__()

    def run(self):
        if not self.getConfig():
            return

        mode = self._config.get('mode', 'winrm')
        if mode == 'winrm':
            data = self._read_winrm()
        elif mode == 'file':
            data = self._read_file()
        else:
            raise MSDHCPError('MSDHCP: "mode" must be "winrm" or "file", '
                              'not {0!r}'.format(mode))
        self._add(data)

    # --- reading ------------------------------------------------------------

    def _read_file(self):
        path = self.getInputFilePath(self._config.get('file', EXPORT_FILE))
        if not os.path.exists(path):
            raise MSDHCPError(
                'MSDHCP: no export at input/MSDHCP/{0}. Run '
                'msdhcp-export.ps1 on the DHCP server (see the plugin '
                'README)'.format(os.path.basename(path)))
        # utf-8-sig: Windows PowerShell 5 writes a byte-order mark
        with open(path, encoding='utf-8-sig') as f:
            try:
                data = json.load(f)
            except ValueError as e:
                raise MSDHCPError('MSDHCP: {0} is not valid JSON ({1})'.format(
                    os.path.basename(path), e)) from None
        self._check_age(data)
        return data

    def _check_age(self, data):
        max_age = self._config.get('max_age_days', 7)
        try:
            generated = datetime.datetime.fromisoformat(data['generated'])
        except (KeyError, TypeError, ValueError):
            self._logger.warning('The export has no valid "generated" time')
            return
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=datetime.timezone.utc)
        age = datetime.datetime.now(datetime.timezone.utc) - generated
        if max_age and age > datetime.timedelta(days=max_age):
            self._logger.warning(
                'The DHCP export is {0} days old (from {1}); is the '
                'scheduled export still running?'.format(
                    age.days, data['generated']))

    def _read_winrm(self):
        server = self._config.get('server')
        if not server:
            raise MSDHCPError('MSDHCP: set "server" (the DHCP server\'s name, '
                              'e.g. dc1.example.com) in its config.json '
                              'section')
        username = credentials.get('msdhcp_username')
        password = credentials.get('msdhcp_password')
        missing = [name for name, value in (('msdhcp_username', username),
                                            ('msdhcp_password', password))
                   if not value]
        if missing:
            raise MSDHCPError(
                'MSDHCP: credential {0} not set. Store it with: {1}'.format(
                    ' and '.join(missing),
                    '; '.join('docker compose run --rm secrets set ' + name
                              for name in missing)))
        try:
            import requests
            import winrm
            import winrm.exceptions
        except ImportError:
            raise MSDHCPError('MSDHCP: the image has no pywinrm; rebuild it '
                              '(docker compose build)') from None

        https = self._config.get('transport', 'ntlm') == 'https'
        port = self._config.get('port', 5986 if https else 5985)
        endpoint = '{0}://{1}:{2}/wsman'.format(
            'https' if https else 'http', server, port)
        timeout = int(self._config.get('timeout', 30))
        options = {
            'transport': 'ntlm',
            # NTLM encrypts the session itself when it isn't HTTPS
            'message_encryption': 'auto' if https else 'always',
            'operation_timeout_sec': timeout,
            'read_timeout_sec': timeout + 10,
        }
        if https:
            if self._config.get('verify_tls', 1) in (0, False):
                self._logger.warning('verify_tls is off: the server\'s TLS '
                                     'certificate is not checked')
                options['server_cert_validation'] = 'ignore'
            elif self._config.get('ca_file'):
                path = os.path.join(vars.data_dir, 'conf',
                                    self._config['ca_file'])
                if not os.path.exists(path):
                    raise MSDHCPError('MSDHCP: ca_file {0!r} not found (it '
                                      'is read from conf/ in the content '
                                      'repo)'.format(self._config['ca_file']))
                options['ca_trust_path'] = path

        with open(EXPORT_SCRIPT, encoding='utf-8') as f:
            # The help comment isn't needed on the wire
            script = re.sub(r'<#.*?#>', '', f.read(), flags=re.S).strip()

        self._logger.info('Reading DHCP from {0} over WinRM'.format(server))
        where = '{0} (port {1})'.format(server, port)
        try:
            session = winrm.Session(endpoint, auth=(username, password),
                                    **options)
            result = session.run_ps(script)
        except winrm.exceptions.InvalidCredentialsError:
            raise MSDHCPError(
                'MSDHCP: {0} rejected the login: check msdhcp_username '
                '(DOMAIN\\user or user@domain) and msdhcp_password, and that '
                'the account is in Remote Management Users'.format(
                    server)) from None
        except requests.exceptions.SSLError as e:
            raise MSDHCPError(
                'MSDHCP: the TLS certificate of {0} was not trusted ({1}). '
                'Set "ca_file" to the CA that signed it (a file in conf/), '
                'or "verify_tls": 0'.format(server, _first_line(e))) from None
        except (requests.exceptions.Timeout,
                winrm.exceptions.WinRMOperationTimeoutError):
            raise MSDHCPError('MSDHCP: no answer from {0} within {1}s (raise '
                              '"timeout" if it\'s just slow)'.format(
                                  where, timeout)) from None
        except requests.exceptions.ConnectionError as e:
            raise MSDHCPError(
                'MSDHCP: can\'t reach WinRM on {0}: {1}. Check "server", and '
                'that WinRM is on (Test-WSMan {2})'.format(
                    where, _first_line(e), server)) from None
        except winrm.exceptions.WinRMTransportError as e:
            raise MSDHCPError('MSDHCP: WinRM on {0} failed: {1}'.format(
                where, _first_line(e))) from None

        if result.status_code != 0:
            error = result.std_err.decode('utf-8', 'replace')
            # The DHCP cmdlets talk to the server through WMI, which only
            # lets a remote (WinRM) login in with "Remote Enable" on the
            # DHCP namespace; DHCP Users doesn't have it by default
            if re.search(r'CIM server\. Access (is )?denied', error,
                         re.IGNORECASE):
                raise MSDHCPError(
                    'MSDHCP: {0} denied WMI access to the DHCP namespace: '
                    'give the account (through a group of its own) "Enable '
                    'Account", "Execute Methods" and "Remote Enable" on '
                    'root/Microsoft/Windows/DHCP with grant-dhcp-wmi-access'
                    '.ps1 (see the plugin README)'.format(server))
            if re.search(r'access (is )?denied|PermissionDenied|WIN32 5\b',
                         error, re.IGNORECASE):
                raise MSDHCPError(
                    'MSDHCP: {0} denied reading DHCP: add the account to the '
                    'DHCP Users group (on a domain controller, the domain '
                    'group); group changes apply to new logins'.format(
                        server))
            raise MSDHCPError('MSDHCP: the export failed on {0}: {1}'.format(
                server, _first_line(error)))
        try:
            return json.loads(result.std_out.decode('utf-8-sig'))
        except ValueError:
            raise MSDHCPError('MSDHCP: {0} did not return JSON'.format(
                server)) from None

    # --- data ---------------------------------------------------------------

    def _add(self, data):
        wanted = {str(s) for s in self._config.get('scopes', [])}
        scopes = {}
        for scope in data.get('scopes') or []:
            scope_id = scope.get('ScopeId')
            if wanted and scope_id not in wanted:
                continue
            try:
                subnet = str(ipaddress.ip_network(
                    '{0}/{1}'.format(scope_id, scope.get('SubnetMask')),
                    strict=False))
            except ValueError:
                continue
            scopes[scope_id] = subnet
            self.addNetwork(subnet, source='MSDHCP',
                            name=scope.get('Name') or '',
                            purpose=scope.get('Description') or '')

        count = 0
        for lease in data.get('leases') or []:
            if lease.get('ScopeId') not in scopes or \
                    lease.get('AddressState') not in ACTIVE:
                continue
            ip = _ip(lease.get('IPAddress'))
            if not ip:
                continue
            self.addHost(ip, source='MSDHCP', mac=_mac(lease.get('ClientId')),
                         hostname=lease.get('HostName') or '',
                         subnet=scopes[lease['ScopeId']])
            count += 1

        notes = self._config.get('reservation_notes', 1) == 1
        for reservation in data.get('reservations') or []:
            if reservation.get('ScopeId') not in scopes:
                continue
            ip = _ip(reservation.get('IPAddress'))
            if not ip:
                continue
            note = ''
            if notes:
                note = ': '.join(['DHCP reservation'] + [' - '.join(
                    part for part in (reservation.get('Name'),
                                      reservation.get('Description'))
                    if part)]).rstrip(': ')
            self.addHost(ip, source='MSDHCP',
                         mac=_mac(reservation.get('ClientId')),
                         subnet=scopes[reservation['ScopeId']], notes=note)
            count += 1

        self._logger.info('Read {0} lease(s) and reservation(s) in {1} '
                          'scope(s)'.format(count, len(scopes)))


def _ip(value):
    try:
        return str(ipaddress.ip_address((value or '').strip()))
    except ValueError:
        return ''


def _mac(value):
    """A DHCP ClientId as a MAC address (aa:bb:cc:dd:ee:ff), or '' if it
    isn't one (a client can send any identifier)."""
    value = (value or '').strip().lower()
    return value.replace('-', ':') if MAC.match(value) else ''


def _first_line(error):
    text = str(error).strip()
    return text.splitlines()[0] if text else type(error).__name__


def getPlugin():
    return MSDHCP()
