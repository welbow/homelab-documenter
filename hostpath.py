"""Name paths the way the user sees them on their own machine, not as the
container sees them: "Docker volume homelab-documenter-keys" rather than
/keys, "C:\\Users\\...\\secrets" rather than /app/secrets. Read from the
kernel's mount table; anything it can't map is shown as it is."""
import os
import posixpath
import re

MOUNTINFO = '/proc/self/mountinfo'
VOLUME = re.compile(r'/volumes/([^/]+)/_data$')
# Docker Desktop's file sharing: the mount point's root is the host path
SHARED_FS = ('9p', 'virtiofs', 'fuse.grpcfuse', 'fakeowner')


def _unescape(field):
    # mountinfo escapes spaces, tabs, newlines and backslashes as \ooo
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), field)


def _mounts(mountinfo):
    try:
        with open(mountinfo, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    mounts = []
    for line in lines:
        fields = line.split()
        if ' - ' not in line or len(fields) < 5:
            continue
        before, after = line.split(' - ', 1)
        before, after = before.split(), after.split()
        mounts.append({'root': _unescape(before[3]),
                       'point': _unescape(before[4]),
                       'fstype': after[0] if after else '',
                       'source': _unescape(after[1]) if len(after) > 1 else ''})
    return mounts


def describe(path, mountinfo=MOUNTINFO):
    """path as the user would recognise it on the host, if it can tell."""
    path = posixpath.normpath(path)
    best = None
    for m in _mounts(mountinfo):
        point = m['point'].rstrip('/') or '/'
        if point != '/' and (path == point or path.startswith(point + '/')):
            if best is None or len(point) > len(best['point']):
                best = m
    if best is None:
        return path
    rest = path[len(best['point'].rstrip('/')):]

    volume = VOLUME.search(best['root'])
    if volume:
        where = 'Docker volume {0}'.format(volume.group(1))
        return where if not rest.strip('/') else '{0} ({1})'.format(
            posixpath.basename(path), where)

    if best['fstype'] in SHARED_FS and best['root'].startswith('/'):
        host = (best['root'].rstrip('/') + rest) or '/'
        # Docker Desktop on Windows: source is the drive, e.g. "C:\"
        drive = re.match(r'^([A-Za-z]:)', best['source'])
        if drive:
            return drive.group(1) + host.replace('/', '\\')
        return host
    return path


def join(directory, name):
    """describe() of a file in directory, with the host's separator."""
    where = describe(directory)
    sep = '\\' if re.match(r'^[A-Za-z]:\\', where) else '/'
    if where.startswith('Docker volume'):
        return '{0} in {1}'.format(name, where)
    return where.rstrip(sep) + sep + name.replace('/', sep)
