# OutputHostInfo (900)

Renders the host table from everything the data plugins found
([HostOverrides](../050-host-overrides/README.md),
[NmapPingScan](../100-nmap-ping-scan/README.md), and future sources).

```json
"OutputHostInfo": {
  "enabled": 1,
  "title": "Appendix A - Hosts",
  "header": "Every device found on the network",
  "seq_number": "950"
}
```

| Key | Required | Meaning |
|---|---|---|
| `title` | yes | Section heading. |
| `header` | yes | Line shown above the table. |
| `seq_number` | yes | Position in the packet (a number). |

**Columns**, in this order, each shown only if some host has a value: Name,
Hostname, IP Address, Type (always shown, "Unknown" when no source knows
it), Subnet, MAC Address, Vendor, Seen by, Notes. Hosts are sorted by IP.

**Seen by** lists every source that reported the host, e.g. "manual,
nmap". When sources disagree (two different hostnames), the
lower-numbered plugin's value is kept and the other is logged.
