import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pipeline  # noqa: E402
import vars  # noqa: E402


# A small, fake content repo: three static sections (one of them a
# hide_surround banner), nmap and Bitwarden off, everything else on.
DEFAULT_CONFIG = {
    'plugins': {
        'StaticFile': {
            'enabled': 1,
            'files': [
                {'seq_number': '005', 'title': 'Introduction',
                 'file': 'intro.html'},
                {'seq_number': '010', 'title': 'Plain notes',
                 'file': 'notes.txt'},
                {'seq_number': '002', 'title': '',
                 'file': 'banner.html', 'hide_surround': 1},
            ],
        },
        'NmapPingScan': {'enabled': 0, 'subnets': []},
        'BitwardenPasswords': {'enabled': 0},
        'OutputHostInfo': {'enabled': 1, 'title': 'Appendix A - Hosts',
                           'header': 'All hosts', 'seq_number': 950},
        'OutputCredInfo': {'enabled': 1},
        'TableOfContents': {'enabled': 1, 'seq_number': '004',
                            'title': 'Table of Contents'},
        'HTMLOutput': {'enabled': 1, 'outputfile': 'output.html',
                       'stylesheets': ['standard.css']},
    }
}

STATIC_FILES = {
    'intro.html': '<p>Hello from the intro</p>',
    'notes.txt': 'line one\nline two',
    'banner.html': '<p class="warn">Confidential</p>',
}


class Content:
    """A throwaway content dir (conf/, input/, output/) under tmp_path."""

    def __init__(self, root, config):
        self.root = str(root)
        self.config = config
        os.makedirs(os.path.join(self.root, 'conf'))
        os.makedirs(os.path.join(self.root, 'input', 'StaticFile'))
        os.makedirs(os.path.join(self.root, 'output'))
        for name, text in STATIC_FILES.items():
            with open(os.path.join(self.root, 'input', 'StaticFile', name),
                      'w') as f:
                f.write(text)

    def run(self):
        """Write the config, run the whole pipeline, return the HTML."""
        with open(os.path.join(self.root, 'conf', 'config.json'), 'w') as f:
            json.dump(self.config, f)
        assert pipeline.main(data_dir=self.root) == 0
        with open(os.path.join(self.root, 'output', 'output.html')) as f:
            return f.read()


@pytest.fixture(autouse=True)
def clean_state():
    vars.reset()
    yield
    vars.reset()


@pytest.fixture
def content(tmp_path):
    return Content(tmp_path, json.loads(json.dumps(DEFAULT_CONFIG)))
