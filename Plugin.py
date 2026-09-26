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
            self._logger.warning('No config for plugin found')
            return False

        self._config = vars.config['plugins'][type(self).__name__]

        # A plugin config without "enabled" counts as disabled
        if self._config.get('enabled', 0) != 1:
            self._logger.warning('Plugin disabled by configuration')
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

    def addHost(self, ip, source=None, **fields):
        """Add what this plugin knows about the host at ip to vars.hosts.
        Several plugins can report the same host: each is listed in its
        "sources", blank values never replace real ones, and when two
        disagree the first (lowest-numbered plugin) wins and the
        disagreement is logged."""
        source = source or type(self).__name__
        host = vars.hosts.setdefault(ip, {'ipaddress': ip, 'sources': []})
        if source not in host['sources']:
            host['sources'].append(source)

        for key, value in fields.items():
            if value in (None, ''):
                continue
            current = host.get(key)
            if current in (None, ''):
                host[key] = value
            elif current != value:
                self._logger.info(
                    'Host {0}: keeping {1} {2!r}, {3} reported {4!r}'.format(
                        ip, key, current, source, value))

    def getInputFilePath(self,file):
        return os.path.join(vars.data_dir, 'input',
            type(self).__name__, file)

    def makeOutputFilePath(self, filename):
        # Generated files go to the build dir, never to output/ (which
        # holds the extra files shipped alongside the page)
        os.makedirs(vars.build_dir, exist_ok=True)
        return os.path.join(vars.build_dir, filename)

    def __init__(self):
        # Plugins are created before the config is loaded, so config is
        # only read in run() (via getConfig), never here.
        self._logger=logging.getLogger(type(self).__name__)

    def run(self):
        pass
