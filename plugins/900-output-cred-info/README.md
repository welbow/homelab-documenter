# OutputCredInfo (900)

Renders the credential tables collected by password-manager plugins
(currently [BitwardenPasswords](../500-bitwarden-passwords/README.md)):
one section per table, with the title, header and position the collecting
plugin was configured with. Without such a plugin it adds nothing.

```json
"OutputCredInfo": {"enabled": 1}
```

No other keys. Columns: Name, Type, Folder, Username, Password,
Multi-Factor, URL. In print, rows don't split across pages and the header
row repeats on each page.
