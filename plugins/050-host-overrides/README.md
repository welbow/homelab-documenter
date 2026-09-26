# HostOverrides (050)

Adds what no scan can know about a device: a friendly name, what kind of
device it is, and notes for the reader ("safe to unplug", "runs the home
automation"). Runs before the discovery plugins, so what you write wins.

```json
"HostOverrides": {"enabled": 1}
```

| Key | Required | Meaning |
|---|---|---|
| `file` | no | CSV file name in `input/HostOverrides/` (default `host-overrides.csv`). |

**Input** (`input/HostOverrides/host-overrides.csv`), one row per device:

```csv
ip,name,type,notes
192.0.2.1,Router,router,Internet gateway. Don't unplug.
192.0.2.20,Living room TV box,IoT,Safe to replace
```

- `ip` is required; rows without a valid IP are skipped with a warning.
- `type` should be one of `router`, `switch`, `server`, `VM`, `PC`,
  `phone`, `IoT` (any case). Anything else is used as written, with a
  warning in case it's a typo.
- A header-only file is fine, and so is no file at all.
- Excel's "CSV UTF-8" works.

**Adds** to the host table (via `addHost`, Seen by **manual**): the Name,
Type and Notes columns, and the host itself even if no scan finds it.

**Reading the table**
- Seen by "manual" only: you listed it, but nothing found it on the
  network. Offline, moved or gone?
- Type "Unknown": found on the network, but not described yet.

**Later**: matching by MAC address as well as IP (so an entry follows a
device whose DHCP address changes) needs a MAC source such as a DHCP or
switch plugin.
