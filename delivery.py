"""Getting the generated page to people: --preview serves it on the local
machine until Ctrl-C, --export copies it (plus the extra files in output/)
to a folder such as a USB stick. Nothing else writes a durable copy."""
import fnmatch
import functools
import http.server
import json
import logging
import os
import posixpath
import shutil
import threading

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


# Injected by the preview server into the page it serves (never into the
# generated file, so exports and prints don't have it); hidden in print
REBUILD_BUTTON = b"""
<div id="hd-rebuild" style="position:fixed;right:1rem;bottom:1rem;z-index:9999;
  max-width:40rem;padding:.5rem .75rem;background:#fff;border:1px solid #888;
  border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.25);font:14px sans-serif">
  <button type="button">Rebuild</button> <span></span>
</div>
<style>@media print { #hd-rebuild { display: none !important; } }</style>
<script>
(function () {
  var box = document.getElementById('hd-rebuild');
  var button = box.querySelector('button'), note = box.querySelector('span');
  button.onclick = function () {
    button.disabled = true;
    note.textContent = 'Rebuilding...';
    fetch('/rebuild', {method: 'POST'})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) { location.href = d.page; return; }
        button.disabled = false;
        note.textContent = d.error;
      })
      .catch(function (e) { button.disabled = false; note.textContent = String(e); });
  };
})();
</script>
"""


class PreviewState:
    """The page being served, and how to rebuild it (one at a time)."""

    def __init__(self, page, rebuild=None):
        self.page = page
        self.rebuild = rebuild
        self.lock = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the build dir, falling back to the extras folder, sends / to
    the page, and (when a rebuild is possible) adds the Rebuild button to
    the page and handles POST /rebuild."""

    def __init__(self, *args, state=None, extras_dir=None, **kwargs):
        self.state = state
        self.extras_dir = extras_dir
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        built = super().translate_path(path)
        if os.path.exists(built) or not self.extras_dir:
            return built
        relative = os.path.relpath(built, self.directory)
        return os.path.join(self.extras_dir, relative)

    def _page_path(self):
        return '/' + os.path.basename(self.state.page)

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, data):
        self._send(code, json.dumps(data).encode('utf-8'), 'application/json')

    def do_GET(self):
        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', self._page_path())
            self.end_headers()
            return
        if self.state.rebuild and self.path.split('?')[0] == self._page_path():
            with open(self.state.page, 'rb') as f:
                html = f.read()
            at = html.lower().rfind(b'</body>')
            if at == -1:
                at = len(html)
            self._send(200, html[:at] + REBUILD_BUTTON + html[at:],
                       'text/html; charset=utf-8')
            return
        super().do_GET()

    def do_POST(self):
        if self.path != '/rebuild' or not self.state.rebuild:
            self._json(404, {'ok': False, 'error': 'Not found'})
            return
        # Only from the preview page itself, not from other web pages
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self._json(403, {'ok': False, 'error': 'Not allowed'})
            return
        if not self.state.lock.acquire(blocking=False):
            self._json(409, {'ok': False, 'error': 'Already rebuilding'})
            return
        try:
            logger.info('Rebuilding')
            self.state.page = self.state.rebuild()
            self._json(200, {'ok': True, 'page': self._page_path()})
            logger.info('Rebuilt')
        except Exception as exc:
            logger.error('Rebuild failed: {0}'.format(exc))
            self._json(500, {'ok': False,
                             'error': 'Rebuild failed: {0}'.format(exc)})
        finally:
            self.state.lock.release()

    def log_message(self, fmt, *args):
        logger.debug(fmt % args)


def make_server(page, extras_dir, host, port, rebuild=None):
    state = PreviewState(page, rebuild)
    handler = functools.partial(Handler, state=state, extras_dir=extras_dir,
                                directory=os.path.dirname(page))
    server = http.server.ThreadingHTTPServer((host, port), handler)
    server.state = state
    return server


def preview(page, extras_dir, host='127.0.0.1', port=8000, rebuild=None):
    """Serve the page until Ctrl-C. With rebuild (a function that re-runs
    the pipeline and returns the new page), the page gets a Rebuild
    button."""
    server = make_server(page, extras_dir, host, port, rebuild)
    logger.info('Preview at http://127.0.0.1:{0}/ (Ctrl-C to stop){1}'.format(
        port, '; use the Rebuild button after editing content'
        if rebuild else ''))
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
