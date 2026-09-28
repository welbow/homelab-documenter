# PortMap (800)

Joins up what the discovery plugins found about devices and their
interfaces: which switch port each host is plugged into, and which
interfaces face each other. On by default; it has nothing to do until a
plugin reports device interfaces (e.g. [OPNsense](../150-opnsense/README.md),
or a switch plugin).

```json
"PortMap": {"enabled": 0}
```

Only needed to turn it off. It runs on every rebuild, after all discovery
(its number is in the 800s, see [plugins.md](../../docs/plugins.md)).

**What it does**
- **Neighbours:** when a device reports the neighbour on one of its
  interfaces (CDP/LLDP: "fw igb1"), the neighbour's interface is linked
  back, if that device is known. Long and short interface names match
  (`GigabitEthernet1/0/5` = `Gi1/0/5`).
- **Hosts on ports:** each MAC address a switch learned on a port is matched
  with the hosts' MAC addresses (from the firewall's ARP table, DHCP). A
  MAC seen on several ports belongs to the one with the fewest other MACs,
  the port it's plugged into rather than the uplinks it was also seen on;
  ports facing another known device are uplinks and skipped.
- The host's row in the device table gets **Connected to** (e.g.
  `core-sw Gi1/0/5`), or `core-sw Gi1/0/7 (shared)` when several devices
  are on that port (an access point or an unmanaged switch behind it).
- A host alone on a port gets the port's description as its **Name**,
  unless something else named it; a host override always wins.
