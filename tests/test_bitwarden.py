import importlib
import json
import logging
import os
import subprocess
import traceback

import pytest

import vars

bwmod = importlib.import_module('plugins.500-bitwarden-passwords')

SERVER = 'https://bw.example.invalid'


class FakeBw:
    """Stands in for the bw CLI (subprocess.run): records each command and
    the BW_SESSION it saw, and answers from a small script."""

    def __init__(self, status='unauthenticated', server=SERVER, items=(),
                 folders=({'id': None, 'name': 'No Folder'},), fail=None):
        self.calls = []
        self.status = status
        self.server = server
        self.items = list(items)
        self.folders = list(folders)
        self.fail = fail or {}

    def __call__(self, cmd, env=None, stderr=None, **kwargs):
        args = tuple(cmd[1:])
        self.calls.append((args, (env or {}).get('BW_SESSION'),
                           stderr is None))
        name = args[0]
        if name in self.fail:
            return subprocess.CompletedProcess(cmd, 1, '', self.fail[name])
        out = ''
        if name == 'status':
            out = json.dumps({'status': self.status,
                              'serverUrl': self.server})
        elif name == 'unlock':
            out = 'SESSION123\n'
        elif args[:2] == ('list', 'folders'):
            out = json.dumps(self.folders)
        elif args[:2] == ('list', 'items'):
            out = json.dumps(self.items)
        return subprocess.CompletedProcess(cmd, 0, out, '')

    def commands(self):
        return [' '.join(args) for args, _, _ in self.calls]


@pytest.fixture
def bw_plugin(monkeypatch, tmp_path):
    """The Bitwarden plugin, enabled, with the `bw` CLI stubbed out so a
    test fails if the plugin gets as far as calling it."""
    vars.config = {'plugins': {'BitwardenPasswords': {
        'enabled': 1, 'server_url': SERVER, 'queries': []}}}
    monkeypatch.setattr(
        bwmod.subprocess, 'run',
        lambda *a, **k: pytest.fail('bw CLI must not be called: {0}'.format(a)))
    monkeypatch.setattr(bwmod, 'BW_DATA_DIR', str(tmp_path / 'bw-data'))
    monkeypatch.setattr(bwmod, 'PASSWORD_SECRET', str(tmp_path / 'secret'))
    monkeypatch.setattr(bwmod.sys.stdin, 'isatty', lambda: True,
                        raising=False)
    vars.build_dir = str(tmp_path / 'build')
    for var in ('BW_CLIENTID', 'BW_CLIENTSECRET', 'BW_SESSION'):
        monkeypatch.delenv(var, raising=False)
    return bwmod.getPlugin()


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv('BW_CLIENTID', 'user.example')
    monkeypatch.setenv('BW_CLIENTSECRET', 'secret')


def fake(monkeypatch, **kwargs):
    bw = FakeBw(**kwargs)
    monkeypatch.setattr(bwmod.subprocess, 'run', bw)
    return bw


def test_missing_key_stops_the_run(bw_plugin):
    with pytest.raises(RuntimeError,
                       match='BW_CLIENTID, BW_CLIENTSECRET not set'):
        bw_plugin.run()


def test_names_only_the_missing_variable(bw_plugin, monkeypatch):
    monkeypatch.setenv('BW_CLIENTID', 'user.example')

    with pytest.raises(RuntimeError, match='^BW_CLIENTSECRET not set'):
        bw_plugin.run()


def test_key_left_in_config_is_ignored_with_warning(bw_plugin, caplog):
    vars.config['plugins']['BitwardenPasswords']['client_id'] = 'old'

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError):
        bw_plugin.run()

    assert 'client_id/client_secret in config.json are ignored' in caplog.text


def test_disabled_plugin_never_checks_the_key(bw_plugin):
    vars.config['plugins']['BitwardenPasswords']['enabled'] = 0

    bw_plugin.run()  # no RuntimeError, no bw call


def test_logged_out_logs_in_unlocks_queries_and_cleans_up(
        bw_plugin, with_key, monkeypatch, tmp_path):
    bw = fake(monkeypatch)
    (tmp_path / 'bw-data').mkdir()
    (tmp_path / 'bw-data' / 'data.json').write_text('{}')

    bw_plugin.run()

    assert bw.commands() == [
        'status', 'config server ' + SERVER, 'login --apikey',
        'unlock --raw', 'sync', 'list folders', 'list items',
        'lock', 'logout']
    # the master password prompt goes to the terminal
    assert bw.calls[3][2] is True
    # the session is passed in the environment only after unlocking
    assert [s for _, s, _ in bw.calls[4:7]] == ['SESSION123'] * 3
    assert not (tmp_path / 'bw-data').exists()
    assert os.environ['BW_CLIENTSECRET'] == ''


def test_locked_vault_unlocks_without_logging_in(bw_plugin, with_key,
                                                 monkeypatch):
    bw = fake(monkeypatch, status='locked')

    bw_plugin.run()

    assert 'login --apikey' not in bw.commands()
    assert bw.commands()[:2] == ['status', 'unlock --raw']


def test_stdin_password_unlocks_from_a_private_file_then_deletes_it(
        bw_plugin, with_key, monkeypatch, tmp_path, caplog):
    vars.bw_password = 'Tëst pass 1'
    seen = {}
    bw = FakeBw(status='locked')

    def run(cmd, **kwargs):
        if cmd[1] == 'unlock':
            path = cmd[cmd.index('--passwordfile') + 1]
            seen['path'] = path
            with open(path, encoding='utf-8') as f:
                seen['content'] = f.read()
        return bw(cmd, **kwargs)
    monkeypatch.setattr(bwmod.subprocess, 'run', run)

    with caplog.at_level(logging.DEBUG):
        bw_plugin.run()

    assert seen['content'] == 'Tëst pass 1'
    assert seen['path'].startswith(str(tmp_path / 'build'))
    assert not os.path.exists(seen['path'])
    assert vars.bw_password is None
    assert all(not interactive for _, _, interactive in bw.calls)
    assert 'Tëst pass 1' not in caplog.text
    assert all('Tëst pass 1' not in ' '.join(a) for a, _, _ in bw.calls)


def test_password_file_removed_even_if_unlock_fails(bw_plugin, with_key,
                                                    monkeypatch, tmp_path):
    vars.bw_password = 'wrong'
    fake(monkeypatch, status='locked', fail={'unlock': 'Invalid password'})

    with pytest.raises(RuntimeError, match='bw unlock failed: Invalid'):
        bw_plugin.run()

    assert os.listdir(tmp_path / 'build') == []


def test_docker_secret_unlocks_without_prompting(bw_plugin, with_key,
                                                 monkeypatch, tmp_path):
    (tmp_path / 'secret').write_text('master')
    bw = fake(monkeypatch, status='locked')

    bw_plugin.run()

    assert 'unlock --passwordfile {0} --raw'.format(tmp_path / 'secret')         in bw.commands()
    assert all(not interactive for _, _, interactive in bw.calls)


def test_stdin_password_wins_over_the_secret(bw_plugin, with_key,
                                             monkeypatch, tmp_path):
    (tmp_path / 'secret').write_text('master')
    vars.bw_password = 'piped'
    bw = fake(monkeypatch, status='locked')

    bw_plugin.run()

    unlock = [c for c in bw.commands() if c.startswith('unlock')][0]
    assert str(tmp_path / 'build') in unlock


def test_no_password_source_and_no_terminal_is_a_clear_error(
        bw_plugin, with_key, monkeypatch):
    monkeypatch.setattr(bwmod.sys.stdin, 'isatty', lambda: False,
                        raising=False)
    bw = fake(monkeypatch, status='locked')

    with pytest.raises(RuntimeError, match='no terminal to ask for the '
                                           'master password'):
        bw_plugin.run()

    assert bw.commands()[-2:] == ['lock', 'logout']


def test_unlocked_session_is_reused_and_left_open(bw_plugin, with_key,
                                                  monkeypatch, tmp_path):
    monkeypatch.setenv('BW_SESSION', 'DEVSESSION')
    bw = fake(monkeypatch, status='unlocked')
    (tmp_path / 'bw-data').mkdir()

    bw_plugin.run()

    assert bw.commands() == ['status', 'sync', 'list folders', 'list items']
    assert [s for _, s, _ in bw.calls[1:]] == ['DEVSESSION'] * 3
    assert (tmp_path / 'bw-data').exists()


def test_other_server_logs_out_first(bw_plugin, with_key, monkeypatch):
    bw = fake(monkeypatch, status='locked', server='https://vault.other')

    bw_plugin.run()

    assert bw.commands()[:4] == ['status', 'logout',
                                 'config server ' + SERVER, 'login --apikey']


def test_failure_still_logs_out_and_keeps_token_out_of_traceback(
        bw_plugin, with_key, monkeypatch, tmp_path):
    bw = fake(monkeypatch, fail={'sync': 'Vault error'})
    (tmp_path / 'bw-data').mkdir()

    with pytest.raises(RuntimeError, match='bw sync failed: Vault error') as e:
        bw_plugin.run()

    assert bw.commands()[-2:] == ['lock', 'logout']
    assert not (tmp_path / 'bw-data').exists()
    assert 'SESSION123' not in ''.join(traceback.format_exception(e.value))
    # never on the command line either
    assert all('SESSION123' not in ' '.join(args) for args, _, _ in bw.calls)


def test_logout_key_in_config_is_ignored_with_warning(bw_plugin, with_key,
                                                      monkeypatch, caplog):
    vars.config['plugins']['BitwardenPasswords']['logout'] = 0
    bw = fake(monkeypatch, status='locked')

    with caplog.at_level(logging.WARNING):
        bw_plugin.run()

    assert bw.commands()[-2:] == ['lock', 'logout']
    assert '"logout" in config.json is ignored' in caplog.text


def test_items_listed_with_types_and_folders(bw_plugin, with_key,
                                             monkeypatch):
    vars.config['plugins']['BitwardenPasswords']['queries'] = [
        {'title': 'All', 'seq_number': '600'},
        {'title': 'Home', 'seq_number': '610', 'include_folders': 'Home'}]
    fake(monkeypatch, status='locked',
         folders=[{'id': None, 'name': 'No Folder'},
                  {'id': 'f1', 'name': 'Home'}],
         items=[
             {'type': 5, 'name': 'router key', 'folderId': None},
             {'type': 99, 'name': 'future thing', 'folderId': 'gone'},
             {'type': 1, 'name': 'nas', 'folderId': 'f1',
              'login': {'username': 'admin', 'password': 'pw',
                        'uris': [{'uri': 'https://nas'}], 'totp': 'x'}},
         ])

    bw_plugin.run()

    assert [(c['name'], c['type'], c['folder'])
            for c in vars.creds['600-All']['items']] == [
        ('nas', 'Login', 'Home'),
        ('router key', 'SSH Key', 'No Folder'),
        # a folder id that no longer exists doesn't crash the run
        ('future thing', 'Unknown (99)', 'No Folder')]
    home = vars.creds['610-Home']['items']
    assert home == [{'folder': 'Home', 'type': 'Login', 'name': 'nas',
                     'url': 'https://nas', 'username': 'admin',
                     'password': 'pw', 'mfa': True}]
