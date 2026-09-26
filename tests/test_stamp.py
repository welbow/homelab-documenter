import json
import os
import zoneinfo

import pipeline
import stamp

STAMP = ('Generated 25 Sep 2026 19:42 EDT | engine {0} (abc1234). '
         'Passwords may have changed since this date.'
         .format(stamp.ENGINE_VERSION))


def test_stamp_text_names_time_zone_and_engine():
    assert stamp.text(stamp.make()) == STAMP


def test_now_uses_tz(monkeypatch):
    monkeypatch.undo()  # the real clock, not the tests' fixed one
    monkeypatch.setenv('TZ', 'America/New_York')

    assert stamp.now().tzinfo == zoneinfo.ZoneInfo('America/New_York')


def test_now_ignores_unknown_tz(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv('TZ', 'Nowhere/Special')

    assert stamp.now().utcoffset() is not None


def test_engine_commit_from_env_or_git_dir(tmp_path, monkeypatch):
    monkeypatch.delenv('ENGINE_COMMIT')
    git = tmp_path / '.git'
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n')

    assert stamp.engine_commit(str(tmp_path)) == 'dev'  # no ref yet

    (git / 'packed-refs').write_text(
        '# pack-refs with: peeled\n1111111aaaa refs/heads/main\n')
    assert stamp.engine_commit(str(tmp_path)) == '1111111'

    (git / 'refs' / 'heads' / 'main').write_text('2222222bbbb\n')
    assert stamp.engine_commit(str(tmp_path)) == '2222222'

    (git / 'HEAD').write_text('3333333cccc\n')  # detached
    assert stamp.engine_commit(str(tmp_path)) == '3333333'

    monkeypatch.setenv('ENGINE_COMMIT', '4444444dddd')
    assert stamp.engine_commit(str(tmp_path)) == '4444444'


def test_no_git_dir_is_dev(tmp_path, monkeypatch):
    monkeypatch.delenv('ENGINE_COMMIT')

    assert stamp.engine_commit(str(tmp_path)) == 'dev'


def test_every_page_carries_the_stamp(content):
    html = content.run()

    # the print footer (a page-margin box in the inline CSS), the banner
    # under the title, and the last line
    assert html.count(STAMP) == 3
    assert '@bottom-center { content: "{0}";'.replace('{0}', STAMP) in html
    assert html.index('<p class="stamp">' + STAMP) \
        < html.index('<a name=')


def test_date_placeholder_in_output_file_name(content):
    content.config['plugins']['HTMLOutput']['outputfile'] = \
        'homelab-packet-{date}.html'
    with open(os.path.join(content.root, 'conf', 'config.json'), 'w') as f:
        json.dump(content.config, f)

    pipeline.main(data_dir=content.root)

    assert os.listdir(os.path.join(content.root, 'build')) \
        == ['homelab-packet-2026-09-25.html']
