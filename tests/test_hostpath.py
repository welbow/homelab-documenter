import pytest

import hostpath

# Captured from preview on Docker Desktop for Windows, plus a macOS-style
# share and an ordinary container path
MOUNTINFO = r"""1014 1 0:60 / / rw - overlay overlay rw
1236 1014 8:64 /data/docker/volumes/homelab-documenter-keys/_data /keys rw,relatime master:27 - ext4 /dev/sde rw
1397 1014 0:98 /Users/jason/Documents/GitHub/homelab-documenter-local/secrets /app/secrets ro,noatime - 9p C:\134 rw,aname=drvfs;path=C:\;uid=0
1398 1014 0:99 / /export rw - 9p E:\134 rw,aname=drvfs;path=E:\
1399 1014 0:100 /Users/sam/content/output /app/output ro - virtiofs virtiofs rw
1400 1014 0:101 / /app/build rw - tmpfs tmpfs rw
"""


@pytest.fixture
def table(tmp_path):
    path = tmp_path / 'mountinfo'
    path.write_text(MOUNTINFO)
    return str(path)


def test_named_volume(table):
    assert hostpath.describe('/keys', table) \
        == 'Docker volume homelab-documenter-keys'
    assert hostpath.describe('/keys/instance-key.pem', table) \
        == 'instance-key.pem (Docker volume homelab-documenter-keys)'


def test_windows_share_becomes_a_drive_path(table):
    assert hostpath.describe('/app/secrets/bw_clientid.enc', table) == \
        r'C:\Users\jason\Documents\GitHub\homelab-documenter-local' \
        r'\secrets\bw_clientid.enc'


def test_whole_drive_share(table):
    assert hostpath.describe('/export', table) == 'E:\\'
    assert hostpath.describe('/export/img/map.png', table) == r'E:\img\map.png'


def test_mac_share_keeps_the_host_path(table):
    assert hostpath.describe('/app/output/standard.css', table) \
        == '/Users/sam/content/output/standard.css'


def test_unmapped_paths_are_shown_as_they_are(table):
    assert hostpath.describe('/app/build/output.html', table) \
        == '/app/build/output.html'
    assert hostpath.describe('/somewhere/else', table) == '/somewhere/else'


def test_no_mount_table(tmp_path):
    assert hostpath.describe('/keys', str(tmp_path / 'missing')) == '/keys'


def test_join_uses_the_host_separator(table, monkeypatch):
    monkeypatch.setattr(hostpath, 'MOUNTINFO', table)
    monkeypatch.setattr(hostpath.describe, '__defaults__', (table,))

    assert hostpath.join('/app/secrets', 'bw_clientid.enc') == \
        r'C:\Users\jason\Documents\GitHub\homelab-documenter-local' \
        r'\secrets\bw_clientid.enc'
    assert hostpath.join('/export', 'img/map.png') == r'E:\img\map.png'
    assert hostpath.join('/keys', 'instance-key.pem') \
        == 'instance-key.pem in Docker volume homelab-documenter-keys'
