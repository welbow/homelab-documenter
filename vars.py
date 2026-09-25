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


def reset(new_data_dir=os.curdir):
    """Clear the state plugins share, so one run can't leak into the next."""
    global data_dir, config, hosts, creds, output
    data_dir = new_data_dir
    config = {}
    hosts = {}
    creds = {}
    output = {}
