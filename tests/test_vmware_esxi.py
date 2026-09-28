import copy
import importlib
from types import SimpleNamespace as NS

import pytest

import credentials
import vars

vmware = importlib.import_module('plugins.130-vmware-esxi')
port_map = importlib.import_module('plugins.800-port-map')

# What read_inventory returns for a small host (shape checked against
# VMware's vcsim simulator)
INVENTORY = {
    'address': 'esxi01.example.com',
    'autostart': True,
    'host': {
        'name': 'esxi01.example.com',
        'model': 'Dell Inc. PowerEdge R730',
        'version': 'VMware ESXi 8.0.2 build-22380479',
        'serial': 'ABC1234',
        'vmks': [{'name': 'vmk0', 'address': '192.0.2.20',
                  'subnet': '192.0.2.0/24', 'mac': '00:50:56:00:00:01',
                  'portgroup': 'Management Network', 'vlan': ''},
                 {'name': 'vmk1', 'address': '0.0.0.0', 'subnet': '',
                  'mac': '00:50:56:00:00:02', 'portgroup': 'vMotion',
                  'vlan': '30'}],
        'pnics': [{'name': 'vmnic0', 'mac': 'aa:bb:cc:00:0e:00',
                   'speed': '10G', 'vswitch': 'vSwitch0'},
                  {'name': 'vmnic1', 'mac': 'aa:bb:cc:00:0e:01',
                   'speed': '', 'vswitch': ''}],
        'datastores': [{'name': 'datastore1', 'type': 'VMFS',
                        'capacity': 3998614437888,
                        'free': 1319413953331}],
    },
    'vms': [
        {'name': 'fileserver', 'power': 'on', 'guest': 'Ubuntu Linux (64-bit)',
         'hostname': 'files', 'cpus': 4, 'memory_mb': 8192,
         'notes': 'Family photos live here',
         'disks': [{'capacity': 107374182400, 'datastore': 'datastore1'},
                   {'capacity': 2199023255552, 'datastore': 'datastore1'}],
         'nics': [{'mac': '00:50:56:aa:00:01', 'network': 'LAN',
                   'addresses': ['192.0.2.30']}],
         'autostart': 1, 'start_delay': 120},
        {'name': 'dns', 'power': 'on', 'guest': 'Debian GNU/Linux 12',
         'hostname': 'dns', 'cpus': 1, 'memory_mb': 1024, 'notes': '',
         'disks': [{'capacity': 17179869184, 'datastore': 'datastore1'}],
         'nics': [{'mac': '00:50:56:aa:00:02', 'network': 'LAN',
                   'addresses': ['192.0.2.53']}],
         'autostart': 'any', 'start_delay': 0},
        {'name': 'test-vm', 'power': 'off', 'guest': 'Windows 11',
         'hostname': '', 'cpus': 2, 'memory_mb': 4096, 'notes': '',
         'disks': [], 'nics': [{'mac': '00:50:56:aa:00:03',
                                'network': 'LAB', 'addresses': []}],
         'autostart': None, 'start_delay': 0},
    ],
}


@pytest.fixture
def esxi(tmp_path, monkeypatch):
    vars.reset(str(tmp_path))
    vars.config = {'plugins': {'VMwareESXi': {
        'enabled': 1, 'hosts': ['esxi01.example.com']}}}
    inventory = copy.deepcopy(INVENTORY)
    monkeypatch.setattr(vmware.VMwareESXi, '_read',
                        lambda self, entry: inventory)
    return inventory


def config():
    return vars.config['plugins']['VMwareESXi']


def run():
    vmware.getPlugin().run()


def test_host_is_a_hypervisor_device(esxi):
    run()

    host = vars.devices['esxi01']
    assert host['type'] == 'hypervisor'
    assert host['model'] == 'Dell Inc. PowerEdge R730'
    assert host['interfaces']['vmk0']['addresses'] == '192.0.2.20'
    assert host['interfaces']['vmnic0']['mac'] == 'aa:bb:cc:00:0e:00'
    assert host['interfaces']['vmnic1']['status'] == 'down'
    row = vars.hosts['192.0.2.20']
    assert (row['type'], row['device'], row['sources']) == \
        ('hypervisor', 'esxi01', ['VMwareESXi'])
    assert '0.0.0.0' not in vars.hosts          # an unset vmk address


def test_vms_feed_the_device_table(esxi):
    run()

    row = vars.hosts['192.0.2.30']
    assert (row['type'], row['name'], row['hostname'], row['mac']) == \
        ('VM', 'fileserver', 'files', '00:50:56:aa:00:01')
    assert row['connected_to'] == 'esxi01 · LAN'
    assert row['seen'] is True


def test_vm_section(esxi):
    run()

    html = vars.output['040-vmware-vms']['output'].render()
    assert '<h2>esxi01.example.com</h2>' in html
    assert 'https://esxi01.example.com/ui' in html
    assert 'Datastore datastore1 (VMFS): 1.2 TB free of 3.6 TB' in html
    rows = html.split('<tbody>')[1]
    # autostart order first, then the rest by name
    assert rows.index('fileserver') < rows.index('>dns<') < \
        rows.index('test-vm')
    assert '<td>#1, after 120s</td>' in html
    assert '<td>yes (any order)</td>' in html
    assert '<td>off</td>' in html                 # powered-off VM listed
    assert '<td>4 vCPU / 8.0 GB</td>' in html
    assert '<td>100 GB (datastore1), 2.0 TB (datastore1)</td>' in html
    assert '<td>Family photos live here</td>' in html


def test_autostart_turned_off_on_the_host(esxi):
    esxi['autostart'] = False

    run()

    html = vars.output['040-vmware-vms']['output'].render()
    assert 'Autostart is turned off on this host' in html
    assert '<td>#1, after 120s</td>' not in html


def test_autostart_unknown(esxi):
    esxi['autostart'] = None

    run()

    html = vars.output['040-vmware-vms']['output'].render()
    assert '<td>unknown</td>' in html


def test_section_title_and_place(esxi):
    config()['section'] = {'title': 'VMware Virtual Machines',
                           'seq_number': '035'}

    run()

    assert vars.output['035-vmware-vms']['title'] == \
        'VMware Virtual Machines'


def test_section_can_be_left_out(esxi):
    config()['section'] = 0

    run()

    assert vars.output == {}
    assert '192.0.2.30' in vars.hosts


def test_vmnic_on_a_switch_port(esxi):
    run()
    from Plugin import Plugin
    switch = Plugin()
    switch.addDevice('core-sw', type='switch')
    switch.addPort('core-sw', 'te1/0/5')
    switch.addPortMac('core-sw', 'te1/0/5', 'aa:bb:cc:00:0e:00', 1)

    port_map.getPlugin().run()

    assert vars.ports[('core-sw', 'te1/0/5')]['connected'] == \
        ['esxi01 vmnic0']
    assert vars.devices['esxi01']['interfaces']['vmnic0']['connected_to'] \
        == 'core-sw te1/0/5'


def test_missing_credentials(tmp_path):
    vars.reset(str(tmp_path))
    vars.config = {'plugins': {'VMwareESXi': {
        'enabled': 1, 'hosts': ['esxi01.example.com']}}}

    with pytest.raises(vmware.VMwareError,
                       match='hd secret set vmware_esxi_username'):
        run()


def test_credential_names_can_be_changed(tmp_path):
    vars.reset(str(tmp_path))
    credentials.put('esxi_user', 'x')
    vars.config = {'plugins': {'VMwareESXi': {
        'enabled': 1, 'username_secret': 'esxi_user',
        'hosts': ['esxi01.example.com']}}}

    with pytest.raises(vmware.VMwareError,
                       match='credential vmware_esxi_password not set'):
        run()


def test_size():
    assert vmware.size(3998614437888) == '3.6 TB'
    assert vmware.size(107374182400) == '100 GB'
    assert vmware.size(1024 ** 3) == '1.0 GB'


# --- read_inventory, with a fake vSphere object tree -------------------------

class FakeVim:
    class HostSystem:
        pass

    class VirtualMachine:
        pass

    class PropertyCollector:
        FilterSpec = ObjectSpec = PropertySpec = RetrieveOptions = \
            staticmethod(lambda *a, **k: NS(**k))

    class vm:
        class device:
            class VirtualDisk(NS):
                pass

            class VirtualEthernetCard(NS):
                pass


def fake_si(vm_props, autostart_config):
    vm_refs = [NS(_moId=moid) for moid in vm_props]
    system = NS(
        summary=NS(hardware=NS(vendor='Dell Inc.', model='PowerEdge R730',
                               otherIdentifyingInfo=[NS(
                                   identifierType=NS(key='ServiceTag'),
                                   identifierValue='ABC1234')]),
                   config=NS(name='esxi01')),
        config=NS(product=NS(fullName='VMware ESXi 8.0.2'), network=NS(
            dnsConfig=NS(hostName='esxi01'),
            portgroup=[NS(spec=NS(name='Management Network', vlanId=0))],
            vswitch=[NS(name='vSwitch0', pnic=['key-vmnic0'])],
            vnic=[NS(device='vmk0', portgroup='Management Network',
                     spec=NS(mac='00:50:56:00:00:01', ip=NS(
                         ipAddress='192.0.2.20',
                         subnetMask='255.255.255.0')))],
            pnic=[NS(key='key-vmnic0', device='vmnic0',
                     mac='AA:BB:CC:00:0E:00', linkSpeed=NS(speedMb=10000))])),
        datastore=[NS(summary=NS(name='datastore1', type='VMFS',
                                 capacity=100, freeSpace=40))],
        configManager=NS(autoStartManager=autostart_config),
        vm=vm_refs)

    class Collector:
        def RetrievePropertiesEx(self, specs, options):
            return NS(token=None, objects=[
                NS(obj=NS(_moId=moid), propSet=[
                    NS(name=k, val=v) for k, v in props.items()])
                for moid, props in vm_props.items()])

    class View:
        view = [system]

        def Destroy(self):
            pass

    content = NS(rootFolder=None, propertyCollector=Collector(),
                 viewManager=NS(CreateContainerView=lambda *a: View()))
    return NS(RetrieveContent=lambda: content, content=content)


def test_read_inventory():
    props = {'vm-1': {
        'name': 'fileserver', 'runtime.powerState': 'poweredOn',
        'config.guestFullName': 'Ubuntu', 'config.hardware.numCPU': 4,
        'config.hardware.memoryMB': 8192, 'config.annotation': ' Photos ',
        'guest.hostName': 'files',
        'config.hardware.device': [
            FakeVim.vm.device.VirtualDisk(
                capacityInKB=1048576,
                backing=NS(fileName='[datastore1] fs/fs.vmdk')),
            FakeVim.vm.device.VirtualEthernetCard(
                macAddress='00:50:56:AA:00:01',
                backing=NS(deviceName='LAN'))],
        'guest.net': [NS(macAddress='00:50:56:aa:00:01',
                         ipAddress=['192.0.2.30', 'fe80::1'])]}}
    autostart = NS(config=NS(defaults=NS(enabled=True), powerInfo=[
        NS(key=NS(_moId='vm-1'), startAction='powerOn', startOrder=1,
           startDelay=120)]))

    inventory = vmware.read_inventory(fake_si(props, autostart), FakeVim,
                                      'esxi01.example.com')

    host = inventory['host']
    assert (host['name'], host['model'], host['serial']) == \
        ('esxi01', 'Dell Inc. PowerEdge R730', 'ABC1234')
    assert host['vmks'][0]['subnet'] == '192.0.2.0/24'
    assert host['pnics'][0] == {'name': 'vmnic0', 'mac': 'aa:bb:cc:00:0e:00',
                                'speed': '10G', 'vswitch': 'vSwitch0'}
    vm = inventory['vms'][0]
    assert (vm['power'], vm['notes'], vm['autostart'], vm['start_delay']) \
        == ('on', 'Photos', 1, 120)
    assert vm['disks'] == [{'capacity': 1073741824,
                            'datastore': 'datastore1'}]
    assert vm['nics'] == [{'mac': '00:50:56:aa:00:01', 'network': 'LAN',
                           'addresses': ['192.0.2.30']}]   # no IPv6 LL
    assert inventory['autostart'] is True


def test_read_inventory_without_autostart_manager():
    class Broken:
        @property
        def config(self):
            raise RuntimeError('not implemented (e.g. a simulator)')

    inventory = vmware.read_inventory(fake_si({}, Broken()), FakeVim,
                                      'esxi01')

    assert inventory['autostart'] is None and inventory['vms'] == []
