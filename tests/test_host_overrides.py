import importlib
import logging
import os

import pytest

import vars
from Plugin import Plugin

overrides = importlib.import_module('plugins.050-host-overrides')


@pytest.fixture
def overrides_file(tmp_path):
    vars.reset(str(tmp_path))
    vars.config = {'plugins': {'HostOverrides': {'enabled': 1}}}
    folder = tmp_path / 'input' / 'HostOverrides'
    folder.mkdir(parents=True)
    return folder / 'host-overrides.csv'


def test_rows_become_manual_hosts(overrides_file):
    overrides_file.write_text(
        '﻿ip,name,type,notes\n'  # Excel's byte-order mark
        '192.168.2.1,Router,router,"Internet gateway, don\'t unplug"\n'
        '192.168.2.20,Living room Roku,iot,\n', encoding='utf-8')

    overrides.getPlugin().run()

    assert vars.hosts['192.168.2.1'] == {
        'ipaddress': '192.168.2.1', 'sources': ['manual'], 'name': 'Router',
        'type': 'router', 'notes': "Internet gateway, don't unplug"}
    # type matching ignores case and uses the canonical spelling
    assert vars.hosts['192.168.2.20']['type'] == 'IoT'
    assert 'notes' not in vars.hosts['192.168.2.20']


def test_bad_ip_skipped_and_unknown_type_warned(overrides_file, caplog):
    overrides_file.write_text('ip,name,type,notes\n'
                           'router,Router,router,\n'
                           '192.168.2.11,Core switch,swtich,\n')

    with caplog.at_level(logging.WARNING):
        overrides.getPlugin().run()

    assert list(vars.hosts) == ['192.168.2.11']
    assert vars.hosts['192.168.2.11']['type'] == 'swtich'
    assert "Line 2: skipping, 'router' is not an IP address" in caplog.text
    assert "Line 3: unknown type 'swtich'" in caplog.text


def test_missing_file_adds_nothing(overrides_file):
    overrides.getPlugin().run()

    assert vars.hosts == {}


def test_manual_values_win_over_discovered(overrides_file):
    overrides_file.write_text('ip,name,type,notes\n192.168.2.1,Router,router,\n')

    overrides.getPlugin().run()
    Plugin().addHost('192.168.2.1', source='nmap', hostname='sphincter.lan',
                     type='server')

    host = vars.hosts['192.168.2.1']
    assert host['type'] == 'router'
    assert host['hostname'] == 'sphincter.lan'
    assert host['sources'] == ['manual', 'nmap']
