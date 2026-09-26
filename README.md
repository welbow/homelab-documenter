# homelab-documenter

Generates an "if something happens to me" packet for a homelab: one HTML
document that tells the people you trust what is running, where it is, how
to get in, and what to do with it. It's meant to be printed and put on a
USB stick, and handed out in advance.

The packet is assembled by a pipeline of plugins: your own hand-written
pages, information about the devices on your network, and (with the right
plugins) data from the systems you run, such as a password manager.
Credentials are stored encrypted, the page is built in memory, and the only
durable copy is the one you export.

Written by an IT guy who hasn't touched Python in 15 years as an exercise
to (re-)learn Python and to document his homelab in the most
[ambitiously-lazy](https://www.redhat.com/sysadmin/what-automate-first)
way possible.

## Contents

- [How it fits together](#how-it-fits-together)
- [Quick start](#quick-start)
- [Everyday use](#everyday-use)
- [Credentials](#credentials)
- [Configuration](#configuration)
- [Plugins](#plugins)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)
- [Development](docs/DEVELOPMENT.md)

## How it fits together

Two repositories:

- **This repo, the engine**: the code, the Docker image and the plugins.
  Nothing specific to anyone's environment lives here.
- **A content repo per environment** (keep it private): its
  configuration, its pages and its encrypted credentials. Start from the
  example content repo (see Quick start).

```
my-homelab-content/
  conf/config.json      which plugins run and how (see Configuration)
  input/<Plugin>/       each plugin's input files, e.g. input/StaticFile/*.html
  output/               extra files shipped with the packet, e.g. standard.css
  secrets/*.enc         encrypted credentials (safe to commit, see Credentials)
```

Docker is the supported way to run it, on Windows (Docker Desktop) and
Linux. Running natively on Windows is not supported.

## Quick start

1. Clone this repo, and next to it the example content repo,
   `<forgejo>/jwell/homelab-documenter-example` (placeholder URL until it's
   published). Push your copy of the example to a new **private** repo:
   it becomes your environment's content.

   ```
   homelab-documenter/     <- this repo
   my-homelab-content/     <- your copy of the example
   ```

2. In this repo, copy `docker-compose.override.yml.example` to
   `docker-compose.override.yml` (gitignored) and point it at your content
   repo. It's also where you set your LAN's DNS servers (for hostnames)
   and the export folder (for `build`).

3. Optionally copy `.env.example` to `.env` for settings like `TZ`,
   `LOG_LEVEL` or `SKIP_PLUGINS`. It holds no secrets.

4. Build the image and preview the example packet:

   ```
   docker compose build
   docker compose run --rm --service-ports preview
   ```

   Open <http://127.0.0.1:8000>, read it, print it from the browser (use
   "Save as PDF" for a PDF).

5. Replace the example pages and settings with your own, using the
   preview's Rebuild button to see each change. Turn on the plugins you
   want (see [Plugins](#plugins)) and store the credentials they need (see
   [Credentials](#credentials)).

## Everyday use

Always use `docker compose run --rm`, so no container (and nothing in it)
is left behind.

| Command | What it does |
|---|---|
| `docker compose run --rm --service-ports preview` | Generates the packet and serves it on <http://127.0.0.1:8000> until Ctrl-C. |
| `docker compose run --rm build` | Generates the packet and copies it, plus everything in `output/`, to the folder mounted at `/export`. |
| `docker compose run --rm secrets <set\|list\|check\|remove> [name]` | Manages encrypted credentials. |

**Preview.** The page is generated in memory (a tmpfs) and served only on
this machine (127.0.0.1). The **Rebuild** button in the bottom-right corner
opens a panel for re-running after you edit your content, without
restarting: tick the plugins to run again and the others reuse their
results from the last run (slow ones such as network scans and password
managers are unticked by default), or rebuild everything. A plugin whose
config.json section changed runs again regardless. Plugins that log in to
something may keep their session open until you stop the preview. The
button is added only to the page being served, never to the file, so it
can't end up in a printout or an export.

**Build (export).** `/export` has no mount by default, on purpose: add one
in `docker-compose.override.yml`, e.g. `'E:/:/export'` for a USB stick on
Windows or `'/media/you/USBSTICK:/export'` on Linux. Without it the run
stops with an error instead of writing inside the container. The export
lists every file it copies, warns about anything in `output/` that looks
like an old packet (`output.html`, `homelab-packet-*.html`, which would
hold outdated passwords), and refuses a run that skipped plugins unless
you add `--force`.

**Options.** Anything after the service name is added to its options, e.g.

```
docker compose run --rm --service-ports preview --skip 100
docker compose run --rm build --skip NmapPingScan --force
```

`--skip` (or `SKIP_PLUGINS` in `.env`) skips plugins by number (`100`),
folder (`100-nmap-ping-scan`) or class (`NmapPingScan`). Every skip is
logged as a warning, and a run with skips is marked incomplete. The config
loader can't be skipped.

**Stamp.** Every page shows when it was generated and by which engine
version, with a reminder that passwords may have changed since; in print
it's at the bottom of every page (Chrome/Edge). Set `TZ` (e.g.
`America/New_York`) in `.env` for local time. `{date}` in the output file
name (see [HTMLOutput](plugins/990-output-html/README.md)) gives dated
exports like `homelab-packet-2026-09-25.html`, so the newest copy is
obvious.

## Credentials

Any plugin that needs a password, API key or token gets it the same way,
on every OS. Each plugin's README lists the names it uses; for example:

```
docker compose run --rm secrets set example_api_token   # prompts twice, nothing echoed
docker compose run --rm secrets list                    # names only
docker compose run --rm secrets check                   # can each one be decrypted?
docker compose run --rm secrets remove example_api_token
```

Values can also be piped in (`... | docker compose run --rm -T secrets set
name`); they are never printed.

How it works:

- On first use the engine creates a key pair for this install and keeps the
  private key in the Docker volume **homelab-documenter-keys**, not in your
  repos, folders or backups.
- Each credential is `secrets/<name>.enc` in your content repo, encrypted to
  that key (AES-256-GCM, with the AES key sealed by RSA-3072). The files
  are useless without the key volume, so they're safe to commit and back up.
- Plugins decrypt what they need in memory, when they need it.

What that protects against, and what it doesn't:

- A leaked repo, backup or copied `.enc` file reveals nothing.
- Anyone with Docker access on your machine (effectively an admin) or
  malware running as you can use the key. Nothing that runs unattended can
  prevent that.
- If the key volume is lost, `secrets check` says so; set the credentials
  again from wherever you keep the originals.
  The volume is deleted by `docker volume rm homelab-documenter-keys`,
  `docker volume prune --all`, `docker compose down -v`, uninstalling
  Docker, or Docker Desktop's "Clean / Purge data" and "Reset to factory
  defaults". Restarts, updates, image rebuilds, plain `docker compose
  down` and plain `docker volume prune` / `docker system prune --volumes`
  (anonymous volumes only, on Docker 23+) leave it alone.

## Configuration

`conf/config.json` in your content repo says which plugins run and how;
`.env` holds optional engine settings (`LOG_LEVEL`, `SKIP_PLUGINS`, `TZ`).
See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) and each plugin's
README.

## Plugins

Plugins run in the order of their folder numbers. Use the ones that fit
your environment; each is off unless its config section enables it.

| # | Plugin (config key) | What it does |
|---|---|---|
| 001 | [ConfigLoader](plugins/001-config-loader/README.md) | Reads `conf/config.json`; always runs first. |
| 010 | [StaticFile](plugins/010-static-file/README.md) | Adds your hand-written pages. |
| 050 | [HostOverrides](plugins/050-host-overrides/README.md) | Adds hand-written name, type and notes per device. |
| 100 | [NmapPingScan](plugins/100-nmap-ping-scan/README.md) | Finds live hosts on your subnets. |
| 150 | [OPNsense](plugins/150-opnsense/README.md) | Adds devices from an OPNsense firewall's ARP table, with MAC addresses, vendors and interfaces (optional; only if you use OPNsense). |
| 500 | [BitwardenPasswords](plugins/500-bitwarden-passwords/README.md) | Lists the items in a Bitwarden vault (optional; only if you use Bitwarden). |
| 900 | [OutputCredInfo](plugins/900-output-cred-info/README.md) | Renders the credential tables that password plugins collect. |
| 900 | [OutputHostInfo](plugins/900-output-host-info/README.md) | Renders the device table. |
| 950 | [TableOfContents](plugins/950-generate-table-of-contents/README.md) | Builds the table of contents, after every other section exists. |
| 990 | [HTMLOutput](plugins/990-output-html/README.md) | Writes the packet. |

## Security notes

- **Nothing sensitive on disk.** The packet can contain passwords in
  plain text, so it is generated in memory and only ever written where you
  export it. Credentials are stored encrypted (see above). The logs never
  contain secret values.
- **Preview is local only.** It listens on 127.0.0.1, and rebuild requests
  from other web pages are refused.
- **Plugins clean up after themselves.** A plugin that logs in to
  something (e.g. a password manager) logs out and removes its local data
  at the end of every run, even on failure (a preview does this when you
  stop it).
- **Your content repo holds sensitive pages** (e.g. a phone unlock code the
  family will need). Keep them in git deliberately:
  - keep the repo private, with access for you only; no mirrors to public
    hosts, and no CI or dependency bots on it;
  - put secrets only on a few clearly named pages, not scattered through
    the narrative;
  - never put bank PINs or master passwords there; keep those in your
    password manager, and let a plugin bring them into the packet;
  - if something leaks, change it rather than rewriting git history.

## Troubleshooting

Common problems and fixes are in
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

For tests, the plugin numbering scheme and writing your own plugin, see
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
