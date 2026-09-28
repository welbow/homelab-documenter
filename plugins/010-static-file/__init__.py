global logging
import logging
import os
import re

from dominate.util import raw

from Plugin import Plugin

def default_keyname(filename):
    """Section key for a page without key_name: "static-file-" plus the
    file name (lowercase, no extension, other characters as "-"), so pages
    sharing a seq_number don't replace each other."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    slug = re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')
    return 'static-file-' + slug if slug else 'static-file'

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
                title=staticfile.get('title', 'No Title Specified'), 
                seq=staticfile.get('seq_number', None),
                keyname=staticfile.get('key_name') or
                        default_keyname(staticfile['file']),
                hide_surround=staticfile.get('hide_surround', False)
            )

def getPlugin():
    return StaticFile()