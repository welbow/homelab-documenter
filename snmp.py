"""SNMP for plugins (#19): sessions (v2c or v3), credentials from the
encrypted store, and get/walk helpers on top of pysnmp. Vendor MIB logic
belongs in the plugins; this only reads.

A plugin reads its settings from its config.json section, optionally
overridden per device (e.g. one entry of a "switches" list):

  version        "2c" (default) or "3"
  port, timeout, retries
  v2c: community_secret   the credential holding the community
                          (default <prefix>_snmp_community)
  v3:  user, auth_protocol (SHA, SHA256, MD5), priv_protocol (AES, AES256,
       DES, none), auth_secret / priv_secret (default
       <prefix>_snmp_auth_password / <prefix>_snmp_priv_password)

v2c sends the community in clear text: use a read-only community,
restricted by ACL to the machine the engine runs on, ideally on a
management network."""
import asyncio

import credentials


class SNMPError(RuntimeError):
    pass


def settings(prefix, config, device):
    """This device's SNMP settings: its own entry, else the plugin's."""
    def pick(key, default=None):
        value = device.get(key)
        return value if value not in (None, '') else config.get(key, default)

    version = str(pick('version', '2c')).lower().lstrip('v')
    found = {
        'host': device.get('host'),
        'version': version,
        'port': int(pick('port', 161)),
        'timeout': float(pick('timeout', 5)),
        'retries': int(pick('retries', 1)),
    }
    if version in ('2c', '2'):
        found['version'] = '2c'
        found['community_secret'] = pick('community_secret',
                                         prefix + '_snmp_community')
    elif version == '3':
        found['user'] = pick('user')
        if not found['user']:
            raise SNMPError('SNMP v3 for {0}: set "user"'.format(
                found['host']))
        found['auth_protocol'] = str(pick('auth_protocol', 'SHA')).upper()
        found['priv_protocol'] = str(pick('priv_protocol', 'AES')).upper()
        found['auth_secret'] = pick('auth_secret',
                                    prefix + '_snmp_auth_password')
        found['priv_secret'] = pick('priv_secret',
                                    prefix + '_snmp_priv_password')
    else:
        raise SNMPError('SNMP version {0!r} for {1}: use "2c" or "3"'.format(
            version, found['host']))
    return found


def _secret(name):
    value = credentials.get(name)
    if not value:
        raise SNMPError('credential {0} not set. Store it with: {1}'.format(
            name, credentials.set_command(name)))
    return value


class Session:
    """A synchronous SNMP session to one device. walk() and get() return
    plain Python values: int, bytes (octet strings), str (IP addresses),
    tuple (OIDs)."""

    def __init__(self, found):
        self.host = found['host']
        self.found = found
        self._secrets = {}
        if found['version'] == '2c':
            self._secrets['community'] = _secret(found['community_secret'])
        else:
            self._secrets['auth'] = _secret(found['auth_secret'])
            if found['priv_protocol'] != 'NONE':
                self._secrets['priv'] = _secret(found['priv_secret'])
        self._loop = asyncio.new_event_loop()
        self._engine = None
        self._target = None

    def describe(self):
        return '{0} (SNMP v{1}, port {2})'.format(
            self.host, self.found['version'], self.found['port'])

    def close(self):
        if self._engine is not None:
            try:
                self._engine.close_dispatcher()
            except Exception:
                pass
        # pysnmp leaves timer tasks behind; finish them quietly
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- pysnmp plumbing ----------------------------------------------------

    def _setup(self):
        if self._engine is not None:
            return
        from pysnmp.hlapi.v3arch import asyncio as hl
        self._hl = hl
        self._engine = hl.SnmpEngine()
        self._target = self._loop.run_until_complete(
            hl.UdpTransportTarget.create(
                (self.host, self.found['port']),
                timeout=self.found['timeout'],
                retries=self.found['retries']))

    def _auth(self, community_suffix):
        hl = self._hl
        if self.found['version'] == '2c':
            return hl.CommunityData(
                self._secrets['community'] + (community_suffix or ''),
                mpModel=1)
        auth = {'SHA': hl.usmHMACSHAAuthProtocol,
                'SHA256': hl.usmHMAC192SHA256AuthProtocol,
                'MD5': hl.usmHMACMD5AuthProtocol}
        priv = {'AES': hl.usmAesCfb128Protocol,
                'AES256': hl.usmAesCfb256Protocol,
                'DES': hl.usmDESPrivProtocol}
        found = self.found
        if found['auth_protocol'] not in auth:
            raise SNMPError('auth_protocol {0!r}: use SHA, SHA256 or '
                            'MD5'.format(found['auth_protocol']))
        options = {'authKey': self._secrets['auth'],
                   'authProtocol': auth[found['auth_protocol']]}
        if found['priv_protocol'] != 'NONE':
            if found['priv_protocol'] not in priv:
                raise SNMPError('priv_protocol {0!r}: use AES, AES256, DES '
                                'or none'.format(found['priv_protocol']))
            options.update(privKey=self._secrets['priv'],
                           privProtocol=priv[found['priv_protocol']])
        return hl.UsmUserData(found['user'], **options)

    def _context(self, context_name):
        if self.found['version'] == '3' and context_name:
            return self._hl.ContextData(contextName=context_name)
        return self._hl.ContextData()

    def _fail(self, indication):
        text = str(indication)
        if 'timeout' in text.lower() or 'no snmp response' in text.lower():
            hint = ('check the address, that SNMP is on and allows this '
                    'machine, and the ' +
                    ('community' if self.found['version'] == '2c'
                     else 'user and passwords'))
            raise SNMPError('no answer from {0}: {1}'.format(
                self.describe(), hint))
        raise SNMPError('{0}: {1}'.format(self.describe(), text))

    @staticmethod
    def _value(value):
        from pysnmp.proto import rfc1902, rfc1905
        if isinstance(value, (rfc1905.NoSuchObject, rfc1905.NoSuchInstance,
                              rfc1905.EndOfMibView)):
            return None
        if isinstance(value, rfc1902.IpAddress):
            return '.'.join(str(b) for b in value.asOctets())
        if isinstance(value, rfc1902.OctetString):
            return bytes(value.asOctets())
        if isinstance(value, rfc1902.ObjectIdentifier):
            return tuple(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            return value.prettyPrint()

    # --- reading ------------------------------------------------------------

    def get(self, oid, community_suffix=None, context_name=None):
        """One value, or None if the device doesn't have it."""
        self._setup()
        hl = self._hl
        result = self._loop.run_until_complete(hl.get_cmd(
            self._engine, self._auth(community_suffix), self._target,
            self._context(context_name),
            hl.ObjectType(hl.ObjectIdentity(oid))))
        indication, status, _, binds = result
        if indication:
            self._fail(indication)
        if status or not binds:
            return None
        return self._value(binds[0][1])

    def walk(self, oid, community_suffix=None, context_name=None):
        """[(index, value)] under oid; index is the tuple of the OID's
        parts after oid. Empty if the device doesn't have it.
        community_suffix (v2c) and context_name (v3) select another context,
        e.g. Cisco's per-VLAN bridge tables ("@10" / "vlan-10")."""
        self._setup()
        hl = self._hl
        prefix = tuple(int(p) for p in oid.strip('.').split('.'))

        async def collect():
            found = []
            async for indication, status, _, binds in hl.bulk_walk_cmd(
                    self._engine, self._auth(community_suffix), self._target,
                    self._context(context_name), 0, 25,
                    hl.ObjectType(hl.ObjectIdentity(oid)),
                    lexicographicMode=False):
                if indication:
                    self._fail(indication)
                if status:
                    break
                for name, value in binds:
                    name = tuple(name)
                    if name[:len(prefix)] != prefix:
                        return found
                    value = self._value(value)
                    if value is not None:
                        found.append((name[len(prefix):], value))
            return found

        return self._loop.run_until_complete(collect())


def session(prefix, config, device):
    """A Session for one device, from the plugin's config and the device's
    entry. Raises SNMPError if a credential is missing or the settings are
    wrong."""
    return Session(settings(prefix, config, device))


# --- value helpers ------------------------------------------------------------

def text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace').strip('\x00').strip()
    return '' if value is None else str(value)


def mac(value):
    if isinstance(value, bytes) and len(value) == 6:
        return ':'.join('{0:02x}'.format(b) for b in value)
    return ''


def index_mac(index):
    """A MAC address at the end of a table index (e.g. dot1dTpFdbTable)."""
    return ':'.join('{0:02x}'.format(b) for b in index[-6:])
