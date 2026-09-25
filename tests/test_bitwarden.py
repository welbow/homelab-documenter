import importlib
import json
import logging
import subprocess
import traceback

import pytest

import vars

bwmod = importlib.import_module('plugins.500-bitwarden-passwords')
REAL_BW = bwmod.bwkr.bw


@pytest.fixture
def bw_plugin(monkeypatch):
    """The Bitwarden plugin, enabled, with the `bw` CLI stubbed out so a
    test fails if the plugin gets as far as calling it."""
    vars.config = {'plugins': {'BitwardenPasswords': {
        'enabled': 1, 'server_url': 'https://bw.example.invalid',
        'queries': []}}}
    monkeypatch.setattr(
        bwmod.bwkr, 'bw',
        lambda *a, **k: pytest.fail('bw CLI must not be called: {0}'.format(a)))
    monkeypatch.delenv('BW_CLIENTID', raising=False)
    monkeypatch.delenv('BW_CLIENTSECRET', raising=False)
    return bwmod.getPlugin()


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


def test_ssh_key_and_unknown_item_types_are_listed(bw_plugin, monkeypatch):
    vars.config['plugins']['BitwardenPasswords']['queries'] = [
        {'title': 'All', 'seq_number': '600'}]
    vars.config['plugins']['BitwardenPasswords']['logout'] = 0
    monkeypatch.setenv('BW_CLIENTID', 'user.example')
    monkeypatch.setenv('BW_CLIENTSECRET', 'secret')
    items = [
        {'type': 5, 'name': 'router key', 'folderId': None},
        {'type': 99, 'name': 'future thing', 'folderId': None},
    ]
    replies = {
        'status': '{"status": "locked"}',
        'folders': '[{"id": null, "name": "No Folder"}]',
        'items': json.dumps(items),
    }
    monkeypatch.setattr(bwmod.bwkr, 'bw',
                        lambda *a, **k: replies.get(a[-1], ''))
    monkeypatch.setattr(bwmod.bwkr, 'get_session', lambda env: 'session')

    bw_plugin.run()

    assert [(c['name'], c['type']) for c in vars.creds['600-All']['items']] \
        == [('router key', 'SSH Key'), ('future thing', 'Unknown (99)')]


def test_failed_bw_call_does_not_leak_session_token(bw_plugin, monkeypatch):
    monkeypatch.setenv('BW_CLIENTID', 'user.example')
    monkeypatch.setenv('BW_CLIENTSECRET', 'secret')
    monkeypatch.setattr(bwmod.bwkr, 'bw', REAL_BW)
    monkeypatch.setattr(bwmod.bwkr, 'get_session', lambda env: 'TOKEN123')

    def bw_run(*cmd):
        if '--session' in cmd:
            raise subprocess.CalledProcessError(1, cmd, output=b'Vault error')
        return subprocess.CompletedProcess(cmd, 0, stdout=b'{"status": "locked"}')
    monkeypatch.setattr(bwmod.bwkr, 'bw_run', bw_run)

    with pytest.raises(RuntimeError, match='bw sync failed: Vault error') as e:
        bw_plugin.run()

    assert 'TOKEN123' not in ''.join(
        traceback.format_exception(e.value))
