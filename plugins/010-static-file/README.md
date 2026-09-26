# StaticFile (010)

Adds your hand-written pages to the packet: introductions, instructions,
"how to get into my PC", anything that can't be discovered.

```json
"StaticFile": {
  "enabled": 1,
  "files": [
    {"seq_number": "002", "title": "", "file": "confidential.html", "hide_surround": 1},
    {"seq_number": "010", "title": "Start here", "file": "start-here.html"},
    {"seq_number": "020", "title": "Router notes", "file": "router.txt"}
  ]
}
```

**Each entry in `files`**

| Key | Required | Meaning |
|---|---|---|
| `file` | yes | File name in `input/StaticFile/` in the content repo. |
| `title` | no | Section heading (default "No title specified"). |
| `seq_number` | no | Position in the packet (a number, e.g. `"010"`); default `010`. |
| `key_name` | no | Section key after the number, also used in the page anchor. Default: `static-file-` plus the file name, e.g. `start-here.html` gives `010-static-file-start-here`, so pages sharing a `seq_number` both appear. Two entries with the same number and key replace each other (with a warning). |
| `hide_surround` | no | `1` to show the content without a heading, table-of-contents entry or "Return to top" link, e.g. a confidentiality banner at the top. |

**Input files** (`input/StaticFile/`): a file that contains HTML (any
closing tag like `</p>`) is inserted as is; anything else is treated as
plain text and shown preformatted. Images or stylesheets the pages refer
to go in `output/` so they ship with the packet.

**Adds** one section per file.

**Sensitive pages** (e.g. a phone unlock pattern): see the content-repo
guardrails in the main README's Security notes.
