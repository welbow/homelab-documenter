# Configuration

`conf/config.json` has one section per plugin under `"plugins"`, keyed by
the plugin's class name. A plugin runs only if its section exists and has
`"enabled": 1`. Each plugin's README lists its keys; a minimal file:

```json
{
  "log_level": "INFO",
  "plugins": {
    "StaticFile": {"enabled": 1, "files": [
      {"seq_number": "010", "title": "Start here", "file": "start-here.html"}
    ]},
    "TableOfContents": {"enabled": 1, "seq_number": "005", "title": "Contents"},
    "HTMLOutput": {"enabled": 1, "outputfile": "homelab-packet-{date}.html",
                   "stylesheets": ["standard.css"]}
  }
}
```

**Section order.** Every section has a `seq_number`, and the packet is
sorted by it. Sorting is by text, so use three-digit numbers throughout
(`"005"`, `"010"`, `"950"`); a mix like `5` and `10` sorts out of order.

**Environment** (`.env`, all optional):

| Variable | Meaning |
|---|---|
| `LOG_LEVEL` | `DEBUG`, `INFO` (default), `WARNING`, `ERROR`. Overrides `"log_level"` in config.json. DEBUG also logs the config, with anything that looks secret masked. |
| `SKIP_PLUGINS` | Plugins to skip, comma-separated (see `--skip` above). |
| `TZ` | Time zone for the stamp, e.g. `America/New_York` (default UTC). |

Each plugin's settings are in its README; see the plugin table in the
[main README](../README.md#plugins).
