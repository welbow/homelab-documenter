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

        output = []

        with ol():
            for itemkey in sorted(vars.output.keys()):
                output.append(str(li(a(vars.output[itemkey]['title'],href='#{0}'.format(itemkey)))))
        
        self.addOutput(
            output=raw(''.join(output)),
            title=self._config['title'],
            seq=self._config['seq_number'],
            keyname="table-of-contents"
        )

def getPlugin():
    return TableOfContents()