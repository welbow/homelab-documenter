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


def reset(new_data_dir=os.curdir):
    """Clear the state plugins share, so one run can't leak into the next."""
    global data_dir, config, hosts, creds, output, skipped
    data_dir = new_data_dir
    config = {}
    hosts = {}
    creds = {}
    output = {}
    skipped = []
