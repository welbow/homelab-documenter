# homelab-documenter example content

A starting point for your own content repo for
[homelab-documenter](<forgejo>/jwell/homelab-documenter), the engine that
turns it into an "if something happens to me" packet for your homelab.

Everything here is made up (example.com, 192.0.2.x addresses). It builds as
is, with no credentials: the plugins that need them (password manager,
network scan, firewall) are switched off until you set them up.

## Start your own

1. Clone this repo, then push it to a **private** repo of your own (one per
   environment you document). It will hold sensitive pages; see "Keeping
   secrets here" below.
2. Point the engine at it: in the engine repo, copy
   `docker-compose.override.yml.example` to `docker-compose.override.yml`
   and set the paths to your clone.
3. Preview the example packet from the engine repo:
   `docker compose run --rm --service-ports preview`, then open
   <http://127.0.0.1:8000>.
4. Replace the example pages and settings with your own, using the
   preview's Rebuild button to see each change.

## What goes where

```
conf/config.json        which plugins run, and their settings
input/StaticFile/       your hand-written pages (HTML, or plain text)
input/HostOverrides/    host-overrides.csv: names, types and notes per device
output/                 files shipped with the packet, e.g. standard.css
secrets/                encrypted credentials, created by the engine's
                        `docker compose run --rm secrets set <name>`
```

Each plugin's settings and input formats are described in the engine's
`plugins/*/README.md`. Sections appear in `seq_number` order (as numbers,
so 5 comes before 10).

To turn on a plugin that needs credentials (for example a password
manager plugin), set `"enabled": 1` in its section, fill in its settings,
and store what it needs with `docker compose run --rm secrets set <name>`
(its README lists the names).

## Keeping secrets here

Some pages will hold things the people reading the packet need, like a
phone's unlock code. Keeping them in this repo is a deliberate trade-off:

- Keep the repo **private**, with access for you only. No mirrors to public
  hosts, no CI and no dependency bots on it.
- Put secrets only on a few clearly named pages, not scattered through the
  narrative.
- Never put bank PINs or master passwords here; those belong in your
  password manager and reach the packet through its plugin.
- `secrets/*.enc` files are safe to commit: they're encrypted to a key that
  lives only in the engine's Docker volume on your machine.
- Never commit a generated packet: it holds every password in plain text
  (`output/*.html` is ignored for that reason).
- If something leaks, change it rather than rewriting git history.
