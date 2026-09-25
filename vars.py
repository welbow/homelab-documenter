import os

data_dir = os.curdir
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
    global data_dir, config, hosts, creds, output, skipped, stamp
    data_dir = new_data_dir
    config = {}
    hosts = {}
    creds = {}
    output = {}
    skipped = []
    stamp = {}
