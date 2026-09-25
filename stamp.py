"""The generation stamp: when a packet was made and from which engine
version, so recipients holding copies from different runs can tell them
apart."""
import datetime
import os
import zoneinfo

ENGINE_VERSION = '0.2.0'

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def now():
    """The current time in TZ (e.g. America/New_York), else local time."""
    tz = os.environ.get('TZ', '').strip()
    if tz:
        try:
            return datetime.datetime.now(zoneinfo.ZoneInfo(tz))
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.datetime.now().astimezone()


def engine_commit(app_dir=APP_DIR):
    """Short hash of the engine's commit: ENGINE_COMMIT if set, else read
    from .git (without needing git installed), else 'dev'."""
    if os.environ.get('ENGINE_COMMIT', '').strip():
        return os.environ['ENGINE_COMMIT'].strip()[:7]

    git_dir = os.path.join(app_dir, '.git')
    try:
        with open(os.path.join(git_dir, 'HEAD')) as f:
            head = f.read().strip()
        if not head.startswith('ref: '):
            return head[:7]  # detached HEAD
        ref = head[5:]
        ref_file = os.path.join(git_dir, *ref.split('/'))
        if os.path.exists(ref_file):
            with open(ref_file) as f:
                return f.read().strip()[:7]
        with open(os.path.join(git_dir, 'packed-refs')) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0][:7]
    except OSError:
        pass
    return 'dev'


def make():
    """The stamp for this run; taken once so every page shows the same."""
    generated = now()
    return {
        'generated': generated,
        'date': generated.strftime('%Y-%m-%d'),
        'engine': '{0} ({1})'.format(ENGINE_VERSION, engine_commit()),
    }


def text(s):
    """One-line description of a stamp, as shown on every page."""
    return 'Generated {0} | engine {1}. Passwords may have changed since ' \
        'this date.'.format(s['generated'].strftime('%d %b %Y %H:%M %Z'),
                            s['engine'])
