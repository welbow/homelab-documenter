import re

import pipeline


def test_discovers_all_plugins_in_numeric_order():
    names = [type(p).__name__ for p in pipeline.discover_plugins()]

    assert names == ['ConfigLoader', 'StaticFile', 'HostOverrides',
                     'NmapPingScan',
                     'BitwardenPasswords', 'OutputCredInfo',
                     'OutputHostInfo', 'TableOfContents', 'HTMLOutput']


def test_sections_render_in_seq_order(content):
    html = content.run()

    sections = re.findall(r'<a name="([^"]+)"', html)
    assert sections == ['004-table-of-contents', '005-static-file',
                        '010-static-file', '950-output-host-info']
    # The hide_surround banner (seq 002) has no anchor but still comes first.
    assert html.index('Confidential') < html.index('<a name=')


def test_html_input_kept_raw_and_plain_text_wrapped_in_pre(content):
    html = content.run()

    assert '<p>Hello from the intro</p>' in html
    assert re.search(r'<pre>\s*line one\s+line two\s*</pre>', html)


def test_hide_surround_has_no_heading_toc_entry_or_top_link(content):
    html = content.run()

    assert '<p class="warn">Confidential</p>' in html
    assert 'name="002-static-file"' not in html
    assert 'href="#002-static-file"' not in html
    # Every visible section (TOC, intro, notes, Appendix A) gets a
    # "Return to top" link; the banner doesn't.
    assert html.count('Return to top') == 4


def test_toc_links_all_point_at_anchors(content):
    html = content.run()

    links = re.findall(r'href="#([^"]+)"', html)
    anchors = set(re.findall(r'name="([^"]+)"', html))
    toc_links = [link for link in links if link != 'top']

    # The TOC lists every visible section except itself, in seq order.
    assert toc_links == ['005-static-file', '010-static-file',
                         '950-output-host-info']
    assert set(links) <= anchors


def test_running_twice_gives_identical_output(content):
    assert content.run() == content.run()
