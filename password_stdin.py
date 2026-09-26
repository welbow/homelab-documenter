"""--password-stdin: the Bitwarden master password piped in on standard
input (e.g. from scripts/bw-password.ps1), so it never has to be in a
file, an environment variable or on a command line."""


def read(stream):
    """The first line of stream (bytes), as text: UTF-8 with any byte-order
    mark and the line ending removed. Raises ValueError if stream is a
    terminal or holds no password."""
    if stream.isatty():
        raise ValueError('--password-stdin needs the password piped in '
                         '(e.g. from scripts/bw-password.ps1), not typed at '
                         'a terminal; run without it to be prompted')
    line = stream.buffer.readline() if hasattr(stream, 'buffer') \
        else stream.readline()
    # Windows PowerShell may add a byte-order mark and CRLF
    password = line.decode('utf-8-sig').rstrip('\r\n')
    if not password:
        raise ValueError('--password-stdin: nothing was piped in')
    return password
