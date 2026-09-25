import logging

import pytest

import logconfig


@pytest.fixture(autouse=True)
def restore_root_level():
    root = logging.getLogger()
    level = root.level
    yield
    root.setLevel(level)


def test_default_level_is_info(content, monkeypatch):
    monkeypatch.delenv('LOG_LEVEL', raising=False)

    content.run()

    assert logging.getLogger().level == logging.INFO


def test_env_sets_level(content, monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', 'debug')

    content.run()

    assert logging.getLogger().level == logging.DEBUG


def test_config_log_level_used_without_env(content, monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', '')  # compose passes an empty value
    content.config['log_level'] = 'WARNING'

    content.run()

    assert logging.getLogger().level == logging.WARNING


def test_env_overrides_config(content, monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', 'ERROR')
    content.config['log_level'] = 'WARNING'

    content.run()

    assert logging.getLogger().level == logging.ERROR


def test_unknown_level_keeps_current_and_warns(caplog):
    logging.getLogger().setLevel(logging.DEBUG)

    assert logconfig.set_level('LOUD') is False

    assert logging.getLogger().level == logging.DEBUG
    assert 'Unknown log level' in caplog.text


def test_redact_masks_sensitive_keys_at_any_depth():
    config = {'plugins': {
        'BitwardenPasswords': {'enabled': 1, 'client_secret': 's3cret',
                               'server_url': 'https://vault.example'},
        'Other': {'items': [{'password': 'pw', 'name': 'router'}],
                  'API_KEY': 'k', 'client_id': 'user.x',
                  'session_token': 't'},
    }}

    redacted = logconfig.redact(config)

    bw = redacted['plugins']['BitwardenPasswords']
    other = redacted['plugins']['Other']
    assert bw == {'enabled': 1, 'client_secret': logconfig.MASK,
                  'server_url': 'https://vault.example'}
    assert other['items'] == [{'password': logconfig.MASK, 'name': 'router'}]
    assert other['API_KEY'] == other['client_id'] \
        == other['session_token'] == logconfig.MASK
    # the original is untouched
    assert config['plugins']['BitwardenPasswords']['client_secret'] == 's3cret'


def test_debug_run_logs_no_secret_values(content, monkeypatch, caplog):
    monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
    content.config['plugins']['StaticFile']['client_secret'] = 'LEAKME'

    with caplog.at_level(logging.DEBUG):
        content.run()

    assert 'config = ' in caplog.text
    assert 'LEAKME' not in caplog.text
