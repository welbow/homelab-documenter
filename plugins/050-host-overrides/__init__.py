global logging
import logging
import csv
import ipaddress
import os

from Plugin import Plugin

# The types the packet uses; anything else is probably a typo, so it's
# warned about (but still shown)
KNOWN_TYPES = ('router', 'switch', 'server', 'VM', 'PC', 'phone', 'IoT')

class HostOverrides (Plugin):
    """What can't be discovered, written down by hand: a CSV in the content
    repo (input/HostOverrides/host-overrides.csv) with columns ip, name,
    type, notes. Runs before the discovery plugins, so these values win
    over discovered ones; shown as "manual" in the Seen by column."""

    def __init__(self):
        super().__init__()

    def run(self):
        if not self.getConfig():
            return

        filename = self.getInputFilePath(self._config.get('file', 'host-overrides.csv'))
        if not os.path.exists(filename):
            self._logger.info('No host overrides file at {0}'.format(filename))
            return

        known = {t.lower(): t for t in KNOWN_TYPES}
        count = 0
        # utf-8-sig: Excel saves CSV with a byte-order mark
        with open(filename, newline='', encoding='utf-8-sig') as f:
            for line, row in enumerate(csv.DictReader(f), start=2):
                row = {(k or '').strip().lower(): (v or '').strip()
                       for k, v in row.items()}
                try:
                    ip = str(ipaddress.ip_address(row.get('ip', '')))
                except ValueError:
                    self._logger.warning('Line {0}: skipping, {1!r} is not '
                                         'an IP address'.format(
                                             line, row.get('ip', '')))
                    continue

                host_type = row.get('type', '')
                if host_type.lower() in known:
                    host_type = known[host_type.lower()]
                elif host_type:
                    self._logger.warning('Line {0}: unknown type {1!r} for '
                                         '{2} (expected one of {3})'.format(
                                             line, host_type, ip,
                                             ', '.join(KNOWN_TYPES)))

                self.addHost(ip, source='manual', name=row.get('name', ''),
                             type=host_type, notes=row.get('notes', ''))
                count += 1

        self._logger.info('Read {0} host override(s)'.format(count))

def getPlugin():
    return HostOverrides()
