global logging
import logging

from dominate.tags import *
from dominate.util import raw

import vars
from Plugin import Plugin

class TableOfContents (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Generating table of contents')

        with ol() as o:
            for itemkey in sorted(vars.output.keys()):
                if not vars.output[itemkey].get('hide_surround', False):
                    li(a(vars.output[itemkey]['title'],href='#{0}'.format(itemkey)))
        
        self.addOutput(
            output=o,
            title=self._config['title'],
            seq=self._config['seq_number'],
            keyname="table-of-contents"
        )

def getPlugin():
    return TableOfContents()