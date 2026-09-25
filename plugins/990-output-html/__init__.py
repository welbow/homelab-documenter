global logging
import logging

from dominate import document
from dominate.tags import *
from dominate.util import raw

import stamp
import vars
from Plugin import Plugin

# Inline, so the stamp shows even when the file is opened without its
# stylesheets (e.g. from a USB stick). In print, a page-margin box puts it
# at the bottom of every page, outside the content so it can't overlap
# (Chrome/Edge; other browsers still print the banner and the last line).
STAMP_CSS = """
.stamp {{ font-size: 0.9em; color: #555; }}
@media print {{
  @page {{
    margin: 1.5cm 1.5cm 2cm;
    @bottom-center {{ content: "{0}"; font-size: 8pt; color: #555; }}
  }}
}}
"""


def css_string(text):
    """Text made safe inside a double-quoted CSS string."""
    return text.replace('\\', '\\\\').replace('"', '\\"')


class HTMLOutput (Plugin):
    def __init__(self):
        super().__init__()
    
    def run(self):
        if not self.getConfig():
            return
        
        self._logger.info('Generating HTML')

        if not vars.stamp:  # run outside the pipeline
            vars.stamp = stamp.make()
        stamp_text = stamp.text(vars.stamp)

        with document(title='Homelab Documentation') as doc:
            with doc.head:
                # raw: dominate would HTML-escape the quotes and break the CSS
                style(raw(STAMP_CSS.format(css_string(stamp_text))))
                if 'stylesheets' in self._config.keys():
                    for ss in self._config['stylesheets']:
                        link(rel='stylesheet', href=ss)


            with doc.body as body:
                body['class'] = 'standard'

                h1('Homelab Documentation', name="top",_class='title')
                p(stamp_text, _class='stamp')
                
                for itemkey in sorted(vars.output.keys()):
                    item = vars.output[itemkey]
                    
                    if not item.get('hide_surround', False):
                        a(name=itemkey)
                        h1(item['title'])

                    div(item['output'])

                    if not item.get('hide_surround', False):
                        div(p(a('Return to top',href='#top')))

                p(stamp_text, _class='stamp')

        # "{date}" in the file name becomes the stamp's date, so the newest
        # copy is obvious
        outputfilename = self.makeOutputFilePath(
            self._config['outputfile'].replace('{date}', vars.stamp['date']))
        self._logger.info('Writing HTML to file {0}'.format(outputfilename))
        
        with open(outputfilename, 'w') as html_file:
            html_file.write(str(doc))

def getPlugin():
    return HTMLOutput()