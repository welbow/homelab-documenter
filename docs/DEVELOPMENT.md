# Development

- [Running the tests](#running-the-tests)
- [Working on content quickly](#working-on-content-quickly)
- [Working on the engine with a running preview](#working-on-the-engine-with-a-running-preview)
- [Plugin numbering](#plugin-numbering)
- [Section numbering (seq_number)](#section-numbering-seq_number)
- [Writing a plugin](#writing-a-plugin)

## Running the tests

In the image, as CI does:

```
docker compose run --rm test
```

Extra arguments go to pytest, e.g. `docker compose run --rm test -k host -x`.

Locally (Python 3.12):

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

Any warning fails the run (see `pytest.ini`). `tests/fixtures/example-content`
is a copy of the example content repo, and a test builds it, so the example
and the engine can't drift apart: when you change the example repo, update
the fixture too.

## Working on content quickly

- Use the preview's **Rebuild** button instead of restarting, and untick
  the slow plugins: they reuse their last results.
- Skip slow plugins with `SKIP_PLUGINS=100,500` in `.env` (or `--skip`).
  Skipped runs are marked incomplete and `build` refuses to export them
  without `--force`.
- `LOG_LEVEL=DEBUG` in `.env` shows each plugin's work, and the config with
  secrets masked.
- Plugin-specific tips (e.g. reusing a Bitwarden session in a dev shell)
  are in that plugin's README.

## Working on the engine with a running preview

Normally the preview runs the engine code baked into the image. To try
code changes without restarting, run it on your checkout instead: in
`docker-compose.override.yml`, give the `preview` service the engine
folder as `/app` (the commented example in
`docker-compose.override.yml.example` shows the volumes). Then:

1. `docker compose run --rm --service-ports preview` as usual.
2. Edit a plugin or the engine.
3. In the Rebuild panel, tick **Reload code first** and rebuild (partly or
   fully). The engine and every plugin are imported again, so new plugin
   folders appear and removed ones go; a plugin whose code changed runs
   again even if it's unticked. The panel's notes say which ones did.

- If the new code fails (e.g. a syntax error), the panel shows the error
  and the page from the last good run stays; fix the code and rebuild.
- Kept sessions (e.g. an unlocked vault) and cached results survive a
  reload. The preview server itself isn't reloaded; restart for changes to
  `delivery.py` or `homelab-documenter.py`.
- Without the mount, **Reload code first** is greyed out, with a tooltip
  explaining why.
- The mount is read-only, so the container can't change your checkout.
  The empty `conf/`, `input/`, `output/`, `secrets/` and `build/` folders
  in the engine repo (each holding only a `.gitkeep`) are the mount points
  Docker needs inside it; anything else put in them is ignored by git.
- Your checkout's `.env` is visible inside the container through the
  mount (nothing reads it there). It shouldn't hold secrets anyway; see
  Credentials in the main README.

## Plugin numbering

Plugins live in `plugins/NNN-name/` and run in order of `NNN`. The ranges
are in [plugins.md](plugins.md). A few things the list doesn't spell out:

- Hand-written input (static pages at 010, host overrides at 050) runs
  before host discovery (100+), so what a person wrote wins when sources
  disagree.
- The table of contents (950) has to run right before the final output
  (990): after every plugin that adds sections, including the appendix
  renderers (900-949), or those sections won't be in it. Anything that
  adds sections must be numbered below 950.
- Plugins with the same number (e.g. the two 900s) run in folder-name
  order.

## Section numbering (seq_number)

Every section has a `seq_number` (from config.json, or the plugin's folder
number by default), and the packet shows sections in that order. It's
independent of when the plugin runs: the table of contents runs at 950 but
usually sits near the top (`"005"`).

Sorting is numeric (`5` before `10`; non-numbers last, with a warning).
Three digits are a readable convention. A typical layout:

| seq_number | Section |
|---|---|
| 002 | Banner (e.g. confidentiality notice, `hide_surround`) |
| 005 | Table of contents |
| 010-899 | Your pages and plugin sections |
| 950 | Appendix: devices |
| 960+ | Appendices: credentials |

Each section's key is `<seq_number>-<keyname>`, which is also its anchor
in the page (e.g. `#010-static-file-start-here`). Sections sharing a
`seq_number` appear side by side, ordered by key. If a plugin adds a key
that's already taken, the later section replaces the earlier and a warning
names both, so give each section its own number or key name.

## Writing a plugin

A plugin is a numbered folder under `plugins/` with an `__init__.py` that
defines a subclass of `Plugin` and a `getPlugin()` function. Pick the
number from [Plugin numbering](#plugin-numbering).

```python
from Plugin import Plugin
import credentials


class ExampleDevices(Plugin):
    def run(self):
        if not self.getConfig():          # section missing or not enabled
            return
        token = credentials.get('example_token')   # decrypted in memory
        for device in fetch(self._config['url'], token):
            self.addHost(device.ip, source='example',
                         hostname=device.name, type='IoT')
        self.addOutput('<p>Found some devices.</p>', title='Devices',
                       seq='400')


def getPlugin():
    return ExampleDevices()
```

- `getConfig()` loads `self._config` (the plugin's section of config.json)
  and returns False if the plugin shouldn't run.
- `addOutput(output, title, seq, keyname, hide_surround=...)` adds a
  section to the packet; `seq` and `keyname` default to the folder name.
- `addHost(ip, source, **fields)` merges what the plugin knows about a
  host into the device table: blank values never replace real ones, the
  lower-numbered plugin wins a conflict (logged), and `source` shows in
  the Seen by column.
- `credentials.get(name)` returns a stored credential (or None); tell
  users to store it with `docker compose run --rm secrets set <name>`.
  Never log it or put it on a command line or in an environment variable
  that outlives the call.
- `getInputFilePath(name)` is `input/<ClassName>/<name>` in the content
  repo.
- Set `expensive = True` on the class if it's slow or logs in to
  something; the Rebuild panel then leaves it unticked by default and
  reuses its last results. Its sections, credentials and `addHost` calls
  are recorded automatically during a preview.
- If the plugin logs in to something, log out and clean up in a `finally`
  block. During a preview (`vars.keep_alive`), a session may stay open for
  the Rebuild button if you register its cleanup in `vars.cleanups`.
- Add a `README.md` next to `__init__.py` like the existing ones (purpose,
  config keys with an example, input files, credential names, what it
  adds, gotchas), and tests under `tests/`.
