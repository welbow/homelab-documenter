import vars
import os
global logging
import logging


# Define our default class

class Plugin:
    def getConfig(self) -> bool:
        # Corner case since a plugin loads the config - don't break that
        # Have we loaded config yet? If not, return early
        if 'plugins' not in vars.config.keys():
            return True

        # Does our plugin have config defined? If not, bail
        if type(self).__name__ not in vars.config['plugins'].keys():
            self._logger.warn('No config for plugin found')
            return False
        
        self._config = vars.config['plugins'][type(self).__name__]

        if self._config['enabled'] != 1:
            self._logger.warn('Plugin disabled by configuration')
            return False

        return True

    def addOutput(self, output, title=None, seq=None, keyname=None, **kwargs):
        module_key = type(self).__module__.split('.')[1]

        if title is None:
            title = module_key

        if seq is None:
            seq = module_key.split('-')[0]

        if keyname is None:
            keyname = '-'.join(module_key.split('-')[1:])

        new_module_key = '{0}-{1}'.format(seq, keyname)

        new_output = {
            'output': output,
            'title': title
        }

        for key, value in kwargs.items():
            new_output[key] = value

        vars.output[new_module_key] = new_output

    def getInputFilePath(self,file):
        return os.path.join(os.path.curdir, 'input',
            type(self).__name__, file)

    def makeOutputFilePath(self, filename):
        return os.path.join(os.path.curdir, 'output', filename)

    def __init__(self):
        self._logger=logging.getLogger(type(self).__name__)
        self.getConfig()

    def run(self):
        pass
