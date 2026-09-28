# Configuration

`conf/config.json` has one section per plugin under `"plugins"`, keyed by
the plugin's class name. A plugin runs only if its section exists and has
`"enabled": 1`. Each plugin's README lists its keys; a minimal file:

```json
{
  "log_level": "INFO",
  "plugins": {
    "StaticFile": {"enabled": 1, "files": [
      {"seq_number": "010", "title": "Start Here", "file": "start-here.html"}
    ]},
    "TableOfContents": {"enabled": 1, "seq_number": "005", "title": "Contents"},
    "HTMLOutput": {"enabled": 1, "outputfile": "homelab-packet-{date}.html",
                   "stylesheets": ["standard.css"]}
  }
}
```

**Section order.** Every section has a `seq_number`, and the packet is
sorted by it as a number: `5` comes before `10`, and `"005"`, `5` and
`"5"` are the same position. Numbers or strings both work. Three digits
(`"005"`, `"010"`, `"950"`) keep config.json easy to scan, but they're a
style choice, not a requirement. A `seq_number` that isn't a number sorts
after all the numbered sections, with a warning.

**Environment** (`.env`, all optional):

| Variable | Meaning |
|---|---|
| `LOG_LEVEL` | `DEBUG`, `INFO` (default), `WARNING`, `ERROR`. Overrides `"log_level"` in config.json. DEBUG also logs the config, with anything that looks secret masked. |
| `SKIP_PLUGINS` | Plugins to skip, comma-separated (see `--skip` above). |
| `TZ` | Time zone for the stamp, e.g. `America/New_York` (default UTC). |

Each plugin's settings are in its README; see the plugin table in the
[main README](../README.md#plugins).
