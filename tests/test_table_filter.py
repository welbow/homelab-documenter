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


def test_panel_stays_open_until_ok_cancel_or_another_panel(content):
    """Clicking elsewhere or scrolling (even the page, e.g. when the wheel
    keeps going past the end of the value list) doesn't close the panel;
    OK, Cancel, Esc or another column's panel do."""
    html = content.run()

    assert "addEventListener('scroll'" not in html
    assert "addEventListener('mousedown'" not in html
    assert "document.addEventListener('click', closePanel)" not in html
    assert "cancel.addEventListener('click', closePanel)" in html
    assert "if (event.key === 'Escape') closePanel();" in html
    assert 'overscroll-behavior: contain;' in html
