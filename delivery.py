"""Getting the generated page to people: --preview serves it on the local
machine until Ctrl-C, --export copies it (plus the extra files in output/)
to a folder such as a USB stick. Nothing else writes a durable copy."""
import fnmatch
import functools
import http.server
import logging
import os
import posixpath
import shutil

import hostpath

logger = logging.getLogger('delivery')

# Names the engine gives its generated page (config outputfile and the
# {date} form suggested for it); such a file among the extras is probably
# an old packet with outdated passwords
PACKET_PATTERNS = ('output.html', 'homelab-packet-*.html')


def extras(extras_dir):
    """The extra files shipped alongside the page (e.g. stylesheets): every
    file in the content repo's output/ folder, as relative paths."""
    found = []
    if not os.path.isdir(extras_dir):
        return found
    for root, dirs, files in os.walk(extras_dir):
        dirs.sort()
        for name in sorted(files):
            found.append(os.path.relpath(os.path.join(root, name),
                                         extras_dir))
    return found


def is_mount_point(path, mountinfo='/proc/self/mountinfo'):
    """Is something mounted at path (e.g. a bind mount of a USB stick)?
    Reads the kernel's mount table where there is one (Linux, including
    containers), else falls back to os.path.ismount."""
    try:
        with open(mountinfo) as f:
            # Field 5 is the mount point, with spaces etc. octal-escaped
            points = {line.split()[4].encode().decode('unicode_escape')
                      for line in f if len(line.split()) > 4}
    except OSError:
        return os.path.ismount(path)
    # The mount table only exists on Linux, so compare POSIX paths
    if not path.startswith('/'):
        path = posixpath.join(os.getcwd(), path)
    return posixpath.normpath(path) in points


def looks_like_packet(path):
    name = os.path.basename(path).lower()
    return any(fnmatch.fnmatch(name, p) for p in PACKET_PATTERNS)


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the build dir, falling back to the extras folder, and sends /
    to the page."""

    def __init__(self, *args, page=None, extras_dir=None, **kwargs):
        self.page = page
        self.extras_dir = extras_dir
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        built = super().translate_path(path)
        if os.path.exists(built) or not self.extras_dir:
            return built
        relative = os.path.relpath(built, self.directory)
        return os.path.join(self.extras_dir, relative)

    def do_GET(self):
        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', '/' + os.path.basename(self.page))
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        logger.debug(fmt % args)


def make_server(page, extras_dir, host, port):
    handler = functools.partial(Handler, page=page, extras_dir=extras_dir,
                                directory=os.path.dirname(page))
    return http.server.ThreadingHTTPServer((host, port), handler)


def preview(page, extras_dir, host='127.0.0.1', port=8000):
    """Serve the page until Ctrl-C."""
    server = make_server(page, extras_dir, host, port)
    logger.info('Preview at http://127.0.0.1:{0}/ (Ctrl-C to stop)'.format(
        port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    logger.info('Preview stopped')


def export(page, extras_dir, target, skipped=(), force=False,
           require_mount=False):
    """Copy the page and every extra file into target, listing each one.
    Refuses (returns False) if plugins were skipped, unless force, and,
    with require_mount, if nothing is mounted at target (in a container
    that would write into the container, where the copy is lost)."""
    if require_mount and not is_mount_point(target):
        logger.error('Not exporting: nothing is mounted at {0}. Mount the '
                     'export folder (e.g. a USB stick) there; see '
                     'docker-compose.override.yml.example.'.format(target))
        return False

    if skipped and not force:
        logger.error('Not exporting: this run skipped {0}, so the packet is '
                     'incomplete. Run without skipping, or add --force.'
                     .format(', '.join(skipped)))
        return False
    if skipped:
        logger.warning('Exporting an incomplete packet (skipped {0}) '
                       'because of --force'.format(', '.join(skipped)))

    if not os.path.isdir(target):
        logger.error('Not exporting: {0} is not a folder'.format(
            hostpath.describe(target)))
        return False

    copies = [(page, os.path.basename(page))]
    for name in extras(extras_dir):
        if name == os.path.basename(page):
            logger.warning('Not copying extra file {0}: the generated page '
                           'has the same name'.format(name))
            continue
        copies.append((os.path.join(extras_dir, name), name))

    for source, name in copies:
        destination = os.path.join(target, name)
        if source != page and looks_like_packet(name):
            logger.warning('Extra file {0} looks like an old generated packet '
                           '(outdated passwords?); delete it from output/ if '
                           'it should not be handed out'.format(name))
        if os.path.exists(destination):
            logger.warning('Replacing {0}'.format(hostpath.join(target, name)))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copyfile(source, destination)
        logger.info('Exported {0}'.format(hostpath.join(target, name)))

    logger.info('Exported {0} file(s) to {1}'.format(
        len(copies), hostpath.describe(target)))
    return True
