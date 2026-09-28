global logging
import logging
import base64
import ipaddress
import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from dominate.tags import *

import credentials
import vars
from Plugin import Plugin

# Read-only endpoints of the OPNsense REST API, with the privilege (as
# named in System > Access > Users) the API user needs for each
ARP = 'diagnostics/interface/get_arp'
INTERFACES = 'interfaces/overview/interfaces_info'
# The firewall's own name (hostname.domain) and version
SYSTEM = 'diagnostics/system/system_information'
# DHCPv4 leases, per DHCP server; whichever answers is used. (ISC DHCP,
# end of life and a plugin since 26.1, isn't read.)
LEASES = {
    'Kea': 'kea/leases4/search',
    'Dnsmasq': 'dnsmasq/leases/search',
}
PRIVILEGES = {
    ARP: 'Diagnostics: ARP Table',
    SYSTEM: 'Lobby: Dashboard',
    INTERFACES: 'Status: Interfaces',
    LEASES['Kea']: 'Services: DHCP: Kea(v4)',
    LEASES['Dnsmasq']: 'Services: Dnsmasq DNS/DHCP: Settings',
}

MAC = re.compile(r'^[0-9a-f]{2}(:[0-9a-f]{2}){5}$', re.IGNORECASE)


class OPNsenseError(RuntimeError):
    pass


class NotFound(OPNsenseError):
    """The endpoint doesn't exist on this firewall (older version, or the
    service isn't installed)."""


class Forbidden(OPNsenseError):
    """The API user lacks the privilege for the endpoint."""


class OPNsense (Plugin):
    """Hosts from an OPNsense firewall: its ARP table (every device it has
    talked to recently, on every interface and VLAN, with MAC address and
    vendor), its own interface addresses, and optionally its DHCP leases.
    Shown as "OPNsense" in the Seen by column."""
    expensive = True

    def __init__(self):
        super().__init__()

    def run(self):
        if not self.getConfig():
            return

        if not self._config.get('url'):
            raise OPNsenseError('OPNsense: set "url" (the firewall\'s web '
                                'address, e.g. https://192.0.2.1) in its '
                                'config.json section')
        self._url = self._config['url'].rstrip('/')
        key = credentials.get('opnsense_api_key')
        secret = credentials.get('opnsense_api_secret')
        missing = [name for name, value in (('opnsense_api_key', key),
                                            ('opnsense_api_secret', secret))
                   if not value]
        if missing:
            raise OPNsenseError(
                'OPNsense: credential {0} not set. Store it with: {1}'.format(
                    ' and '.join(missing),
                    '; '.join(credentials.set_command(name)
                              for name in missing)))
        # Basic auth header built here and passed only to urllib, so the
        # key and secret never reach a log line or an error message
        self._auth = 'Basic ' + base64.b64encode(
            '{0}:{1}'.format(key, secret).encode('utf-8')).decode('ascii')
        self._context = self._tls_context()

        self._logger.info('Reading {0}'.format(self._url))
        interfaces = self._interfaces()
        self._add_firewall(interfaces)
        count = self._add_arp(interfaces)
        if self._config.get('leases', 0) == 1:
            count += self._add_leases(interfaces)
        self._logger.info('Read {0} host entries from OPNsense'.format(count))

        if self._config.get('network_section'):
            self._add_network_section(interfaces)

    # --- HTTP ---------------------------------------------------------------

    def _tls_context(self):
        if self._config.get('verify_tls', 1) in (0, False):
            self._logger.warning('verify_tls is off: the firewall\'s TLS '
                                 'certificate is not checked')
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        ca_file = self._config.get('ca_file')
        if ca_file:
            path = os.path.join(vars.data_dir, 'conf', ca_file)
            if not os.path.exists(path):
                raise OPNsenseError('OPNsense: ca_file {0!r} not found (it '
                                    'is read from conf/ in the content '
                                    'repo)'.format(ca_file))
            return ssl.create_default_context(cafile=path)
        return ssl.create_default_context()

    def _get(self, endpoint, **params):
        url = '{0}/api/{1}'.format(self._url, endpoint)
        if params:
            url += '?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={
            'Authorization': self._auth, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(
                    request, context=self._context,
                    timeout=self._config.get('timeout', 15)) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise OPNsenseError(
                    'OPNsense rejected the API key (401): check the '
                    'opnsense_api_key and opnsense_api_secret credentials, '
                    'and that the API user is enabled') from None
            if e.code == 403:
                raise Forbidden(
                    'OPNsense refused {0} (403): give the API user the '
                    'privilege "{1}" (System > Access > Users)'.format(
                        endpoint, PRIVILEGES.get(endpoint, '?'))) from None
            if e.code == 404:
                raise NotFound('{0} not found (404)'.format(endpoint)) \
                    from None
            raise OPNsenseError('OPNsense: {0} failed: HTTP {1}'.format(
                endpoint, e.code)) from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                raise OPNsenseError(
                    'OPNsense: the TLS certificate of {0} was not trusted '
                    '({1}). Set "ca_file" to the CA that signed it (a file '
                    'in conf/), or "verify_tls": 0'.format(
                        self._url, e.reason.verify_message)) from None
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise self._timeout() from None
            raise OPNsenseError('OPNsense: can\'t reach {0}: {1}'.format(
                self._url, e.reason)) from None
        except (socket.timeout, TimeoutError):
            raise self._timeout() from None
        except ValueError:
            raise OPNsenseError('OPNsense: {0} did not return JSON; is '
                                '"url" the firewall\'s web address?'.format(
                                    endpoint)) from None

    def _timeout(self):
        return OPNsenseError('OPNsense: no answer from {0} within {1}s '
                             '(raise "timeout" if it\'s just slow)'.format(
                                 self._url, self._config.get('timeout', 15)))

    # --- data ---------------------------------------------------------------

    def _interfaces(self):
        """The firewall's assigned interfaces, by device name: {'igb1':
        {'name', 'address', 'subnet', 'dhcp', 'vlan', 'mac', 'status',
        'excluded'}}. Excluded ones (exclude_interfaces) stay in the list
        for the Networks section, but add no hosts. Empty (with a warning)
        if this OPNsense has no overview API."""
        self._excluded = {'devices': set(), 'subnets': []}
        try:
            rows = self._get(INTERFACES, current=1, rowCount=-1).get('rows', [])
        except NotFound:
            self._logger.warning('No interface overview on this OPNsense '
                                 '(24.1 or later has it); hosts get no '
                                 'subnet or interface')
            return {}
        exclude = {str(name).lower()
                   for name in self._config.get('exclude_interfaces', [])}
        interfaces = {}
        for row in rows:
            self._logger.debug('Interface {0}: {1}'.format(
                row.get('device'), {k: row.get(k) for k in (
                    'identifier', 'description', 'link_type', 'addr4',
                    'vlan_tag', 'enabled')}))
            # Devices without an identifier aren't assigned (not in use)
            if not row.get('device') or not row.get('identifier') or \
                    row.get('enabled') is False:
                continue
            address = subnet = ''
            addr4 = row.get('addr4') or ''
            if addr4:
                try:
                    iface = ipaddress.ip_interface(addr4)
                    address = str(iface.ip)
                    subnet = str(iface.network)
                except ValueError:
                    pass
            # The firewall's loopback isn't on the network
            if address and ipaddress.ip_address(address).is_loopback:
                continue
            names = {str(row.get(k) or '').lower()
                     for k in ('description', 'identifier', 'device')}
            excluded = bool(names & exclude)
            if excluded:
                # Its ARP entries and leases are left out too
                self._excluded['devices'].add(row['device'])
                if subnet:
                    self._excluded['subnets'].append(
                        ipaddress.ip_network(subnet))
            interfaces[row['device']] = {
                'name': row.get('description') or row.get('identifier') or
                row['device'],
                'address': address,
                'subnet': subnet,
                # Address from DHCP (e.g. a WAN): it changes, so the
                # Networks section says DHCP rather than today's lease
                'dhcp': row.get('link_type') == 'dhcp',
                'vlan': str(row.get('vlan_tag') or ''),
                'mac': row.get('macaddr') or '',
                'status': row.get('status') or '',
                'excluded': excluded,
            }
        return interfaces

    def _is_excluded(self, ip, device=None):
        return device in self._excluded['devices'] or any(
            ipaddress.ip_address(ip) in subnet
            for subnet in self._excluded['subnets'])

    def _firewall_name(self):
        """The firewall's hostname: "hostname" in config.json, else what
        OPNsense calls itself (hostname.domain), else '' with a warning."""
        if self._config.get('hostname'):
            return self._config['hostname']
        try:
            return self._get(SYSTEM).get('name') or ''
        except (Forbidden, NotFound) as e:
            self._logger.warning('{0}; the firewall\'s addresses get no '
                                 'hostname (or set "hostname" in its '
                                 'config.json section)'.format(e))
            return ''

    def _add_firewall(self, interfaces):
        addresses = [(device, iface) for device, iface in interfaces.items()
                     if iface['address'] and not iface['excluded']]
        if not addresses:
            return
        # On every one of its addresses; where reverse DNS (nmap) already
        # named an address, that name stays (the usual merge rule)
        name = self._firewall_name()
        for device, iface in addresses:
            self.addHost(iface['address'], source='OPNsense', type='router',
                         hostname=name,
                         mac=_mac(iface['mac']), subnet=iface['subnet'],
                         interface=iface['name'])

    def _add_arp(self, interfaces):
        count = 0
        for entry in self._get(ARP) or []:
            if entry.get('expired'):
                continue
            ip = _ip(entry.get('ip'))
            mac = _mac(entry.get('mac'))
            if not ip or not mac or self._is_excluded(ip, entry.get('intf')):
                continue
            iface = interfaces.get(entry.get('intf'), {})
            self.addHost(ip, source='OPNsense', mac=mac,
                         vendor=entry.get('manufacturer') or '',
                         hostname=entry.get('hostname') or '',
                         subnet=_subnet(ip, iface),
                         interface=iface.get('name') or
                         entry.get('intf_description') or '')
            count += 1
        return count

    def _add_leases(self, interfaces):
        by_subnet = {i['subnet']: i for i in interfaces.values()
                     if i['subnet'] and not i['excluded']}
        count = 0
        answered = False
        for server, endpoint in LEASES.items():
            try:
                rows = self._get(endpoint, current=1,
                                 rowCount=-1).get('rows', [])
            except NotFound:
                continue
            except Forbidden as e:
                # Only a problem if this is the DHCP server in use
                self._logger.warning(str(e))
                continue
            answered = True
            self._logger.debug('{0} DHCP: {1} lease(s)'.format(server,
                                                              len(rows)))
            for row in rows:
                ip = _ip(row.get('address'))
                if not ip or self._is_excluded(ip):
                    continue
                iface = next((i for s, i in by_subnet.items()
                              if ipaddress.ip_address(ip)
                              in ipaddress.ip_network(s)), {})
                self.addHost(ip, source='OPNsense',
                             mac=_mac(row.get('hwaddr') or row.get('mac')),
                             hostname=row.get('hostname') or '',
                             subnet=iface.get('subnet', ''),
                             interface=iface.get('name', ''))
                count += 1
        if not answered:
            self._logger.warning('"leases" is on, but no DHCP server on '
                                 'OPNsense answered')
        return count

    def _add_network_section(self, interfaces):
        """A table of the networks the firewall routes, with what each is
        for (network_section.purposes, by interface name)."""
        section = self._config['network_section']
        if not isinstance(section, dict):   # "network_section": 1
            section = {}
        purposes = {str(k).lower(): v
                    for k, v in section.get('purposes', {}).items()}
        known = {i['name'].lower() for i in interfaces.values()}
        for name in section.get('purposes', {}):
            if str(name).lower() not in known:
                self._logger.warning('network_section.purposes: no interface '
                                     'named {0!r}'.format(name))

        # What a network is for: config.json first, else what another
        # plugin knows about the subnet (e.g. a DHCP scope description)
        def purpose(device, iface):
            return purposes.get(iface['name'].lower()) or \
                vars.networks.get(iface['subnet'], {}).get('purpose', '')

        columns = [('Network', lambda d, i: i['name'])]
        if any(purpose(d, i) for d, i in interfaces.items()):
            columns.append(('Purpose', purpose))
        columns += [('Subnet', lambda d, i: 'DHCP' if i['dhcp']
                     else i['subnet']),
                    ('Firewall address', lambda d, i: 'DHCP' if i['dhcp']
                     else i['address']),
                    ('VLAN', lambda d, i: i['vlan']),
                    ('Interface', lambda d, i: d)]

        with div() as d:
            if section.get('header'):
                p(section['header'])
            with table():
                with thead(), tr():
                    for title, _ in columns:
                        th(title)
                with tbody():
                    # Every assigned interface, excluded ones too (e.g. the
                    # WAN: which port the internet comes in on)
                    for device, iface in sorted(
                            interfaces.items(),
                            key=lambda item: item[1]['name'].lower()):
                        with tr():
                            for _, value in columns:
                                td(value(device, iface))
        self.addOutput(d, title=section.get('title', 'Networks'),
                       seq=section.get('seq_number'),
                       keyname='opnsense-networks')


def _ip(value):
    try:
        return str(ipaddress.ip_address((value or '').strip()))
    except ValueError:
        return ''


def _mac(value):
    value = (value or '').strip().lower()
    return value if MAC.match(value) else ''


def _subnet(ip, iface):
    if iface.get('subnet') and \
            ipaddress.ip_address(ip) in ipaddress.ip_network(iface['subnet']):
        return iface['subnet']
    return ''


def getPlugin():
    return OPNsense()
