import importlib
import logging
import os
import sys

import logconfig
import vars

logger = logging.getLogger('main')

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Loads the config every other plugin needs, so it can't be skipped
NEVER_SKIP = '001-config-loader'


def discover_plugins(plugins_dir=os.path.join(APP_DIR, 'plugins')):
    """Import every numbered plugin package, in numeric order, and return
    one instance of each (via its module-level getPlugin())."""
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


def main(data_dir=os.curdir, skip=()):
    """Run every plugin in order against the content in data_dir
    (which holds conf/, input/ and output/), minus any plugins skipped
    via SKIP_PLUGINS or skip."""
    logging.basicConfig(format='%(asctime)s %(name)s %(levelname)s:%(message)s')
    # LOG_LEVEL wins; otherwise INFO until the config loader applies
    # the config's log_level
    logging.getLogger().setLevel(logconfig.DEFAULT_LEVEL)
    if logconfig.env_level():
        logconfig.set_level(logconfig.env_level())

    logger.info('Starting {0}'.format(sys.argv[0]))

    vars.reset(data_dir)

    plugins = discover_plugins()

    logger.info('Found {0} plugins'.format(len(plugins)))

    plugins = select_plugins(plugins, skip_list(skip))

    for plugin in plugins:
        logger.info('Running plugin {0}'.format(type(plugin).__name__))
        plugin.run()
        logger.info('Finished running plugin {0}'.format(type(plugin).__name__))

    if vars.skipped:
        logger.warning('Skipped {0}: this output is incomplete; do not hand '
                       'it out'.format(', '.join(vars.skipped)))

    logger.info('Script terminated normally')
    return 0
