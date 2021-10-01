global logging
import logging

from dominate import document
from dominate.tags import *

import vars
from Plugin import Plugin

class HTMLOutput (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Generating HTML')

        with document(title='Homelab Documentation') as doc:
            if 'stylesheets' in self._config.keys():
                with doc.head:
                    for ss in self._config['stylesheets']:
                        link(rel='stylesheet', href=ss)


            with doc.body as body:
                body['class'] = 'standard'

                h1('Homelab Documentation', name="top",_class='title')
                
                for itemkey in sorted(vars.output.keys()):
                    item = vars.output[itemkey]
                    h1(item['title'],name=itemkey)

                    div(item['output'])

                    div(p(a('Return to top',href='#top')))

        outputfilename = self.makeOutputFilePath(self._config['outputfile'])
        self._logger.info('Writing HTML to file {0}'.format(outputfilename))
        
        with open(outputfilename, 'w') as html_file:
            html_file.write(str(doc))

def getPlugin():
    return HTMLOutput()