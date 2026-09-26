"""A secret piped in on standard input, for `secrets set` (e.g. from
scripts/bw-password.ps1 -Encrypt), so it never has to be in a file, an
environment variable or on a command line."""


def read(stream):
    """The first line of stream (bytes), as text: UTF-8 with any byte-order
    mark and the line ending removed. Raises ValueError if stream is a
    terminal or holds nothing."""
    if stream.isatty():
        raise ValueError('expected the value piped in, not typed at a '
                         'terminal')
    line = stream.buffer.readline() if hasattr(stream, 'buffer') \
        else stream.readline()
    # Windows PowerShell may add a byte-order mark and CRLF
    value = line.decode('utf-8-sig').rstrip('\r\n')
    if not value:
        raise ValueError('nothing was piped in')
    return value
