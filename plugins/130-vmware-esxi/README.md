# VMwareESXi (130)

Reads **VMware ESXi** hosts through the vSphere API on the host itself (no
vCenter needed), as a read-only user. VMware only; Proxmox would be a
plugin of its own.

```json
"VMwareESXi": {
  "enabled": 1,
  "hosts": [{"host": "esxi01.example.com"}],
  "verify_tls": 0,
  "section": {"title": "VMware Virtual Machines", "seq_number": "040"}
}
```

| Key | Required | Meaning |
|---|---|---|
| `hosts` | yes | One entry per ESXi host: `{"host": ...}` (or just the name as a string), plus any of the settings below for that host only. |
| `verify_tls` / `ca_file` | no | ESXi's certificate is self-signed: `ca_file` is a copy of it (PEM) in the content repo's `conf/`, or `"verify_tls": 0` skips the check (with a warning each run). |
| `username_secret`, `password_secret` | no | The credentials to log in with. Default `vmware_esxi_username` and `vmware_esxi_password`. |
| `port`, `timeout` | no | HTTPS port (443), seconds to wait (30). |
| `section` | no | The VMware Virtual Machines section: `title` (default "VMware Virtual Machines"), `seq_number` (default `040`, near the top like the Networks section) and `header`; `0` leaves it out (the device table still gets the VMs). |

**Credentials:** `hd secret set vmware_esxi_username` and
`hd secret set vmware_esxi_password`.

**Adds**
- Each host as a device of type `hypervisor`: model, ESXi version, serial,
  its management interfaces (vmk) with a row per address in the device
  table (Seen by **VMwareESXi**), and its physical NICs (vmnic), so the
  [port map](../800-port-map/README.md) shows which switch port each is on.
- Each VM with an address (from VMware Tools) as a row in the device table:
  type `VM`, the VM's name as its Name, hostname, MAC, and Connected to
  `<host> · <port group>`.
- The **VMware Virtual Machines** section: per host its model and version,
  the web interface link and each datastore's free space, then every VM
  (powered-off ones too): power, autostart, guest OS, addresses, CPU/RAM,
  disks and datastores, network, and the VM's notes (the Notes field in
  ESXi, a good place to say what a VM is for).
- **Autostart:** VMs set to start with the host, in their order
  (`#1, after 120s`), come first, then `yes (any order)`, then the ones
  that don't start by themselves (`no`). If autostart is off for the whole
  host, the section says so: nothing comes back by itself after a power
  cut.

## Setting up access

A dedicated local user with the built-in **Read-only** role (it can't
change anything; this works on the free license too). In the ESXi web
interface (`https://<host>/ui`):

1. **Host > Manage > Security & users > Users > Add user**, e.g.
   `svc-homelab-docs`, with a long random password.
2. **Host > Actions > Permissions > Add user**: that user, role
   **Read-only**, and tick "Propagate to all children".
3. Store the credentials:
   ```
   hd secret set vmware_esxi_username
   hd secret set vmware_esxi_password
   ```

## Errors

| Message | What to do |
|---|---|
| `credential ... not set` | Store it (above). |
| `rejected the login` | Wrong username or password. |
| `refused ...: give the user the Read-only role` | Add the permission (step 2). |
| `the TLS certificate ... was not trusted` | Set `ca_file`, or `"verify_tls": 0`. |
| `can't reach ...` | Check `host`, and that the engine's machine can reach it on 443. |
