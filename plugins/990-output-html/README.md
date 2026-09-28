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
| `table_filter` | no | `0` leaves out the autofilter and search box (below). Default on. |

**The page**
- Title, then the generation stamp and "Passwords may have changed since
  this date", again at the very end, and in print at the bottom of every
  page (Chrome/Edge).
- Each section starts on a new printed page. "Return to top" links are
  hidden in print, table rows don't split and table headers repeat. The
  paper size is left to the print dialog.
- On screen, table header rows stay in view while you scroll. Every table
  with more than 10 rows gets an Excel-style autofilter: a button on each
  column header opens sort A to Z / Z to A, a search box, (Select all) and
  a checklist of that column's values (with (Blanks)); filters on several
  columns combine, and a filtered column's button is highlighted. A quick
  search box above the table matches words anywhere in a row, with a
  count ("24 of 77 rows") and Clear filters. Numbers and IP addresses sort
  by value. It works offline from the exported file, and from the
  keyboard (Tab, Enter, Esc). Print hides the controls and shows every
  row, in the original order.
- These styles, the script and the stamp are inline, so they work even if
  the stylesheets are missing.

The page is written to the in-memory build folder, never to `output/`;
`preview` serves it and `build` exports it (see Everyday use in the main
README).
