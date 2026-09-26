import os

data_dir = os.curdir
# Where the page is generated: BUILD_DIR (a tmpfs in the container, so
# credentials never reach the disk), else build/ under data_dir
build_dir = os.path.join(os.curdir, 'build')
# The generated page, once HTMLOutput has written it
page = None
config = {}
hosts = {}
hosts_keys = {
    'Hostname': 'hostname',
    'IP Address':  'ipaddress'
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
