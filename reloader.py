"""Reloading the engine's code during a preview (#25), so edits show up on
the next rebuild without restarting the container. It only helps when the
engine folder is mounted over /app (see docker-compose.override.yml.example);
otherwise the container runs the code baked into the image."""
import importlib
import os
import sys

import delivery

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Reloaded: the pipeline, the plugin base class, their helpers, and every
# plugin. Kept: vars (the state a preview carries between runs, including
# kept sessions and cached results), the preview server (delivery, which is
# serving the request), and this module.
RELOAD = ('pipeline', 'Plugin', 'credentials', 'hostpath', 'stamp',
          'logconfig', 'stdin_value')


def available():
    """(True, '') if reloading can pick up edits, else (False, why)."""
    if delivery.is_mount_point(APP_DIR):
        return True, ''
    return False, ('The engine code is baked into the image, so there is '
                   'nothing new to load. Mount the engine folder over /app '
                   '(see docker-compose.override.yml.example) to use this.')


def reload_code():
    """Forget the engine's modules and plugins, then import the pipeline
    again, so the next run uses the code on disk now (new plugin folders are
    found, removed ones are gone). Raises whatever the new code raises on
    import, e.g. SyntaxError; the page served until then stays as it was."""
    for name in list(sys.modules):
        if name in RELOAD or name == 'plugins' or name.startswith('plugins.'):
            del sys.modules[name]
    importlib.invalidate_caches()
    # Import fresh and replace the module object the caller holds, so
    # `pipeline.main` refers to the new code
    return importlib.import_module('pipeline')
