global logging
import logging

from dominate.util import raw

from Plugin import Plugin

class StaticFile (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        for staticfile in self._config['files']:
            filename = self.getInputFilePath(staticfile['file'])
            
            with open(filename,'r') as f:
                output = f.read()
            
            if output.find('</') == -1:
                output = raw('<pre>{0}</pre>'.format(output))
            else:
                output = raw(output)

            self.addOutput(
                output=output, 
                title=staticfile.get('title', 'No title specified'), 
                seq=staticfile.get('seq_number', None),
                keyname=staticfile.get('key_name', None),
                hide_surround=staticfile.get('hide_surround', False)
            )

def getPlugin():
    return StaticFile()