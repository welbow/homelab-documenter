# BitwardenPasswords (500)

Lists the items in your Bitwarden (or Bitwarden-compatible) vault, with
usernames, passwords and URLs, for the credentials appendix.

```json
"BitwardenPasswords": {
  "enabled": 1,
  "server_url": "https://vault.example.com",
  "queries": [
    {"title": "Appendix B - Passwords", "header": "All passwords except work",
     "seq_number": "960", "exclude_folders": ["Work"]},
    {"title": "Appendix C - Home Network", "header": "Network gear",
     "seq_number": "970", "include_folders": "Network"}
  ]
}
```

| Key | Required | Meaning |
|---|---|---|
| `server_url` | yes | Your Bitwarden server (`https://vault.bitwarden.com` for Bitwarden's own cloud). |
| `queries` | yes | One credential table per entry (can be empty). |

**Each query**

| Key | Meaning |
|---|---|
| `title` | Section heading. |
| `header` | Line shown above the table. |
| `seq_number` | Position in the packet (a number). |
| `include_folders` | Only items in this folder, or any of these folders (string or list). |
| `exclude_folders` | Leave out items in this folder / these folders. |

Items without a folder (or whose folder was deleted) count as folder
"No Folder".

**Credentials** (see Credentials in the main README):

| Name | What |
|---|---|
| `bw_clientid`, `bw_clientsecret` | Your personal API key (web vault: Settings > Security > Keys > API Key). Required. |
| `bw_master_password` | Unlocks the vault. Optional: without it, the run asks on the terminal, and fails with a clear message if there isn't one. |

**Adds** credential data that [OutputCredInfo](../900-output-cred-info/README.md)
renders: folder, type (Login, Secure Note, Card, Identity, SSH Key), name,
and for logins username, password, MFA (yes if a TOTP secret is set) and
URLs.

**Sessions**
- Every run locks the vault, logs out and deletes the Bitwarden CLI's data
  at the end, even when it fails.
- During a preview the vault stays unlocked for the Rebuild button, until
  the preview stops.
- In a dev shell, an unlocked `BW_SESSION` is reused and left open, so you
  can unlock once and run repeatedly (the Rebuild button usually makes
  this unnecessary):

  ```
  docker compose run --rm --service-ports --entrypoint sh preview
  bw config server https://vault.example.com
  bw login --apikey                    # asks for the API key
  export BW_SESSION=$(bw unlock --raw)
  python /app/homelab-documenter.py --skip 100
  ```

  Exiting the shell discards the session.

## Gotchas

- **`bw unlock failed: ... key_id_backfill ... 404`** (or other odd API
  errors): the Bitwarden CLI must not be newer than your server. A newer
  CLI can call endpoints an older server doesn't have. The Dockerfile pins
  the CLI (`BW_VERSION`); keep it no newer than your server, or update the
  server. Renovate asks for approval before bumping it.
- `client_id`, `client_secret` and `logout` in config.json are no longer
  used; the plugin warns if they're there.
