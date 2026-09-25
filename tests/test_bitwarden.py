import importlib
import logging

import pytest

import vars

bwmod = importlib.import_module('plugins.500-bitwarden-passwords')


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
