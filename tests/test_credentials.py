import io
import json
import logging
import os
import stat

import pytest

import credentials
import secrets_cli


def test_round_trip_and_first_use_creates_the_key(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        credentials.put('bw_master_password', 'Tëst pass 1')

    assert credentials.get('bw_master_password') == 'Tëst pass 1'
    assert 'Created a new instance key in' in caplog.text
    # nothing was stored before, so no "set them again" warning
    assert 'must be set again' not in caplog.text
    key = tmp_path / 'keys' / credentials.KEY_FILE
    assert key.exists()
    if os.name == 'posix':
        assert stat.S_IMODE(key.stat().st_mode) == 0o600


def test_file_holds_no_plaintext_and_differs_each_time(tmp_path):
    credentials.put('a', 'same value')
    first = (tmp_path / 'secrets' / 'a.enc').read_text()
    credentials.put('a', 'same value')
    second = (tmp_path / 'secrets' / 'a.enc').read_text()

    assert 'same value' not in first
    assert first != second
    assert json.loads(first)['version'] == 1


def test_unset_credential_is_none():
    assert credentials.get('nothing') is None


def test_other_install_key_is_a_clear_error(tmp_path, monkeypatch):
    credentials.put('bw_clientsecret', 'secret')
    monkeypatch.setenv('KEYS_DIR', str(tmp_path / 'other-keys'))
    credentials.put('unrelated', 'x')  # creates the "other" install's key

    with pytest.raises(RuntimeError, match='encrypted for a different key'):
        credentials.get('bw_clientsecret')


def test_new_key_warns_about_credentials_it_cannot_read(tmp_path,
                                                        monkeypatch, caplog):
    credentials.put('bw_clientid', 'x')
    monkeypatch.setenv('KEYS_DIR', str(tmp_path / 'reset'))

    with caplog.at_level(logging.WARNING):
        credentials.put('bw_clientsecret', 'y')

    assert 'Credentials stored for an earlier key (bw_clientid) must be ' \
        'set again' in caplog.text


def test_missing_key_is_a_clear_error(tmp_path, monkeypatch):
    credentials.put('bw_clientsecret', 'secret')
    monkeypatch.setenv('KEYS_DIR', str(tmp_path / 'empty'))

    with pytest.raises(RuntimeError, match='has no key'):
        credentials.get('bw_clientsecret')


def test_renamed_file_does_not_decrypt(tmp_path):
    credentials.put('first', 'secret')
    os.rename(tmp_path / 'secrets' / 'first.enc',
              tmp_path / 'secrets' / 'second.enc')

    with pytest.raises(RuntimeError, match='damaged or was renamed'):
        credentials.get('second')


@pytest.mark.parametrize('name', ['', 'Upper', '../x', 'a b', 'x' * 65])
def test_bad_names_are_refused(name):
    with pytest.raises(ValueError, match='Invalid credential name'):
        credentials.put(name, 'v')


def test_names_and_remove():
    credentials.put('b', '1')
    credentials.put('a', '2')

    assert credentials.names() == ['a', 'b']
    assert credentials.remove('a') is True
    assert credentials.remove('a') is False
    assert credentials.names() == ['b']


class Stdin:
    def __init__(self, data, tty=False):
        self.buffer = io.BytesIO(data)
        self._tty = tty

    def isatty(self):
        return self._tty


def test_cli_set_from_pipe_list_check_remove(monkeypatch, capsys):
    monkeypatch.setattr(secrets_cli.sys, 'stdin', Stdin(b'piped secret\r\n'))

    assert secrets_cli.main(['set', 'bw_clientid']) == 0
    assert secrets_cli.main(['list']) == 0
    assert secrets_cli.main(['check']) == 0
    out = capsys.readouterr().out

    assert credentials.get('bw_clientid') == 'piped secret'
    assert 'Stored bw_clientid in ' in out
    assert 'bw_clientid.enc' in out
    assert 'bw_clientid: ok' in out
    assert 'piped secret' not in out

    assert secrets_cli.main(['remove', 'bw_clientid']) == 0
    assert credentials.names() == []


def test_cli_prompt_needs_matching_entries(monkeypatch):
    monkeypatch.setattr(secrets_cli.sys, 'stdin', Stdin(b'', tty=True))
    answers = iter(['one', 'two'])
    monkeypatch.setattr(secrets_cli.getpass, 'getpass',
                        lambda prompt: next(answers))

    with pytest.raises(SystemExit):
        secrets_cli.main(['set', 'bw_master_password'])

    assert credentials.get('bw_master_password') is None


def test_cli_check_reports_undecryptable(tmp_path, monkeypatch, capsys):
    credentials.put('x', 'v')
    monkeypatch.setenv('KEYS_DIR', str(tmp_path / 'empty'))

    assert secrets_cli.main(['check']) == 1
    assert 'x: Credential' in capsys.readouterr().out
