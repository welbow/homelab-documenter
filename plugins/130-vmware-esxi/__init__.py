global logging
import logging
import ipaddress
import os
import re
import ssl

from dominate.tags import *

import credentials
import vars
from Plugin import Plugin, device_key

SECRETS = ('vmware_esxi_username', 'vmware_esxi_password')
POWER = {'poweredOn': 'on', 'poweredOff': 'off', 'suspended': 'suspended'}


class VMwareError(RuntimeError):
    pass


def usable(address):
    """An address worth a row in the device table: not unset (0.0.0.0),
    link-local or loopback."""
    try:
        ip = ipaddress.ip_address(address or '')
    except ValueError:
        return False
    return not (ip.is_unspecified or ip.is_link_local or ip.is_loopback)


def size(n_bytes):
    """Bytes as a short size: 931 GB, 3.6 TB."""
    n = float(n_bytes or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB', 'PB'):
        if n < 1000 or unit == 'PB':
            return ('{0:.0f} {1}' if n >= 100 or unit == 'B'
                    else '{0:.1f} {1}').format(n, unit)
        n /= 1024.0


class VMwareESXi (Plugin):
    """VMware ESXi hosts, read through the vSphere API on the host itself
    (no vCenter needed) as a read-only user (#11): each host as a device
    (type hypervisor) with its management interfaces (vmk) and physical
    NICs (vmnic, so the port map shows which switch port each is on), and
    each VM: power state, guest OS, addresses and MACs (VMware Tools),
    CPU/RAM, disks and datastores, network, autostart order and notes.
    VMs with addresses become rows in the device table (type VM). Adds the
    VMware Virtual Machines section. VMware only; Proxmox would be its own
    plugin. Shown as "VMwareESXi" in the Seen by column."""
    expensive = True

    def __init__(self):
        super().__init__()

    def run(self):
        if not self.getConfig():
            return
        entries = self._config.get('hosts') or []
        if not entries:
            self._logger.warning('No ESXi hosts listed in "hosts"')
            return
        inventories = []
        for entry in entries:
            if isinstance(entry, str):
                entry = {'host': entry}
            if not entry.get('host'):
                raise VMwareError('VMwareESXi: each host needs a "host"')
            inventory = self._read(entry)
            self._add(inventory)
            inventories.append(inventory)
        section = self._config.get('section', {})
        if section != 0:
            self._add_section(inventories,
                              section if isinstance(section, dict) else {})

    # --- reading --------------------------------------------------------------

    def _setting(self, entry, key, default=None):
        value = entry.get(key)
        return value if value not in (None, '') else \
            self._config.get(key, default)

    def _tls_context(self, entry):
        if self._setting(entry, 'verify_tls', 1) in (0, False):
            self._logger.warning('verify_tls is off: the TLS certificate of '
                                 '{0} is not checked'.format(entry['host']))
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        ca_file = self._setting(entry, 'ca_file')
        if ca_file:
            path = os.path.join(vars.data_dir, 'conf', ca_file)
            if not os.path.exists(path):
                raise VMwareError('VMwareESXi: ca_file {0!r} not found (it is '
                                  'read from conf/ in the content repo)'
                                  .format(ca_file))
            return ssl.create_default_context(cafile=path)
        return ssl.create_default_context()

    def _read(self, entry):
        names = [self._setting(entry, 'username_secret', SECRETS[0]),
                 self._setting(entry, 'password_secret', SECRETS[1])]
        values = [credentials.get(n) for n in names]
        missing = [n for n, v in zip(names, values) if not v]
        if missing:
            raise VMwareError(
                'VMwareESXi: credential {0} not set. Store it with: {1}'
                .format(' and '.join(missing), '; '.join(
                    credentials.set_command(n) for n in missing)))
        try:
            from pyVim.connect import SmartConnect, Disconnect
            from pyVmomi import vim
        except ImportError:
            raise VMwareError('VMwareESXi: the image has no pyVmomi; start '
                              'the preview with hd preview, which rebuilds '
                              'it') from None

        host = entry['host']
        port = int(self._setting(entry, 'port', 443))
        self._logger.info('Reading ESXi host {0}'.format(host))
        try:
            si = SmartConnect(host=host, port=port, user=values[0],
                              pwd=values[1],
                              sslContext=self._tls_context(entry),
                              httpConnectionTimeout=int(
                                  self._setting(entry, 'timeout', 30)))
        except vim.fault.InvalidLogin:
            raise VMwareError(
                'VMwareESXi: {0} rejected the login: check {1} and {2}'
                .format(host, *names)) from None
        except ssl.SSLCertVerificationError as e:
            raise VMwareError(
                'VMwareESXi: the TLS certificate of {0} was not trusted '
                '({1}). Set "ca_file" to it (a file in conf/), or '
                '"verify_tls": 0'.format(host, e.verify_message)) from None
        except (OSError, getattr(vim.fault, 'HostConnectFault', OSError)) as e:
            raise VMwareError('VMwareESXi: can\'t reach {0} (port {1}): {2}'
                              .format(host, port, e)) from None
        try:
            return read_inventory(si, vim, host)
        except vim.fault.NoPermission as e:
            raise VMwareError(
                'VMwareESXi: {0} refused {1}: give the user the Read-only '
                'role on the host (Host > Actions > Permissions)'.format(
                    host, getattr(e, 'privilegeId', 'a read'))) from None
        finally:
            Disconnect(si)

    # --- data -----------------------------------------------------------------

    def _add(self, inventory):
        host = inventory['host']
        device = device_key(host['name'] or inventory['address'])
        self.addDevice(device, source='VMwareESXi', type='hypervisor',
                       hostname=host['name'], model=host['model'],
                       version=host['version'], serial=host['serial'])
        for vmk in host['vmks']:
            self.addInterface(device, vmk['name'], source='VMwareESXi',
                              addresses=vmk['address'], subnet=vmk['subnet'],
                              mac=vmk['mac'], description=vmk['portgroup'],
                              vlan=vmk['vlan'])
            if usable(vmk['address']):
                self.addHost(vmk['address'], source='VMwareESXi',
                             device=device, type='hypervisor',
                             hostname=host['name'], mac=vmk['mac'],
                             subnet=vmk['subnet'])
        for nic in host['pnics']:
            self.addInterface(device, nic['name'], source='VMwareESXi',
                              mac=nic['mac'], speed=nic['speed'],
                              status='up' if nic['speed'] else 'down',
                              description=nic['vswitch'])
        for vm in inventory['vms']:
            where = '{0} · {1}'.format(device, ', '.join(
                sorted({n['network'] for n in vm['nics'] if n['network']}))
                ).rstrip(' ·')
            for nic in vm['nics']:
                for ip in nic['addresses']:
                    self.addHost(ip, source='VMwareESXi', type='VM',
                                 name=vm['name'],
                                 hostname=vm['hostname'], mac=nic['mac'],
                                 connected_to=where,
                                 seen=vm['power'] == 'on')
        self._logger.info('{0}: {1} VMs'.format(device, len(inventory['vms'])))

    def _add_section(self, inventories, section):
        with div() as d:
            if section.get('header'):
                p(section['header'])
            for inventory in inventories:
                self._host_summary(inventory)
                self._vm_table(inventory)
        self.addOutput(d, title=section.get('title',
                                            'VMware Virtual Machines'),
                       seq=section.get('seq_number', '040'),
                       keyname='vmware-vms')

    def _host_summary(self, inventory):
        host = inventory['host']
        name = host['name'] or inventory['address']
        h2(name)
        with ul():
            li('{0}; {1}'.format(host['model'] or 'Unknown model',
                                 host['version']))
            with li():
                span('Web interface: ')
                url = 'https://{0}/ui'.format(inventory['address'])
                a(url, href=url)
            if inventory['autostart'] is False:
                li('Autostart is turned off on this host: no VM starts by '
                   'itself after a power cut.')
            for ds in host['datastores']:
                li('Datastore {0} ({1}): {2} free of {3}'.format(
                    ds['name'], ds['type'], size(ds['free']),
                    size(ds['capacity'])))

    def _vm_table(self, inventory):
        def order(vm):
            start = vm['autostart']
            return (start is None, start if isinstance(start, int) else 9999,
                    vm['name'].lower())

        with table():
            with thead(), tr():
                for title in ('VM', 'Power', 'Autostart', 'Guest OS',
                              'Addresses', 'CPU / RAM', 'Disks', 'Network',
                              'Notes'):
                    th(title)
            with tbody():
                for vm in sorted(inventory['vms'], key=order):
                    with tr():
                        td(vm['name'])
                        td(vm['power'])
                        td(self._autostart(vm, inventory['autostart']))
                        td(vm['guest'])
                        td(', '.join(ip for n in vm['nics']
                                     for ip in n['addresses']))
                        td('{0} vCPU / {1}'.format(
                            vm['cpus'], size(vm['memory_mb'] * 1024 * 1024)))
                        td(', '.join('{0} ({1})'.format(
                            size(disk['capacity']), disk['datastore'])
                            for disk in vm['disks']))
                        td(', '.join(sorted({n['network'] for n in vm['nics']
                                             if n['network']})))
                        td(vm['notes'])

    @staticmethod
    def _autostart(vm, enabled):
        start = vm['autostart']
        if enabled is None:
            return 'unknown'
        if not enabled or start is None:
            return 'no'
        if start == 'any':
            return 'yes (any order)'
        text = '#{0}'.format(start)
        if vm['start_delay']:
            text += ', after {0}s'.format(vm['start_delay'])
        return text


VM_PROPERTIES = ('name', 'runtime.powerState', 'config.guestFullName',
                 'config.hardware.numCPU', 'config.hardware.memoryMB',
                 'config.hardware.device', 'config.annotation',
                 'guest.guestFullName', 'guest.hostName', 'guest.net')


def vm_properties(si, vim, vms):
    """{VM id: {property path: value}} for just the properties the plugin
    uses, in one call: faster than reading whole VM objects, and it skips
    fields some hosts send that the library can't parse."""
    if not vms:
        return {}
    collector = si.content.propertyCollector
    spec = vim.PropertyCollector.FilterSpec(
        objectSet=[vim.PropertyCollector.ObjectSpec(obj=vm) for vm in vms],
        propSet=[vim.PropertyCollector.PropertySpec(
            type=vim.VirtualMachine, pathSet=list(VM_PROPERTIES))])
    found = {}
    result = collector.RetrievePropertiesEx(
        [spec], vim.PropertyCollector.RetrieveOptions())
    while result:
        for obj in result.objects:
            found[obj.obj._moId] = {p.name: p.val for p in obj.propSet}
        if not result.token:
            break
        result = collector.ContinueRetrievePropertiesEx(result.token)
    return found


def read_inventory(si, vim, address):
    """Everything the plugin needs from one ESXi host, as plain data (so
    it's easy to test and to reason about)."""
    content = si.RetrieveContent()
    view = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.HostSystem], True)
    try:
        system = view.view[0]
    finally:
        view.Destroy()

    summary = system.summary
    hardware = summary.hardware
    config = system.config
    network = config.network
    serial = ''
    for info in getattr(hardware, 'otherIdentifyingInfo', None) or []:
        if info.identifierType.key in ('SerialNumberTag', 'ServiceTag'):
            serial = info.identifierValue
            break

    portgroups = {pg.spec.name: pg.spec for pg in network.portgroup or []}
    vswitch_of = {}
    for vswitch in network.vswitch or []:
        for key in vswitch.pnic or []:
            vswitch_of[key] = vswitch.name

    vmks = []
    for vnic in network.vnic or []:
        ip = vnic.spec.ip
        subnet = ''
        if ip and ip.ipAddress and ip.subnetMask:
            subnet = str(ipaddress.ip_interface('{0}/{1}'.format(
                ip.ipAddress, ip.subnetMask)).network)
        spec = portgroups.get(vnic.portgroup)
        vmks.append({'name': vnic.device, 'address': ip.ipAddress if ip
                     else '', 'subnet': subnet,
                     'mac': (vnic.spec.mac or '').lower(),
                     'portgroup': vnic.portgroup or '',
                     'vlan': str(spec.vlanId) if spec and spec.vlanId
                     else ''})

    pnics = []
    for nic in network.pnic or []:
        speed = nic.linkSpeed.speedMb if nic.linkSpeed else 0
        pnics.append({'name': nic.device, 'mac': (nic.mac or '').lower(),
                      'speed': ('{0}G'.format(speed // 1000)
                                if speed >= 1000 else
                                '{0}M'.format(speed)) if speed else '',
                      'vswitch': vswitch_of.get(nic.key, '')})

    datastores = [{'name': ds.summary.name, 'type': ds.summary.type,
                   'capacity': ds.summary.capacity,
                   'free': ds.summary.freeSpace}
                  for ds in system.datastore or []]

    # Autostart: None if the host won't say (e.g. a simulator)
    try:
        autostart_config = system.configManager.autoStartManager.config
    except Exception:
        autostart_config = None
    autostart = None if autostart_config is None else         bool(autostart_config.defaults and autostart_config.defaults.enabled)
    power_info = {}
    for info in (autostart_config.powerInfo if autostart_config else None)             or []:
        if info.startAction == 'powerOn':
            power_info[info.key._moId] = (
                info.startOrder if info.startOrder and info.startOrder > 0
                else 'any',
                info.startDelay if info.startDelay and info.startDelay > 0
                else 0)

    vms = []
    for moid, props in vm_properties(si, vim, system.vm or []).items():
        disks, nics = [], []
        for device in props.get('config.hardware.device') or []:
            if isinstance(device, vim.vm.device.VirtualDisk):
                match = re.match(r'\[(.*?)\]', getattr(
                    device.backing, 'fileName', '') or '')
                disks.append({'capacity': (device.capacityInKB or 0) * 1024,
                              'datastore': match.group(1) if match else ''})
            elif isinstance(device, vim.vm.device.VirtualEthernetCard):
                nics.append({'mac': (device.macAddress or '').lower(),
                             'network': getattr(device.backing,
                                                'deviceName', '') or '',
                             'addresses': []})
        by_mac = {n['mac']: n for n in nics}
        for net in props.get('guest.net') or []:
            nic = by_mac.get((net.macAddress or '').lower())
            if nic is None:
                continue
            nic['addresses'] = [a for a in net.ipAddress or []
                                if ipaddress.ip_address(a).version == 4
                                and not ipaddress.ip_address(a).is_link_local]
        start = power_info.get(moid)
        power = str(props.get('runtime.powerState') or '')
        vms.append({
            'name': props.get('name', moid),
            'power': POWER.get(power, power),
            'guest': props.get('guest.guestFullName') or
            props.get('config.guestFullName') or '',
            'hostname': props.get('guest.hostName') or '',
            'cpus': props.get('config.hardware.numCPU') or 0,
            'memory_mb': props.get('config.hardware.memoryMB') or 0,
            'notes': (props.get('config.annotation') or '').strip(),
            'disks': disks, 'nics': nics,
            'autostart': start[0] if start else None,
            'start_delay': start[1] if start else 0,
        })

    product = config.product
    return {
        'address': address,
        'autostart': autostart,
        'host': {
            'name': config.network.dnsConfig.hostName
            if network.dnsConfig and network.dnsConfig.hostName
            else summary.config.name,
            'model': ' '.join(p for p in (hardware.vendor, hardware.model)
                              if p),
            'version': product.fullName if product else '',
            'serial': serial,
            'vmks': vmks, 'pnics': pnics, 'datastores': datastores,
        },
        'vms': vms,
    }


def getPlugin():
    return VMwareESXi()
