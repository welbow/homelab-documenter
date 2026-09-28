# CiscoSwitches (120)

Reads **Cisco switches** over SNMP: each switch's ports, its MAC address
table, port-channels and CDP/LLDP neighbours, for the device table's
**Connected to** column and the **Switch Ports** section (both from
[PortMap](../800-port-map/README.md)). Cisco only: MIBs differ between
vendors. Tested with a Catalyst 2960 (classic IOS) and a CBS350.

```json
"CiscoSwitches": {
  "enabled": 1,
  "switches": [
    {"host": "192.0.2.11"},
    {"host": "192.0.2.12"}
  ]
}
```

| Key | Required | Meaning |
|---|---|---|
| `switches` | yes | One entry per switch: `{"host": ...}` (or just the address as a string), plus any of the settings below for that switch only. |
| `version` | no | `"2c"` (default) or `"3"`. |
| `community_secret` | no | v2c: the credential holding the community. Default `cisco_switches_snmp_community`. Set it (here or per switch) to share one credential with another plugin, or to use a different community per switch. |
| `user`, `auth_protocol`, `priv_protocol` | v3 | The SNMPv3 user; `SHA` (default), `SHA256` or `MD5`; `AES` (default), `AES256`, `DES` or `none`. |
| `auth_secret`, `priv_secret` | no | v3: the credentials holding the passwords. Default `cisco_switches_snmp_auth_password` and `cisco_switches_snmp_priv_password`. |
| `port`, `timeout`, `retries` | no | UDP port (161), seconds per request (5), retries (1). |

**Credentials** (v2c): `hd secret set cisco_switches_snmp_community`
(one community for all switches, unless `community_secret` says otherwise).
v3: `cisco_switches_snmp_auth_password` and, with privacy,
`cisco_switches_snmp_priv_password`.

**SNMP v2c sends the community in clear text.** Use a read-only community,
allow it only from the machine the engine runs on (an ACL), and keep the
switches' management addresses on a management network. v3 with privacy
encrypts everything.

**Adds**
- Each switch as a device of type `switch`, with its model, its L3
  interfaces (VLAN interfaces with an address) and a row per address in
  the device table (Seen by **CiscoSwitches**). Ports aren't device
  interfaces; they have their own table.
- Each port: description, status (`disabled` when shut down), speed (when
  up), VLAN, mode (access/trunk), its port-channel if it's a member, and
  its CDP or LLDP neighbour.
- The MAC addresses learned on each port, with their VLAN.

**How it reads the switches**
- Interfaces: IF-MIB (name, description, status, speed, MAC); the switch's
  addresses: IP-MIB.
- MAC table: Q-BRIDGE-MIB where the switch has it (CBS350). Otherwise
  BRIDGE-MIB once per VLAN, as Catalyst classic IOS keeps a table per VLAN:
  community `<community>@<vlan>` on v2c, context `vlan-<vlan>` on v3
  (VLANs from CISCO-VTP-MIB).
- Port-channels: IEEE8023-LAG-MIB (LACP) and CISCO-PAGP-MIB (PAgP).
- VLAN and mode: CISCO-VLAN-MEMBERSHIP-MIB and CISCO-VTP-MIB (2960), or the
  port's Q-BRIDGE PVID (CBS350; mode isn't shown there).
- Neighbours: CISCO-CDP-MIB, then LLDP-MIB.

## Setting up SNMP

Classic IOS (2960), read-only, allowed from one address:

```
access-list 10 permit 192.0.2.50
snmp-server community <community> RO 10
```

CBS350 (CLI; also under Security > SNMP in the web UI):

```
snmp-server community <community> ro 192.0.2.50 view Default
```

Then store the community: `hd secret set cisco_switches_snmp_community`.

## Errors

| Message | What to do |
|---|---|
| `credential ... not set` | Store it (above). |
| `no answer from <switch> (SNMP v2c, port 161)` | Check the address, that SNMP is on, that its ACL allows the engine's machine, and the community. A wrong community looks the same as no answer: SNMP stays silent. |
| `SNMP version ...: use "2c" or "3"` | Fix `version`. |
