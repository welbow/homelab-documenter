#!/usr/bin/python3

import importlib
import os
import glob
import sys
import logging

import vars

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)s %(levelname)s:%(message)s')

logger = logging.getLogger('main')

plugins = []

logger.info('Starting {0}'.format(sys.argv[0]))

pdirs = glob.glob('plugins/[0-9]*')
pdirs.sort()

for plugin_dir in pdirs:
    d = plugin_dir

    m = d.replace('/', '.')

    logger.debug('Found plugin module {0}'.format(m))

    plugins.append(importlib.import_module(m, "").getPlugin())

logger.info('Found {0} plugins'.format(
    len(plugins)))

for plugin in plugins:
    logger.info('Running plugin {0}'.format(type(plugin).__name__))
    plugin.run()
    logger.info('Finished running plugin {0}'.format(type(plugin).__name__))

logger.info('Script terminated normally')
