# HTMLOutput (990)

Writes the packet: one HTML page with every section in `seq_number` order.

```json
"HTMLOutput": {
  "enabled": 1,
  "outputfile": "homelab-packet-{date}.html",
  "stylesheets": ["standard.css"]
}
```

| Key | Required | Meaning |
|---|---|---|
| `outputfile` | yes | File name of the page. `{date}` becomes the generation date, e.g. `homelab-packet-2026-09-25.html`. |
| `stylesheets` | no | Stylesheets to link, relative to the page. Put them in `output/` in the content repo so they ship with the packet (preview serves them, export copies them). |

**The page**
- Title, then the generation stamp and "Passwords may have changed since
  this date", again at the very end, and in print at the bottom of every
  page (Chrome/Edge).
- Each section starts on a new printed page. "Return to top" links are
  hidden in print, table rows don't split and table headers repeat. The
  paper size is left to the print dialog.
- These print styles and the stamp are inline, so they work even if the
  stylesheets are missing.

The page is written to the in-memory build folder, never to `output/`;
`preview` serves it and `build` exports it (see Everyday use in the main
README).
