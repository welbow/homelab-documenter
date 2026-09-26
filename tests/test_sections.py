import logging
import re

import vars
from Plugin import Plugin


class Page(Plugin):
    pass


Page.__module__ = 'plugins.010-static-file'


def add(seq, keyname, title=None):
    Page().addOutput('<p>{0}</p>'.format(keyname), title=title or keyname,
                     seq=seq, keyname=keyname)


def test_numbers_sort_as_numbers_not_text():
    add('10', 'ten')
    add('5', 'five')
    add('100', 'hundred')
    add('20', 'twenty')

    assert vars.section_keys() == ['5-five', '10-ten', '20-twenty',
                                   '100-hundred']


def test_int_and_padded_str_mix():
    add(960, 'passwords')        # an int in config.json
    add('005', 'contents')       # a padded string
    add(50, 'hosts')
    add('010', 'start')

    assert vars.section_keys() == ['005-contents', '010-start', '50-hosts',
                                   '960-passwords']


def test_same_number_orders_by_key():
    add('010', 'b-page')
    add('010', 'a-page')

    assert vars.section_keys() == ['010-a-page', '010-b-page']


def test_non_numeric_goes_last_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        add('appendix', 'extra', title='Extra')
    add('999', 'last-number')
    add('001', 'first')

    assert vars.section_keys() == ['001-first', '999-last-number',
                                   'appendix-extra']
    assert "seq_number 'appendix' for section 'Extra' is not a number" \
        in caplog.text


def test_packet_and_contents_follow_numeric_order(content):
    files = content.config['plugins']['StaticFile']['files']
    files[0]['seq_number'] = '30'     # intro
    files[1]['seq_number'] = 7        # plain notes, an int
    content.config['plugins']['TableOfContents']['seq_number'] = 4

    html = content.run()

    assert re.findall(r'<a name="([^"]+)"', html) == [
        '4-table-of-contents', '7-static-file', '30-static-file',
        '950-output-host-info']
    # the contents list (which doesn't list itself) in the same order
    contents = re.findall(r'<li>\s*<a href="#([^"]+)"', html)
    assert contents == ['7-static-file', '30-static-file',
                        '950-output-host-info']
