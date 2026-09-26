# ConfigLoader (001)

Reads `conf/config.json` from the content repo into the shared config that
every other plugin uses. It always runs first and can't be skipped or
disabled; it has no section of its own in config.json.

**Reads**
- `conf/config.json`
- `"log_level"` at the top level of config.json: the log level when
  `LOG_LEVEL` isn't set in the environment (`DEBUG`, `INFO`, `WARNING`,
  `ERROR`; default `INFO`).

**Adds** nothing to the packet. At DEBUG it logs the config, with any value
whose key mentions a secret, password, token, client id or API key masked.
