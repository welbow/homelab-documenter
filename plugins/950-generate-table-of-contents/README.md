# TableOfContents (950)

Builds a numbered table of contents linking to every section, in packet
order.

It has to run right before the final output (990): after every plugin
that adds sections, including the output plugins that render the device
and credential tables (900), so the contents list captures everything.
Keep any new section-adding plugin numbered below 950 (see
[plugin numbering](../../docs/DEVELOPMENT.md#plugin-numbering)).
Where the table appears in the packet is set separately, by its
`seq_number`.

```json
"TableOfContents": {"enabled": 1, "seq_number": "005", "title": "Contents"}
```

| Key | Required | Meaning |
|---|---|---|
| `title` | yes | Section heading. |
| `seq_number` | yes | Its own position, usually near the top. |

Sections added with `hide_surround` (e.g. a confidentiality banner) are
left out.
