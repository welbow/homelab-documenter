import os

data_dir = os.curdir
# Where the page is generated: BUILD_DIR (a tmpfs in the container, so
# credentials never reach the disk), else build/ under data_dir
build_dir = os.path.join(os.curdir, 'build')
# The generated page, once HTMLOutput has written it
page = None
config = {}
# Hosts by IP address. Data plugins add to it with Plugin.addHost, which
# merges what several sources know about the same host.
hosts = {}
# Columns of the hosts table, in order; a column no host has data for is
# left out
hosts_keys = {
    # Friendly name, from the host overrides file
    'Name': 'name',
    'Hostname': 'hostname',
    'IP Address':  'ipaddress',
    # What kind of device (e.g. router, switch, VM); nmap can't tell, so
    # this fills in from other sources
    'Type': 'type',
    'Subnet': 'subnet',
    # Firewall interface or VLAN the host is on (OPNsense)
    'Interface': 'interface',
    'MAC Address': 'mac',
    'Vendor': 'vendor',
    'Seen by': 'sources',
    'Notes': 'notes'
}
creds = {}
creds_keys = {
    'Name': 'name',
    'Type': 'type',
    'Folder': 'folder',
    'Username': 'username',
    'Password': 'password',
    'Multi-Factor': 'mfa',
    'URL': 'url'
}
output = {}
# Plugins skipped at runtime (SKIP_PLUGINS / --skip): a run with any
# skipped plugin is incomplete
skipped = []
# When and from what this run was generated (see stamp.py)
stamp = {}

# Kept across runs (not cleared by reset): True while a preview may
# rebuild, so plugins can keep sessions (e.g. the unlocked vault) open
# between runs, registering in cleanups what to do when the preview ends
keep_alive = False
cleanups = []
# Sessions plugins keep open during a preview (e.g. {'bitwarden': token});
# here rather than in the plugin modules so a code reload keeps them
sessions = {}
# Each data plugin's results from its last run in this preview, for partial
# rebuilds (#25): {directory: {'output', 'creds', 'hosts', 'config',
# 'mtime'}}. Memory only: it can hold passwords.
plugin_cache = {}
# While a plugin runs during a preview: the addHost calls it makes
recording = None
# What the last run did: {'ran': [...], 'replayed': [...], 'notes': [...]}
last_run = {}


def section_keys():
    """The keys of output in packet order. Keys are "<seq_number>-<keyname>";
    they sort by seq_number as a number (so 5 comes before 10, and "005"
    and 5 are the same place), then by key. A seq_number that isn't a
    number sorts after all the numbered ones."""
    def order(key):
        seq = key.split('-', 1)[0]
        return (0, int(seq), key) if seq.isdigit() else (1, 0, key)
    return sorted(output, key=order)


def reset(new_data_dir=os.curdir):
    """Clear the state plugins share, so one run can't leak into the next."""
    global data_dir, build_dir, page, config, hosts, creds, output, skipped
    global stamp
    data_dir = new_data_dir
    build_dir = os.environ.get('BUILD_DIR', '').strip() or \
        os.path.join(data_dir, 'build')
    page = None
    config = {}
    hosts = {}
    creds = {}
    output = {}
    skipped = []
    stamp = {}
