import importlib
import json
import logging
import os
import sys

import logconfig
import stamp
import vars

logger = logging.getLogger('main')

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Loads the config every other plugin needs, so it can't be skipped
NEVER_SKIP = '001-config-loader'

# From this number on, plugins assemble what the data plugins produced
# (tables, contents, the page); they always run, even in a partial rebuild
OUTPUT_FROM = 900


def discover_plugins(plugins_dir=None):
    """Import every numbered plugin package, in numeric order, and return
    one instance of each (via its module-level getPlugin()). The folder is
    plugins/ next to this file, or PLUGINS_DIR (used by the tests)."""
    plugins_dir = plugins_dir or os.environ.get('PLUGINS_DIR') or \
        os.path.join(APP_DIR, 'plugins')
    parent = os.path.dirname(plugins_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    package = os.path.basename(plugins_dir)
    names = sorted(n for n in os.listdir(plugins_dir)
                   if n[:1].isdigit()
                   and os.path.isdir(os.path.join(plugins_dir, n)))

    plugins = []
    for name in names:
        module = '{0}.{1}'.format(package, name)
        logger.debug('Found plugin module {0}'.format(module))
        plugins.append(importlib.import_module(module).getPlugin())

    return plugins


def skip_list(extra=()):
    """Plugins to skip: SKIP_PLUGINS (comma-separated) plus any extra
    entries, each of which may itself be comma-separated."""
    entries = [os.environ.get('SKIP_PLUGINS', '')] + list(extra)
    return [s.strip() for e in entries for s in e.split(',') if s.strip()]


def plugin_matches(plugin, entry):
    """Does a skip entry name this plugin, by its numeric prefix (500),
    directory (500-bitwarden-passwords) or class (BitwardenPasswords)?"""
    directory = type(plugin).__module__.split('.')[-1]
    entry = entry.lower()
    return entry in (directory.split('-')[0], directory.lower(),
                     type(plugin).__name__.lower())


def select_plugins(plugins, skip):
    """Drop the plugins named in skip, logging each at WARNING."""
    used = set()
    selected = []
    for plugin in plugins:
        directory = type(plugin).__module__.split('.')[-1]
        matched = [e for e in skip if plugin_matches(plugin, e)]
        used.update(matched)
        if not matched:
            selected.append(plugin)
        elif directory == NEVER_SKIP:
            logger.warning('Not skipping {0}: every run needs the '
                           'config'.format(directory))
            selected.append(plugin)
        else:
            logger.warning('Skipping plugin {0} ({1})'.format(
                type(plugin).__name__, directory))
            vars.skipped.append(directory)

    for entry in skip:
        if entry not in used:
            logger.warning('No plugin matches skip entry {0!r}'.format(entry))

    return selected


def directory(plugin):
    """The plugin's folder name, e.g. 100-nmap-ping-scan."""
    return type(plugin).__module__.split('.')[-1]


def number(plugin):
    prefix = directory(plugin).split('-')[0]
    return int(prefix) if prefix.isdigit() else 0


def always_runs(plugin):
    """The config loader and the output plugins run on every rebuild."""
    return directory(plugin) == NEVER_SKIP or number(plugin) >= OUTPUT_FROM


def source_mtime(plugin):
    try:
        return os.path.getmtime(sys.modules[type(plugin).__module__].__file__)
    except (KeyError, AttributeError, OSError):
        return None


def config_section(plugin):
    section = vars.config.get('plugins', {}).get(type(plugin).__name__)
    return json.dumps(section, sort_keys=True)


def run_recorded(plugin):
    """Run a data plugin during a preview and keep what it produced, so a
    later partial rebuild can reuse it instead of running it again."""
    output_before = dict(vars.output)
    creds_before = dict(vars.creds)
    vars.recording = []
    try:
        plugin.run()
        hosts = vars.recording
    finally:
        vars.recording = None
    vars.plugin_cache[directory(plugin)] = {
        'output': {k: v for k, v in vars.output.items()
                   if output_before.get(k) is not v},
        'creds': {k: v for k, v in vars.creds.items()
                  if creds_before.get(k) is not v},
        'hosts': hosts,
        'config': config_section(plugin),
        'mtime': source_mtime(plugin),
    }


def replay(plugin):
    """Put back what the plugin produced on its last run: its sections,
    credentials, and hosts (through addHost again, in plugin order, so the
    merge rules still hold)."""
    cached = vars.plugin_cache[directory(plugin)]
    vars.output.update(cached['output'])
    vars.creds.update(cached['creds'])
    for ip, source, fields in cached['hosts']:
        plugin.addHost(ip, source=source, **fields)


def why_rerun(plugin, only):
    """Why a data plugin must run in a partial rebuild, or None to reuse its
    last results."""
    name = directory(plugin)
    cached = vars.plugin_cache.get(name)
    if name in only:
        return 'selected'
    if cached is None:
        return 'no earlier results'
    if cached['config'] != config_section(plugin):
        return 'its config.json section changed'
    if cached['mtime'] != source_mtime(plugin):
        return 'its code changed'
    return None


def plugin_options(skip=()):
    """The plugins a partial rebuild can offer, in run order: folder name,
    class name, whether it always runs, whether it's expensive (unticked
    by default) and whether it has results from an earlier run to reuse."""
    plugins = [p for p in discover_plugins()
               if not any(plugin_matches(p, e) for e in skip_list(skip))
               or directory(p) == NEVER_SKIP]
    return [{'name': directory(p), 'title': type(p).__name__,
             'always': always_runs(p), 'expensive': bool(p.expensive),
             'cached': directory(p) in vars.plugin_cache}
            for p in plugins]


def main(data_dir=os.curdir, skip=(), only=None):
    """Run every plugin in order against the content in data_dir
    (which holds conf/, input/ and output/), minus any plugins skipped
    via SKIP_PLUGINS or skip.

    With only (a set of plugin folder names), a partial rebuild during a
    preview: those data plugins run, the others reuse their results from
    the last run (unless their config section or code changed, or they
    have none), and the config loader and output plugins always run."""
    logging.basicConfig(format='%(asctime)s %(name)s %(levelname)s:%(message)s')
    # LOG_LEVEL wins; otherwise INFO until the config loader applies
    # the config's log_level
    logging.getLogger().setLevel(logconfig.DEFAULT_LEVEL)
    if logconfig.env_level():
        logconfig.set_level(logconfig.env_level())

    logger.info('Starting {0}'.format(sys.argv[0]))

    vars.reset(data_dir)
    vars.stamp = stamp.make()
    vars.last_run = {'ran': [], 'replayed': [], 'notes': []}
    logger.info(stamp.text(vars.stamp))

    plugins = discover_plugins()

    logger.info('Found {0} plugins'.format(len(plugins)))

    plugins = select_plugins(plugins, skip_list(skip))

    for plugin in plugins:
        name = directory(plugin)
        if only is not None and not always_runs(plugin):
            reason = why_rerun(plugin, only)
            if reason is None:
                logger.info('Reusing the last results of {0}'.format(
                    type(plugin).__name__))
                replay(plugin)
                vars.last_run['replayed'].append(name)
                continue
            if reason != 'selected':
                vars.last_run['notes'].append('{0} ran because {1}'.format(
                    type(plugin).__name__, reason))

        logger.info('Running plugin {0}'.format(type(plugin).__name__))
        if vars.keep_alive and not always_runs(plugin):
            run_recorded(plugin)
        else:
            plugin.run()
        vars.last_run['ran'].append(name)
        logger.info('Finished running plugin {0}'.format(type(plugin).__name__))

    # Results of plugins that no longer exist or were skipped this time
    # mustn't come back later
    present = {directory(p) for p in plugins}
    for name in list(vars.plugin_cache):
        if name not in present:
            del vars.plugin_cache[name]

    if vars.skipped:
        logger.warning('Skipped {0}: this output is incomplete; do not hand '
                       'it out'.format(', '.join(vars.skipped)))

    logger.info('Script terminated normally')
    return 0
