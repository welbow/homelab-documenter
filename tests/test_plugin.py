import logging

import vars
from Plugin import Plugin


class Dummy(Plugin):
    pass


# addOutput derives defaults from the plugin's module name, as it would for
# a real plugin living in plugins/123-dummy-thing/.
Dummy.__module__ = 'plugins.123-dummy-thing'


def test_addOutput_derives_seq_and_keyname_from_module():
    Dummy().addOutput('body')

    assert vars.output == {
        '123-dummy-thing': {'output': 'body', 'title': '123-dummy-thing'}}


def test_addOutput_overrides_and_extra_fields():
    Dummy().addOutput('body', title='Title', seq='007', keyname='k',
                      hide_surround=True)

    assert vars.output == {
        '007-k': {'output': 'body', 'title': 'Title', 'hide_surround': True}}


def test_init_does_not_read_config(caplog):
    vars.config = {'plugins': {}}

    with caplog.at_level(logging.WARNING):
        Dummy()

    assert caplog.records == []


def test_getConfig_without_plugin_section_is_false():
    vars.config = {'plugins': {}}

    assert Dummy().getConfig() is False


def test_getConfig_disabled_is_false():
    vars.config = {'plugins': {'Dummy': {'enabled': 0}}}

    assert Dummy().getConfig() is False


def test_getConfig_enabled_loads_plugin_config():
    vars.config = {'plugins': {'Dummy': {'enabled': 1, 'x': 42}}}
    plugin = Dummy()

    assert plugin.getConfig() is True
    assert plugin._config['x'] == 42


def test_getConfig_missing_enabled_is_disabled():
    vars.config = {'plugins': {'Dummy': {}}}

    assert Dummy().getConfig() is False
