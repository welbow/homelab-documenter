# MSDHCP (110)

Reads a **Microsoft DHCP server** (the DHCP role on Windows Server) and
adds what it knows to the device table. It's for this one brand of DHCP
server only; OPNsense's own DHCP is read by [OPNsense](../150-opnsense/README.md).

- **Active leases:** IP address, MAC address, and the name the device gave
  when it asked for an address. That includes devices that don't answer
  pings (which nmap misses).
- **Reservations:** devices with a reserved address, even when they're
  offline, with the reservation's name and description in Notes.
- **Scopes:** each scope's description becomes the purpose of that network
  in the OPNsense Networks section (unless config.json gives one there).

Two ways to read the server; both use the same script,
[msdhcp-export.ps1](msdhcp-export.ps1), so they give the same result:

| Mode | How | Needs |
|---|---|---|
| `winrm` (default) | The engine runs the script on the server over WinRM with PowerShell remoting (like `Invoke-Command`), every run. | WinRM on the server (on by default on Windows Server), a read-only account, its credentials stored here. |
| `file` | You run the script on the server (e.g. a scheduled task) and put its JSON in the content repo. | Nothing in the engine; the data is as fresh as the last export. |

```json
"MSDHCP": {
  "enabled": 1,
  "mode": "winrm",
  "server": "dc1.example.com"
}
```

| Key | Required | Meaning |
|---|---|---|
| `mode` | no | `winrm` (default) or `file`. |
| `server` | winrm | The DHCP server's name (or IP address). |
| `transport` | no | `ntlm` (default): WinRM over HTTP, port 5985, with the session encrypted by NTLM. `https`: port 5986, needs an HTTPS listener with a certificate. |
| `port` | no | If WinRM listens on another port. |
| `verify_tls` / `ca_file` | no | With `https`: as for [OPNsense](../150-opnsense/README.md) (`ca_file` is a PEM in `conf/`). |
| `timeout` | no | Seconds to wait (default 30). |
| `file` | no | With `file`: the export's name in `input/MSDHCP/` (default `msdhcp-export.json`). |
| `max_age_days` | no | With `file`: warn when the export is older than this (default 7; `0` never warns). |
| `scopes` | no | Only these scopes, by scope ID, e.g. `["192.0.2.0"]`. Default all. |
| `reservation_notes` | no | `0` leaves reservations' names and descriptions out of Notes. |

**Credentials** (`winrm` only): `msdhcp_username` (`DOMAIN\user` or
`user@domain.example.com`; `.\user` for a local account on a server that
isn't a domain controller) and `msdhcp_password`.

**Adds** to the device table (via `addHost`, Seen by **MSDHCP**): MAC
address, hostname, subnet; Notes for reservations. Expired, declined and
offered leases are skipped. Runs after nmap and before OPNsense: what
[HostOverrides](../050-host-overrides/README.md) says wins, then nmap's
name (from DNS, which a Microsoft DHCP server usually updates, so they
agree).

## Setting up `winrm`

Use a dedicated account that can read DHCP and use WinRM, and nothing
else: members of **DHCP Users** can read the DHCP server but not change
it, and **Remote Management Users** can connect over WinRM without being
administrators.

On a **domain controller** (both groups are domain groups there, and there
are no local accounts), in PowerShell as a domain admin:

```powershell
$password = Read-Host -AsSecureString 'Password for svc-homelab-docs'
New-ADUser -Name 'svc-homelab-docs' -AccountPassword $password -Enabled $true `
    -PasswordNeverExpires $true -CannotChangePassword $true `
    -Description 'homelab-documenter service account (read-only)'
Add-ADGroupMember -Identity 'DHCP Users' -Members 'svc-homelab-docs'
Add-ADGroupMember -Identity 'Remote Management Users' -Members 'svc-homelab-docs'
```

On a **member or standalone server**, use a domain account as above, or a
local one: `New-LocalUser`, then `Add-LocalGroupMember` to the same two
groups on that server.

Then let DHCP Users reach the DHCP part of WMI over WinRM. The DHCP
cmdlets go through WMI (Windows' management layer; WinRM is only the
connection), and WMI only admits a remote login to a namespace with
"Remote Enable", which only administrators have by default (without it:
`Cannot connect to CIM server. Access denied`). The grant is per
namespace, so this opens only the DHCP one, and only to the group that may
read DHCP anyway. On the DHCP server, as an administrator, in Windows
PowerShell:

```powershell
.\grant-dhcp-wmi-access.ps1                               # member server
.\grant-dhcp-wmi-access.ps1 -Group 'EXAMPLE\DHCP Users'   # domain controller
```

[grant-dhcp-wmi-access.ps1](grant-dhcp-wmi-access.ps1) adds Enable Account,
Execute Methods and Remote Enable for the group on
`root/Microsoft/Windows/DHCP` only. It lets the group ask, not change:
what it may do with DHCP is still limited by DHCP Users (read-only). The
same can be done by hand in `wmimgmt.msc` (WMI Control > Properties >
Security > Root > Microsoft > Windows > DHCP > Security: add DHCP Users,
allow Enable Account, Execute Methods and Remote Enable).

Alternatively, grant it to a general-purpose group of your own (e.g. "WMI
Remote Readers", with the service account in it) with `-Group`: a group
grants nothing by itself, since each namespace is granted explicitly, so
it can be reused if other plugins need other namespaces later.

Check it from another Windows machine:

```powershell
Test-WSMan dc1.example.com
Invoke-Command -ComputerName dc1.example.com -Credential EXAMPLE\svc-homelab-docs { Get-DhcpServerv4Scope }
```

Then store the credentials (each command prompts for the value):

```
docker compose run --rm secrets set msdhcp_username
docker compose run --rm secrets set msdhcp_password
```

The container reaches the server by name, so it needs your DNS servers
(`dns:` in `docker-compose.override.yml`, see the NmapPingScan README), or
use the IP address in `server`.

## Setting up `file`

On the DHCP server, run as an account in DHCP Users (e.g. a scheduled
task, daily):

```powershell
powershell -NoProfile -File msdhcp-export.ps1 -OutFile <content repo>\input\MSDHCP\msdhcp-export.json
```

The export is plain JSON with no secrets, but it lists your devices; keep
it in the private content repo like the rest.

## Errors

| Message | What to do |
|---|---|
| `credential ... not set` | Store it (above). |
| `rejected the login` | Wrong username or password, or the account isn't in Remote Management Users. |
| `denied WMI access to the DHCP namespace` | Run grant-dhcp-wmi-access.ps1 on the server (above). |
| `denied reading DHCP: add the account to the DHCP Users group` | Add it; group changes apply to new logins, so it may take a few minutes. |
| `can't reach WinRM on ...` | Check `server`; run `Test-WSMan` against it; the Windows Firewall must allow WinRM (5985/5986) from your Docker host. |
| `the image has no pypsrp` | Rebuild the image: `docker compose build`. |
| `no export at input/MSDHCP/...` | `file` mode: run the export (above). |
