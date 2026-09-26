# Troubleshooting

Problems specific to one plugin are in that plugin's README (e.g. version
or login issues); the list below links to them where relevant.

- **No hostnames in the device table**: the container needs your LAN's DNS
  servers. Set `dns:` in `docker-compose.override.yml` (see the example).
- **Hosts missing, or a scan finds everything "up"**: see the
  [NmapPingScan notes](../plugins/100-nmap-ping-scan/README.md) on Docker
  Desktop.
- **"Credential ... is set, but this install has no key"**: the key volume
  was reset. Run `secrets set` again for each credential listed.
- **"nothing is mounted at /export"**: add the export folder to the `build`
  service in `docker-compose.override.yml`.
- **A plugin fails to log in**: see that plugin's README (e.g.
  [BitwardenPasswords](../plugins/500-bitwarden-passwords/README.md#gotchas)
  for CLI vs server versions).
