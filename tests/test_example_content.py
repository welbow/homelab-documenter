"""The example content repo (homelab-documenter-example, copied here as
tests/fixtures/example-content) must build with the engine as is, with no
credentials, so the sample people start from and the engine can't drift
apart. When the example repo changes, update the fixture."""
import json
import os
import re
import shutil

import pipeline
import vars

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'example-content')


def test_example_content_builds_without_credentials(tmp_path):
    root = str(tmp_path / 'content')
    shutil.copytree(FIXTURE, root)

    assert pipeline.main(data_dir=root) == 0

    with open(vars.page, encoding='utf-8') as f:
        html = f.read()
    assert re.findall(r'<a name="([^"]+)"', html) == [
        '005-table-of-contents', '010-static-file', '020-static-file',
        '030-static-file', '950-output-host-info']
    assert 'Confidential.' in html                 # the hide_surround banner
    assert 'Living room TV box' in html            # from host-overrides.csv
    assert vars.skipped == []


def test_example_config_uses_example_values_only():
    with open(os.path.join(FIXTURE, 'conf', 'config.json')) as f:
        text = f.read()
    config = json.loads(text)

    plugins = config['plugins']
    # the credential-needing and network plugins are off by default
    assert plugins['BitwardenPasswords']['enabled'] == 0
    assert plugins['NmapPingScan']['enabled'] == 0
    # documentation addresses and example.com only
    for address in re.findall(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', text):
        assert address.startswith('192.0.2.'), address
    assert os.listdir(os.path.join(FIXTURE, 'secrets')) == ['.gitkeep']
