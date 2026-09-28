import vars
import os
global logging
import logging


# Define our default class

class Plugin:
    # Slow or needs a login (network scans, password managers): a partial
    # rebuild leaves it unticked by default and reuses its last results
    expensive = False

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

        seq = str(seq).strip()
        if not seq.isdigit():
            self._logger.warning(
                'seq_number {0!r} for section {1!r} is not a number; it goes '
                'after the numbered sections'.format(seq, title))

        new_module_key = '{0}-{1}'.format(seq, keyname)
        if new_module_key in vars.output:
            self._logger.warning(
                'Section {0} is added twice: {1!r} replaces {2!r}. Give one '
                'of them a different seq_number or key name'.format(
                    new_module_key, title,
                    vars.output[new_module_key]['title']))

        new_output = {
            'output': output,
            'title': title
        }

        for key, value in kwargs.items():
            new_output[key] = value

        vars.output[new_module_key] = new_output

    def addHost(self, ip, source=None, seen=True, **fields):
        """Add what this plugin knows about the host at ip to vars.hosts.
        Several plugins can report the same host: each is listed in its
        "sources", blank values never replace real ones, and when two
        disagree the first (lowest-numbered plugin) wins and the
        disagreement is logged.

        seen: whether this source saw the host on the network this run
        (False for what's only written down, e.g. a host override or a DHCP
        reservation without a lease). A host no source saw can say so, or
        be left out, with the fields status_if_unseen (text for the Status
        column) and hide_if_unseen."""
        source = source or type(self).__name__
        if vars.recording is not None:
            vars.recording.append((ip, source, dict(fields, seen=seen)))
        host = vars.hosts.setdefault(ip, {'ipaddress': ip, 'sources': []})
        host['seen'] = host.get('seen', False) or seen
        self._merge(host, 'Host ' + ip, source, fields)

    def addNetwork(self, subnet, source=None, **fields):
        """Add what this plugin knows about a network (subnet in CIDR form,
        e.g. name, purpose) to vars.networks, with the same merge rules as
        addHost."""
        source = source or type(self).__name__
        if vars.recording_networks is not None:
            vars.recording_networks.append((subnet, source, dict(fields)))
        network = vars.networks.setdefault(subnet, {'subnet': subnet,
                                                    'sources': []})
        self._merge(network, 'Network ' + subnet, source, fields)

    def _merge(self, record, label, source, fields):
        if source not in record['sources']:
            record['sources'].append(source)

        for key, value in fields.items():
            if value in (None, ''):
                continue
            current = record.get(key)
            if current in (None, ''):
                record[key] = value
            elif current != value:
                self._logger.info(
                    '{0}: keeping {1} {2!r}, {3} reported {4!r}'.format(
                        label, key, current, source, value))

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
