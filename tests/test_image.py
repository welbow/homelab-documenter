"""Smoke tests for the external tools baked into the Docker image."""
import os
import subprocess

import pytest

in_image = pytest.mark.skipif(not os.path.isdir('/app/bin'),
                              reason='only meaningful inside the Docker image')


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


@in_image
def test_nmap_runs():
    result = run('nmap', '--version')

    assert result.returncode == 0, result.stderr


@in_image
def test_bw_runs():
    result = run('/app/bin/bw', '--version')

    assert result.returncode == 0, result.stderr
