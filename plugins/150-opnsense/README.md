# OPNsense (150)

Reads an OPNsense firewall through its REST API:

- its **ARP table**: every device the firewall has talked to recently, on
  every interface and VLAN, with MAC address and vendor. That includes
  devices that don't answer pings (which nmap misses), and MAC addresses
  and vendors, which nmap can't get from inside Docker.
- its **interfaces**: the firewall's own addresses (added as type
  `router`), and the subnet and interface name for each host.
- optionally its **DHCP leases** (Kea or Dnsmasq), for hostnames.

```json
"OPNsense": {
  "enabled": 1,
  "url": "https://192.0.2.1",
  "hostname": "firewall",
  "ca_file": "opnsense-ca.pem",
  "network_section": {"title": "Networks", "seq_number": "040",
                      "header": "The networks the firewall routes",
                      "purposes": {"LAN": "Computers and the file server",
                                   "IoT": "Smart plugs, TVs, cameras"}}
}
```

| Key | Required | Meaning |
|---|---|---|
| `url` | yes | The firewall's web address, as you open it in a browser. |
| `verify_tls` | no | `1` (default) checks the firewall's TLS certificate. `0` turns the check off, with a warning each run; prefer `ca_file`. |
| `ca_file` | no | For a self-signed certificate: the CA (or the certificate itself) as a PEM file in the content repo's `conf/`. |
| `timeout` | no | Seconds to wait for each API call (default 15). |
| `hostname` | no | The firewall's name for its own rows in the device table. Default: what OPNsense calls itself (hostname.domain, needs the `Lobby: Dashboard` privilege). |
| `exclude_interfaces` | no | Interfaces whose devices to leave out of the device table, by name, identifier or device (e.g. `["WAN"]`): no firewall address, ARP entries or leases from them. They stay in the Networks section. The loopback is always left out. |
| `leases` | no | `1` also reads the DHCPv4 leases (see below). Default off. |
| `network_section` | no | Adds a Networks section: one row per assigned interface/VLAN with its subnet, the firewall's address on it (the gateway), VLAN tag and interface. An interface that gets its address by DHCP (e.g. the WAN) says DHCP instead of the current lease. `title`, `seq_number` and `header` as for other sections, and `purposes`: what each network is for, by interface name (e.g. `{"LAN": "Computers and the file server", "IoT": "Smart plugs, TVs, cameras"}`), shown as a Purpose column. Without one, a purpose another plugin knows for that subnet is used (e.g. the [MSDHCP](../110-msdhcp/README.md) scope description). |

**Credentials:** `opnsense_api_key` and `opnsense_api_secret`.

**Adds** to the device table (via `addHost`, Seen by **OPNsense**): MAC
address, vendor, hostname (when the firewall knows it), subnet and
interface for each ARP entry; each of the firewall's interface addresses
as type `router`. Expired and incomplete ARP entries are skipped. As with
any plugin, what [HostOverrides](../050-host-overrides/README.md) says
wins, and [nmap](../100-nmap-ping-scan/README.md) (which runs first) wins
for a hostname both know.

## Setting up access

Use a dedicated API user with only the privileges this plugin needs, not
your admin account.

1. **System > Access > Users**, add a user (e.g. `homelab-documenter`).
   Give it a long random password (it's never used; the API key is), and
   no shell.
2. Give the user these privileges (and no group that grants more):
   - `Diagnostics: ARP Table`
   - `Status: Interfaces`
   - `Lobby: Dashboard`, for the firewall's own name (hostname.domain) on
     its addresses; without it, set `hostname` in config.json, or they
     only get the names reverse DNS knows
   - only with `"leases": 1`, the one for your DHCP server:
     `Services: DHCP: Kea(v4)` or `Services: Dnsmasq DNS/DHCP: Settings`.
     These also allow changing that service's settings (OPNsense has no
     read-only lease privilege), which is why leases are off by default.
3. Create an API key for the user (its **API keys** section; the exact
   place varies a little between versions). The browser downloads a file
   with a `key=` and a `secret=` line.
4. Store both (each command prompts for the value; paste it):
   ```
   hd secret set opnsense_api_key
   hd secret set opnsense_api_secret
   ```
   Then delete the downloaded file.
5. Set `url` in config.json, and `"enabled": 1`.

The firewall's certificate: OPNsense's default web certificate is
self-signed, so the check fails until you trust it. Download it from
**System > Trust > Certificates** (the web GUI certificate, or the CA that
signed it), save it in the content repo's `conf/`, and set `ca_file` to the
file name. The name in the certificate has to match the host in `url`: an
IP address in `url` needs that IP in the certificate.

## Errors

| Message | What to do |
|---|---|
| `credential ... not set` | Store it (step 4). |
| `rejected the API key (401)` | The key or secret is wrong, or the user is disabled. Store them again. |
| `refused ... (403): give the API user the privilege "..."` | Add that privilege (step 2). |
| `the TLS certificate ... was not trusted` | Set `ca_file` (see above). |
| `can't reach ...` / `no answer ... within` | Check `url`, and that the web GUI listens on the interface the engine reaches it through. |

**Versions:** the interface list needs OPNsense 24.1 or later. Without it,
hosts still come in from the ARP table, without subnet or interface (a
warning says so). ISC DHCP leases aren't read (ISC DHCP is end of life);
its hostnames usually reach the ARP table anyway.
