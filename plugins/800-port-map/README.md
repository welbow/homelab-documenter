# PortMap (800)

Joins up what the discovery plugins found about switch ports, devices and
hosts: which switch port each host (or device interface) is plugged into.
Adds the device table's **Connected to** column and the **Switch ports**
section. On by default; it has nothing to do until a switch plugin (e.g.
[CiscoSwitches](../120-cisco-switches/README.md)) reports ports.

```json
"PortMap": {
  "section": {"title": "Appendix C - Switch ports", "seq_number": "970",
              "header": "Which device is on each switch port"}
}
```

| Key | Required | Meaning |
|---|---|---|
| `enabled` | no | `0` turns it off. |
| `section` | no | The Switch ports section, an appendix like the device and credential tables: `title` (default "Switch ports"; name it like your other appendices, e.g. "Appendix C - Switch ports"), `seq_number` (default `970`, after the device (950) and credential (960+) appendices) and `header`; `0` leaves the section out (Connected to still fills in). |

It runs on every rebuild, after all discovery (its number is in the 800s,
see [plugins.md](../../docs/plugins.md)).

**What it does**
- **Port-channels:** member ports are listed with their channel
  (`Po1 (Gi1/0/47, Gi1/0/48)`), and a member's CDP/LLDP neighbour counts
  for the channel.
- **Uplinks:** a port whose neighbour is a device we know (a switch, the
  firewall) shows it (`Uplink: access-sw Gi0/3`), and the other side learns
  it too. Neighbours don't always send their own name (a CBS350's CDP ID is
  its MAC; OPNsense says "OPNsense" over LLDP), so they're also found by
  the MAC or address they send. Any other neighbour (an IP phone, an access
  point) is shown as `Neighbour: ...`, and what's behind it is still
  placed on the port. If the
  neighbour's interface is known (e.g. the firewall's `igb1`), that
  interface records which switch port it's on. Long and short interface
  names match (`GigabitEthernet1/0/5` = `Gi1/0/5`).
- **Everything else:** each MAC a switch learned is placed on the port
  where it was learned with the fewest other MACs, the port it's plugged
  into rather than the uplinks it was also seen on, and matched with the
  hosts' MAC addresses (from the firewall's ARP table, DHCP) and the
  devices' interfaces.
- The host's row gets **Connected to** (e.g. `core-sw Gi1/0/5`), or
  `core-sw Gi1/0/7 (shared)` when several devices are on that port (an
  access point or an unmanaged switch behind it).
- A host alone on a port gets the port's description as its **Name**,
  unless something else named it; a host override always wins.

**The Switch ports section:** one table per switch, every port (members
under their channel): Port, Description, Status, Speed, VLAN, Mode,
Connected to (the host's name and address, the device interface, or the
uplink's neighbour).
