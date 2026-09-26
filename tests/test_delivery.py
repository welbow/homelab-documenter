import logging
import os
import re
import threading
import urllib.request

import pytest

import delivery
import vars


@pytest.fixture
def built(content):
    """A generated page, plus a stylesheet among the extras in output/."""
    content.run()
    with open(os.path.join(content.root, 'output', 'standard.css'), 'w') as f:
        f.write('body { color: black; }')
    return content


def test_page_is_generated_in_build_dir_not_output(built):
    assert vars.page == os.path.join(built.root, 'build', 'output.html')
    assert os.listdir(os.path.join(built.root, 'output')) == ['standard.css']


def test_build_dir_from_env(content, monkeypatch, tmp_path):
    monkeypatch.setenv('BUILD_DIR', str(tmp_path / 'mem'))

    vars.reset(content.root)

    assert vars.build_dir == str(tmp_path / 'mem')


def test_print_styles_and_section_markup(built):
    with open(vars.page) as f:
        html = f.read()

    assert '.section { break-before: page; }' in html
    assert '.top-link { display: none; }' in html
    assert 'thead { display: table-header-group; }' in html
    # paper size is left to the print dialog
    assert not re.search(r'(?<![-\w])size\s*:', html)
    assert html.count('class="section"') == 4
    assert html.count('class="top-link"') == 4
    assert '<thead>' in html


def test_export_copies_page_and_extras_and_lists_them(built, tmp_path,
                                                      caplog):
    usb = tmp_path / 'usb'
    usb.mkdir()
    extras_dir = os.path.join(built.root, 'output')
    os.makedirs(os.path.join(extras_dir, 'img'))
    with open(os.path.join(extras_dir, 'img', 'map.png'), 'wb') as f:
        f.write(b'png')

    with caplog.at_level(logging.INFO):
        assert delivery.export(vars.page, extras_dir, str(usb))

    assert sorted(os.listdir(usb)) == ['img', 'output.html', 'standard.css']
    assert (usb / 'img' / 'map.png').read_bytes() == b'png'
    for name in ('output.html', 'standard.css', 'map.png'):
        assert name in caplog.text
    assert 'Exported 3 file(s)' in caplog.text


def test_export_warns_about_old_packets_among_extras(built, tmp_path,
                                                     caplog):
    usb = tmp_path / 'usb'
    usb.mkdir()
    extras_dir = os.path.join(built.root, 'output')
    open(os.path.join(extras_dir, 'homelab-packet-2026-01-01.html'),
         'w').close()

    with caplog.at_level(logging.WARNING):
        assert delivery.export(vars.page, extras_dir, str(usb))

    assert 'homelab-packet-2026-01-01.html looks like an old generated ' \
        'packet' in caplog.text
    assert (usb / 'homelab-packet-2026-01-01.html').exists()


def test_extra_with_the_page_name_is_not_copied(built, tmp_path, caplog):
    usb = tmp_path / 'usb'
    usb.mkdir()
    extras_dir = os.path.join(built.root, 'output')
    with open(os.path.join(extras_dir, 'output.html'), 'w') as f:
        f.write('OLD')

    with caplog.at_level(logging.WARNING):
        assert delivery.export(vars.page, extras_dir, str(usb))

    assert (usb / 'output.html').read_text() != 'OLD'
    assert 'Not copying extra file output.html' in caplog.text


def test_export_refuses_skipped_run_unless_forced(built, tmp_path, caplog):
    usb = tmp_path / 'usb'
    usb.mkdir()
    extras_dir = os.path.join(built.root, 'output')

    assert not delivery.export(vars.page, extras_dir, str(usb),
                               skipped=['500-bitwarden-passwords'])
    assert os.listdir(usb) == []
    assert 'packet is incomplete' in caplog.text

    assert delivery.export(vars.page, extras_dir, str(usb),
                           skipped=['500-bitwarden-passwords'], force=True)
    assert 'output.html' in os.listdir(usb)


def test_export_needs_an_existing_folder(built, tmp_path, caplog):
    assert not delivery.export(vars.page, os.path.join(built.root, 'output'),
                               str(tmp_path / 'missing'))
    assert 'is not a folder' in caplog.text


def test_preview_serves_page_and_extras(built):
    server = delivery.make_server(vars.page,
                                  os.path.join(built.root, 'output'),
                                  '127.0.0.1', 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = 'http://127.0.0.1:{0}'.format(port)
        with urllib.request.urlopen(base + '/') as r:  # redirects to page
            assert r.url.endswith('/output.html')
            assert b'Homelab Documentation' in r.read()
        with urllib.request.urlopen(base + '/standard.css') as r:
            assert r.read() == b'body { color: black; }'
    finally:
        server.shutdown()
        server.server_close()
