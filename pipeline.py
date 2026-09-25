import importlib
import logging
import os
import sys

import vars

logger = logging.getLogger('main')

APP_DIR = os.path.dirname(os.path.abspath(__file__))


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


def main(data_dir=os.curdir):
    """Run every plugin in order against the content in data_dir
    (which holds conf/, input/ and output/)."""
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(name)s %(levelname)s:%(message)s')

    logger.info('Starting {0}'.format(sys.argv[0]))

    vars.reset(data_dir)

    plugins = discover_plugins()

    logger.info('Found {0} plugins'.format(len(plugins)))

    for plugin in plugins:
        logger.info('Running plugin {0}'.format(type(plugin).__name__))
        plugin.run()
        logger.info('Finished running plugin {0}'.format(type(plugin).__name__))

    logger.info('Script terminated normally')
    return 0
