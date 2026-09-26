# NmapPingScan (100)

Finds the live hosts on your subnets with an nmap ping scan, and their
names from reverse DNS.

```json
"NmapPingScan": {
  "enabled": 1,
  "subnets": ["192.0.2.0/24", "198.51.100.0/24"]
}
```

| Key | Required | Meaning |
|---|---|---|
| `subnets` | yes | Networks to scan, in CIDR form. |

**Adds** to the host table (via `addHost`, Seen by **nmap**): IP address,
hostname (when reverse DNS knows it) and subnet. The network and
broadcast addresses of each subnet are skipped.

**Under Docker Desktop (Windows/macOS)**
- The scan uses ICMP echo only (`-sn -PE --disable-arp-ping`). A plain
  `nmap -sn` also sends TCP probes, which Docker Desktop's network proxy
  answers for every address, so every address would look "up".
- A device that doesn't answer pings is missed. List it in
  [HostOverrides](../050-host-overrides/README.md), or use another source.
- No MAC addresses or vendors: nmap needs ARP for those, and ARP can't
  leave Docker's VM, even with host networking. Port scans are unreliable
  there for the same proxy reason, so none are done.

**Hostnames** come from the container's DNS resolver, and Docker's default
one doesn't know your LAN's names. Set your DNS servers with `dns:` in
`docker-compose.override.yml` (see the example file); without it the
Hostname column stays empty.
