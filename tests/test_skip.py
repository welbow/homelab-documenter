import logging

import pipeline
import vars


def names(plugins):
    return [type(p).__name__ for p in plugins]


def test_skip_list_merges_env_and_cli_entries(monkeypatch):
    monkeypatch.setenv('SKIP_PLUGINS', ' 500, 100 ,')

    assert pipeline.skip_list(['StaticFile', 'a,b']) \
        == ['500', '100', 'StaticFile', 'a', 'b']


def test_skip_by_number_directory_or_class_name(caplog):
    plugins = pipeline.discover_plugins()

    with caplog.at_level(logging.WARNING):
        kept = pipeline.select_plugins(
            plugins, ['500', '100-nmap-ping-scan', 'tableofcontents'])

    assert 'BitwardenPasswords' not in names(kept)
    assert 'NmapPingScan' not in names(kept)
    assert 'TableOfContents' not in names(kept)
    assert len(kept) == len(plugins) - 3
    assert vars.skipped == ['100-nmap-ping-scan', '500-bitwarden-passwords',
                            '950-generate-table-of-contents']
    assert caplog.text.count('Skipping plugin') == 3


def test_config_loader_is_never_skipped(caplog):
    with caplog.at_level(logging.WARNING):
        kept = pipeline.select_plugins(pipeline.discover_plugins(),
                                       ['001', 'ConfigLoader'])

    assert names(kept)[0] == 'ConfigLoader'
    assert vars.skipped == []
    assert 'Not skipping 001-config-loader' in caplog.text


def test_unknown_skip_entry_warns(caplog):
    with caplog.at_level(logging.WARNING):
        kept = pipeline.select_plugins(pipeline.discover_plugins(), ['777'])

    assert vars.skipped == []
    assert "No plugin matches skip entry '777'" in caplog.text
    assert len(kept) == len(pipeline.discover_plugins())


def test_run_with_skipped_plugin_omits_it_and_warns(content, monkeypatch,
                                                    caplog):
    monkeypatch.setenv('SKIP_PLUGINS', 'TableOfContents')

    with caplog.at_level(logging.WARNING):
        html = content.run()

    assert 'Table of Contents' not in html
    assert 'Hello from the intro' in html
    assert 'this output is incomplete' in caplog.text


def test_full_run_has_nothing_skipped(content, caplog):
    with caplog.at_level(logging.WARNING):
        content.run()

    assert vars.skipped == []
    assert 'incomplete' not in caplog.text
