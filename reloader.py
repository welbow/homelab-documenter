"""Reloading the engine's code during a preview (#25), so edits show up on
the next rebuild without restarting the container. It only helps when the
engine folder is mounted over /app (see docker-compose.override.yml.example);
otherwise the container runs the code baked into the image."""
import hashlib
import importlib
import os
import sys

import delivery
import vars

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Reloaded: the pipeline, the plugin base class, their helpers, and every
# plugin; vars is re-read in place, keeping its live state (vars.STATE).
# Not reloaded: the preview server (delivery and homelab-documenter, which
# are serving the request) and this module; a change to them needs a
# restart, and the Rebuild panel says so (restart_notes).
RELOAD = ('pipeline', 'Plugin', 'credentials', 'hostpath', 'stamp',
          'logconfig', 'stdin_value')
SERVER_FILES = ('delivery.py', 'homelab-documenter.py', 'reloader.py')
# Copies of the dependency lists the image was built with (see the
# Dockerfile), to tell when the image needs rebuilding
IMAGE_DEPS_DIR = '/usr/local/share/homelab-documenter'
DEPS_FILES = ('requirements.txt', 'apt-pkgs.txt')


def _digest(name):
    """The file's content hash: by content, not time, so a checkout that
    rewrites a file unchanged doesn't count as a change."""
    try:
        with open(os.path.join(APP_DIR, name), 'rb') as f:
            text = f.read().replace(b'\r\n', b'\n')
        return hashlib.sha256(text).hexdigest()
    except OSError:
        return None


# When the preview started (this module is imported then)
_started = {name: _digest(name) for name in SERVER_FILES}


def available():
    """(True, '') if reloading can pick up edits, else (False, why)."""
    if delivery.is_mount_point(APP_DIR):
        return True, ''
    return False, ('The engine code is baked into the image, so there is '
                   'nothing new to load. Mount the engine folder over /app '
                   '(see docker-compose.override.yml.example) to use this.')


def refresh_vars(path=None):
    """Re-read vars.py into the vars module, keeping the values of its
    state names (vars.STATE as the file now defines it) so kept sessions and
    cached results survive. Every module keeps the same vars object. If the
    file fails (e.g. a SyntaxError), vars is left as it was."""
    path = path or vars.__file__
    with open(path, encoding='utf-8') as f:
        code = compile(f.read(), path, 'exec')
    before = dict(vars.__dict__)
    try:
        exec(code, vars.__dict__)
    except BaseException:
        vars.__dict__.clear()
        vars.__dict__.update(before)
        raise
    for name in vars.STATE:
        if name in before:
            vars.__dict__[name] = before[name]


def restart_notes():
    """What a code reload can't pick up, for the Rebuild panel's notes."""
    notes = []
    changed = [name for name in SERVER_FILES
               if _digest(name) != _started[name]]
    if changed:
        notes.append('{0} changed since the preview started: restart the '
                     'preview to use {1}'.format(
                         ', '.join(changed),
                         'it' if len(changed) == 1 else 'them'))
    stale = []
    for name in DEPS_FILES:
        built = os.path.join(IMAGE_DEPS_DIR, name)
        if not os.path.exists(built):
            continue
        with open(built, 'rb') as a, \
                open(os.path.join(APP_DIR, name), 'rb') as b:
            if a.read().split() != b.read().split():
                stale.append(name)
    if stale:
        notes.append('{0} changed since the image was built: run docker '
                     'compose build, then restart the preview'.format(
                         ', '.join(stale)))
    return notes


def reload_code():
    """Re-read vars (keeping its state), forget the engine's modules and
    plugins, then import the pipeline again, so the next run uses the code
    on disk now (new plugin folders are found, removed ones are gone).
    Raises whatever the new code raises, e.g. SyntaxError; the page served
    until then stays as it was."""
    refresh_vars()
    for name in list(sys.modules):
        if name in RELOAD or name == 'plugins' or name.startswith('plugins.'):
            del sys.modules[name]
    importlib.invalidate_caches()
    # Import fresh and replace the module object the caller holds, so
    # `pipeline.main` refers to the new code
    return importlib.import_module('pipeline')
