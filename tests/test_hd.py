"""The hd wrappers (#29): hd.cmd (Windows) and hd (Linux/macOS) must run
the same docker compose commands, on services that exist."""
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(ROOT, name), encoding='utf-8', newline='') as f:
        return f.read()


def commands(text):
    """{service: options} of every `docker compose run --rm ...` line."""
    found = {}
    for options, service in re.findall(
            r'docker compose run --rm((?: -[-\w]+)*) (\w+)', text):
        found.setdefault(service, set()).add(options.strip())
    return found


def services():
    compose = read('docker-compose.yml')
    block = compose.split('\nservices:\n', 1)[1]
    return set(re.findall(r'^  (\w+):', block, re.M))


def test_both_wrappers_run_the_same_commands():
    sh = commands(read('hd'))
    cmd = commands(read('hd.cmd'))

    assert set(sh) == set(cmd) == {'preview', 'build', 'secrets', 'test'}
    for service in cmd:
        # hd adds -T when a value is piped in; hd.cmd can't tell
        assert cmd[service] <= sh[service]
    assert sh['preview'] == cmd['preview'] == {'--service-ports'}
    assert sh['secrets'] == {'', '-T'}


def test_wrappers_use_services_that_exist():
    for name in ('hd', 'hd.cmd'):
        text = read(name)
        used = set(commands(text)) | set(
            re.findall(r'refresh (\w+)', text))
        assert used <= services(), name


def test_wrappers_rebuild_quietly_first():
    assert 'docker compose build -q "$1"' in read('hd')
    assert 'docker compose build -q %1' in read('hd.cmd')


def test_line_endings():
    assert '\r\n' not in read('hd')                # sh
    cmd = read('hd.cmd')                          # labels need CRLF
    assert cmd.count('\r\n') == cmd.count('\n')


@pytest.mark.skipif(shutil.which('sh') is None, reason='no sh')
def test_sh_wrapper_syntax_and_help():
    subprocess.run(['sh', '-n', os.path.join(ROOT, 'hd')], check=True)
    result = subprocess.run(['sh', os.path.join(ROOT, 'hd'), 'help'],
                            capture_output=True, text=True, check=True)
    assert 'hd preview' in result.stdout or './hd <command>' in result.stdout
    bad = subprocess.run(['sh', os.path.join(ROOT, 'hd'), 'nonsense'],
                         capture_output=True, text=True)
    assert bad.returncode == 1 and 'Unknown command' in bad.stderr


def test_secret_and_secrets_are_the_same_command():
    """Both spellings are intended: the service is "secrets", and either
    is natural to type."""
    assert 'secret|secrets)' in read('hd')
    cmd = read('hd.cmd')
    assert 'if /i "%command%"=="secret" goto secret' in cmd
    assert 'if /i "%command%"=="secrets" goto secret' in cmd
    for name in ('hd', 'hd.cmd'):
        assert 'secrets works too' in read(name)


def test_docker_desktop_noise_is_dropped_from_the_rebuild():
    assert "grep -v 'error reading preface from client'" in read('hd')
    assert 'findstr /v /c:"error reading preface from client"' in \
        read('hd.cmd')


@pytest.mark.skipif(shutil.which('sh') is None, reason='no sh')
def test_sh_wrapper_accepts_both_spellings(tmp_path):
    """With a stand-in docker on the PATH, both spellings run the secrets
    service."""
    fake = tmp_path / 'docker'
    fake.write_text('#!/bin/sh\necho "docker $*"\n')
    fake.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep +
               os.environ.get('PATH', ''))
    for spelling in ('secret', 'secrets'):
        result = subprocess.run(['sh', os.path.join(ROOT, 'hd'), spelling,
                                 'list'], capture_output=True, text=True,
                                env=env, stdin=subprocess.DEVNULL)
        assert result.returncode == 0, result.stderr
        assert 'docker compose run --rm -T secrets list' in result.stdout
