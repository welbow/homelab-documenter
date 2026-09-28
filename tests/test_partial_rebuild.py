import json
import os
import shutil
import sys

import pytest

import pipeline
import reloader
import vars

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def preview(content, monkeypatch):
    """A preview-like state: results are kept between runs."""
    monkeypatch.setattr(vars, 'keep_alive', True)
    monkeypatch.setattr(vars, 'plugin_cache', {})
    content.config['plugins']['HostOverrides'] = {'enabled': 1}
    os.makedirs(os.path.join(content.root, 'input', 'HostOverrides'))
    write(content, 'input/HostOverrides/host-overrides.csv',
          'ip,name,type,notes\n192.0.2.1,Router,router,\n')
    return content


def write(content, path, text):
    with open(os.path.join(content.root, *path.split('/')), 'w') as f:
        f.write(text)


def write_config(content):
    with open(os.path.join(content.root, 'conf', 'config.json'), 'w') as f:
        json.dump(content.config, f)


def run(content, only=None):
    """Write the config and run the pipeline, fully or partially."""
    write_config(content)
    assert pipeline.main(data_dir=content.root, only=only) == 0
    with open(vars.page) as f:
        return f.read()


def test_unselected_plugins_reuse_their_last_results(preview):
    run(preview)
    write(preview, 'input/StaticFile/intro.html', '<p>Edited intro</p>')

    html = run(preview, only={'050-host-overrides'})

    assert 'Hello from the intro' in html       # StaticFile reused
    assert 'Edited intro' not in html
    assert 'Router' in html                     # hosts replayed too
    assert '010-static-file' in vars.last_run['replayed']
    assert '001-config-loader' in vars.last_run['ran']   # always runs
    assert '990-output-html' in vars.last_run['ran']


def test_selected_plugins_run_again(preview):
    run(preview)
    write(preview, 'input/StaticFile/intro.html', '<p>Edited intro</p>')

    html = run(preview, only={'010-static-file'})

    assert 'Edited intro' in html
    assert vars.last_run['notes'] == []


def test_replayed_hosts_keep_the_merge_order(preview):
    run(preview)
    host = dict(vars.hosts['192.0.2.1'])

    run(preview, only=set())

    assert vars.hosts['192.0.2.1'] == host
    assert vars.hosts['192.0.2.1']['sources'] == ['manual']


def test_changed_config_section_runs_again_with_a_note(preview):
    run(preview)
    preview.config['plugins']['StaticFile']['files'][0]['title'] = 'Welcome'

    html = run(preview, only=set())

    assert 'Welcome' in html
    assert 'StaticFile ran because its config.json section changed' \
        in vars.last_run['notes']


def test_full_run_after_a_partial_one_runs_everything(preview):
    run(preview)
    run(preview, only=set())

    run(preview)

    assert vars.last_run['replayed'] == []


def test_cache_drops_plugins_that_are_gone(preview, monkeypatch):
    run(preview)
    assert '050-host-overrides' in vars.plugin_cache
    monkeypatch.setenv('SKIP_PLUGINS', 'HostOverrides')

    run(preview)

    assert '050-host-overrides' not in vars.plugin_cache


def test_nothing_is_cached_outside_a_preview(content, monkeypatch):
    monkeypatch.setattr(vars, 'plugin_cache', {})
    content.run()

    assert vars.plugin_cache == {}


def test_options_list_plugins_with_defaults(preview):
    run(preview)

    options = {o['name']: o for o in pipeline.plugin_options()}

    assert options['001-config-loader']['always']
    assert options['990-output-html']['always']
    assert options['100-nmap-ping-scan']['expensive']
    assert options['500-bitwarden-passwords']['expensive']
    assert not options['010-static-file']['expensive']
    assert options['010-static-file']['cached']


# --- reloading code ---------------------------------------------------------

@pytest.fixture
def engine_copy(tmp_path, monkeypatch):
    """A throwaway copy of the plugins folder that the engine loads from,
    so a test can edit plugin code; sys.modules is restored afterwards."""
    parent = tmp_path / 'engine'
    shutil.copytree(os.path.join(ROOT, 'plugins'), parent / 'plugins',
                    ignore=shutil.ignore_patterns('__pycache__'))
    saved = {k: v for k, v in sys.modules.items()
             if k in reloader.RELOAD or k == 'plugins'
             or k.startswith('plugins.')}
    for name in saved:
        del sys.modules[name]
    monkeypatch.setenv('PLUGINS_DIR', str(parent / 'plugins'))
    monkeypatch.syspath_prepend(str(parent))
    yield parent / 'plugins'
    for name in [k for k in sys.modules if k in reloader.RELOAD
                 or k == 'plugins' or k.startswith('plugins.')]:
        del sys.modules[name]
    sys.modules.update(saved)


def edit_plugin(plugins, folder, old, new):
    path = plugins / folder / '__init__.py'
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))
    # make sure the change is visible even within the same second
    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + 2))


def test_reload_picks_up_changed_plugin_code(preview, engine_copy):
    write_config(preview)
    code = reloader.reload_code()
    code.main(data_dir=preview.root)
    edit_plugin(engine_copy, '010-static-file',
                "output = raw(output)", "output = raw(output + '<p>NEW CODE</p>')")

    code = reloader.reload_code()
    assert code.main(data_dir=preview.root, only=set()) == 0

    with open(vars.page) as f:
        assert 'NEW CODE' in f.read()
    assert 'StaticFile ran because its code changed' in vars.last_run['notes']


def test_reload_finds_new_plugin_folders(preview, engine_copy):
    code = reloader.reload_code()
    (engine_copy / '020-hello').mkdir()
    (engine_copy / '020-hello' / '__init__.py').write_text(
        'from Plugin import Plugin\n\n'
        'class Hello(Plugin):\n'
        '    def run(self):\n'
        "        self.addOutput('<p>Hello plugin</p>', title='Hello')\n\n"
        'def getPlugin():\n    return Hello()\n')

    code = reloader.reload_code()

    assert '020-hello' in [o['name'] for o in code.plugin_options()]


def test_reload_error_keeps_the_last_page(preview, engine_copy):
    write_config(preview)
    code = reloader.reload_code()
    code.main(data_dir=preview.root)
    page = vars.page
    with open(page) as f:
        before = f.read()
    edit_plugin(engine_copy, '010-static-file', 'def run(self):',
                'def run(self)')   # syntax error

    code = reloader.reload_code()
    with pytest.raises(SyntaxError):
        code.main(data_dir=preview.root, only=set())

    with open(page) as f:
        assert f.read() == before


def test_reload_is_available_only_with_the_code_mounted(monkeypatch):
    monkeypatch.setattr(reloader.delivery, 'is_mount_point',
                        lambda path: False)
    available, why = reloader.available()
    assert available is False
    assert 'Mount the engine folder over /app' in why

    monkeypatch.setattr(reloader.delivery, 'is_mount_point',
                        lambda path: path == reloader.APP_DIR)
    assert reloader.available() == (True, '')


def test_replayed_plugins_bring_back_their_networks(preview, monkeypatch):
    from Plugin import Plugin

    class Scopes(Plugin):
        runs = 0

        def run(self):
            Scopes.runs += 1
            self.addNetwork('192.0.2.0/24', source='MSDHCP', purpose='LAN')

    plugin = Scopes()
    monkeypatch.setattr(pipeline, 'directory', lambda p: 'x-scopes')
    monkeypatch.setattr(pipeline, 'config_section', lambda p: None)
    monkeypatch.setattr(pipeline, 'source_mtime', lambda p: 0)
    pipeline.run_recorded(plugin)
    vars.networks.clear()

    pipeline.replay(plugin)

    assert Scopes.runs == 1
    assert vars.networks['192.0.2.0/24']['purpose'] == 'LAN'


# --- re-reading vars (#30) ---------------------------------------------------

@pytest.fixture
def vars_copy(tmp_path):
    """A copy of vars.py to edit; the real vars module is restored after."""
    saved = dict(vars.__dict__)
    path = tmp_path / 'vars.py'
    with open(vars.__file__, encoding='utf-8') as f:
        path.write_text(f.read(), encoding='utf-8')
    yield path
    vars.__dict__.clear()
    vars.__dict__.update(saved)


def test_reload_takes_new_definitions_and_keeps_state(vars_copy,
                                                       monkeypatch):
    sessions = {'bitwarden': {'session': 'kept'}}
    monkeypatch.setattr(vars, 'sessions', sessions)
    monkeypatch.setattr(vars, 'plugin_cache', {'010-static-file': {}})
    text = vars_copy.read_text(encoding='utf-8')
    vars_copy.write_text(text.replace(
        "    'Notes': 'notes'\n", "    'Notes': 'notes',\n    'Room': 'room'\n")
        + '\nnew_setting = 42\n', encoding='utf-8')

    reloader.refresh_vars(str(vars_copy))

    assert vars.hosts_keys['Room'] == 'room'          # definition: new
    assert vars.new_setting == 42                     # new name: added
    assert vars.sessions is sessions                  # state: kept
    assert vars.plugin_cache == {'010-static-file': {}}
    vars.reset()                                      # functions still work
    assert vars.hosts == {} and vars.sessions is sessions


def test_broken_vars_leaves_vars_as_it_was(vars_copy):
    before = dict(vars.__dict__)
    vars_copy.write_text(vars_copy.read_text(encoding='utf-8')
                         + '\nhosts_keys = {\n', encoding='utf-8')

    with pytest.raises(SyntaxError):
        reloader.refresh_vars(str(vars_copy))

    assert vars.__dict__ == before


def test_restart_notes(tmp_path, monkeypatch):
    app = tmp_path / 'app'
    app.mkdir()
    image = tmp_path / 'image'
    image.mkdir()
    for name in reloader.SERVER_FILES:
        (app / name).write_text('x')
    (app / 'requirements.txt').write_text('dominate\npypsrp\n')
    (app / 'apt-pkgs.txt').write_text('nmap\n')
    (image / 'requirements.txt').write_text('dominate\r\npywinrm\r\n')
    (image / 'apt-pkgs.txt').write_text('nmap\r\n')   # same, other endings
    monkeypatch.setattr(reloader, 'APP_DIR', str(app))
    monkeypatch.setattr(reloader, 'IMAGE_DEPS_DIR', str(image))
    monkeypatch.setattr(reloader, '_started', {
        name: reloader._digest(name) for name in reloader.SERVER_FILES})
    assert reloader.restart_notes() == [
        'requirements.txt changed since the image was built: run docker '
        'compose build, then restart the preview']

    # rewritten unchanged (e.g. by a git checkout): not a change
    stat = os.stat(app / 'reloader.py')
    os.utime(app / 'reloader.py', (stat.st_atime, stat.st_mtime + 5))
    (app / 'delivery.py').write_text('y')
    (image / 'requirements.txt').write_text('dominate\npypsrp\n')

    assert reloader.restart_notes() == [
        'delivery.py changed since the preview started: restart the preview '
        'to use it']
