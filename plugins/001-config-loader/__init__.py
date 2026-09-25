import json
global logging
import logging
import os

import logconfig
import vars
from Plugin import Plugin

class ConfigLoader (Plugin):
    def __init__(self):
        super().__init__()

    def run(self):
        with open(os.path.join(vars.data_dir, 'conf', 'config.json')) as json_file:
            vars.config = json.load(json_file)

        # The LOG_LEVEL environment variable overrides the config
        if 'log_level' in vars.config and not logconfig.env_level():
            logconfig.set_level(vars.config['log_level'])

        self._logger.info('Read config from file')
        self._logger.debug('config = {0}'.format(logconfig.redact(vars.config)))

def getPlugin():
    return ConfigLoader()