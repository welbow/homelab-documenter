import re


def media(html, kind):
    return '\n'.join(re.findall(r'@media ' + kind + r' \{(.*?)\n\}', html,
                                re.S))


def test_page_has_the_autofilter_and_sticky_headers(content):
    html = content.run()

    assert '<meta charset="utf-8">' in html
    assert 'var MIN_ROWS = 10;' in html
    assert "className = 'af-button'" in html          # the column buttons
    assert "'Sort A to Z'" in html and "'(Select all)'" in html
    screen = media(html, 'screen')
    assert 'position: sticky' in screen
    # hidden rows are hidden on screen only, so print shows every row
    assert 'tr.filtered-out { display: none; }' in screen
    printed = media(html, 'print')
    assert '.table-filter, .af-button, .af-panel { display: none' in printed
    assert 'filtered-out' not in printed
    # and in the original order: sorting is undone for printing
    assert "addEventListener('beforeprint'" in html


def test_filter_can_be_turned_off(content):
    content.config['plugins']['HTMLOutput']['table_filter'] = 0

    html = content.run()

    assert 'MIN_ROWS' not in html
    assert 'position: sticky' in html     # headers still stay in view
