import contextlib
import json
import os
import threading
import urllib.error
import urllib.request

import pytest

import delivery
import pipeline
import vars


@contextlib.contextmanager
def serving(page, extras_dir, rebuild=None):
    server = delivery.make_server(page, extras_dir, '127.0.0.1', 0, rebuild)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:{0}'.format(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.read().decode('utf-8')


def post(url, headers=None):
    request = urllib.request.Request(url, data=b'', method='POST',
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture
def built(content):
    content.run()
    return content


def test_button_only_on_the_served_page_never_in_the_file(built):
    extras = os.path.join(built.root, 'output')

    with serving(vars.page, extras, rebuild=lambda: vars.page) as base:
        served = get(base + '/output.html')
    with serving(vars.page, extras) as base:
        without = get(base + '/output.html')

    assert 'id="hd-rebuild"' in served
    assert '@media print { #hd-rebuild { display: none' in served
    assert served.index('hd-rebuild') < served.lower().rindex('</body>')
    # no rebuild possible (e.g. not a preview): no button
    assert 'hd-rebuild' not in without
    # the generated file itself never has it, so exports can't either
    with open(vars.page) as f:
        assert 'hd-rebuild' not in f.read()


def test_rebuild_reruns_the_pipeline_and_serves_the_new_page(built):
    extras = os.path.join(built.root, 'output')
    intro = os.path.join(built.root, 'input', 'StaticFile', 'intro.html')

    def rebuild():
        assert pipeline.main(data_dir=built.root) == 0
        return vars.page

    with serving(vars.page, extras, rebuild) as base:
        assert 'Hello from the intro' in get(base + '/output.html')
        with open(intro, 'w') as f:
            f.write('<p>Edited intro</p>')

        status, data = post(base + '/rebuild')

        assert (status, data) == (200, {'ok': True, 'page': '/output.html'})
        page = get(base + '/output.html')
        assert 'Edited intro' in page
        assert 'Hello from the intro' not in page


def test_failed_rebuild_reports_the_error(built):
    def rebuild():
        raise RuntimeError('config.json is not valid JSON')

    with serving(vars.page, os.path.join(built.root, 'output'),
                 rebuild) as base:
        status, data = post(base + '/rebuild')
        # the old page is still served
        assert 'Homelab Documentation' in get(base + '/output.html')

    assert status == 500
    assert data == {'ok': False, 'error': 'Rebuild failed: config.json is '
                                          'not valid JSON'}


def test_one_rebuild_at_a_time(built):
    started, finish = threading.Event(), threading.Event()

    def slow_rebuild():
        started.set()
        finish.wait(5)
        return vars.page

    with serving(vars.page, os.path.join(built.root, 'output'),
                 slow_rebuild) as base:
        first = threading.Thread(target=post, args=(base + '/rebuild',))
        first.start()
        started.wait(5)
        status, data = post(base + '/rebuild')
        finish.set()
        first.join(5)

    assert (status, data) == (409, {'ok': False,
                                    'error': 'Already rebuilding'})


def test_rebuild_refused_from_another_web_page(built):
    calls = []

    with serving(vars.page, os.path.join(built.root, 'output'),
                 lambda: calls.append(1) or vars.page) as base:
        status, _ = post(base + '/rebuild',
                         {'Origin': 'https://evil.example'})
        same, _ = post(base + '/rebuild', {'Origin': base})

    assert status == 403
    assert same == 200
    assert calls == [1]


def test_no_rebuild_endpoint_without_a_rebuild(built):
    with serving(vars.page, os.path.join(built.root, 'output')) as base:
        status, _ = post(base + '/rebuild')

    assert status == 404
