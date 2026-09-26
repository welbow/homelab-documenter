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
    'Hostname': 'hostname',
    'IP Address':  'ipaddress',
    # What kind of device (e.g. router, switch, VM); nmap can't tell, so
    # this fills in from other sources
    'Type': 'type',
    'Subnet': 'subnet',
    'MAC Address': 'mac',
    'Vendor': 'vendor',
    'Seen by': 'sources'
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


def reset(new_data_dir=os.curdir):
    """Clear the state plugins share, so one run can't leak into the next."""
    global data_dir, build_dir, page, config, hosts, creds, output, skipped, stamp
    data_dir = new_data_dir
    build_dir = os.environ.get('BUILD_DIR', '').strip() or         os.path.join(data_dir, 'build')
    page = None
    config = {}
    hosts = {}
    creds = {}
    output = {}
    skipped = []
    stamp = {}
