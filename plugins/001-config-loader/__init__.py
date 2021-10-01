import json
global logging
import logging

import vars
from Plugin import Plugin

class ConfigLoader (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        with open('conf/config.json') as json_file:
            vars.config = json.load(json_file)

        self._logger.info('Read config from file')
        self._logger.debug('config = {0}'.format(vars.config))

def getPlugin():
    return ConfigLoader()