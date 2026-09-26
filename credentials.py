"""Encrypted credentials (#22): each credential is a file secrets/<name>.enc
in the content repo, encrypted to this install's key pair. The private key
lives in the keys volume (KEYS_DIR, /keys in the container), so the .enc
files are useless anywhere else and safe to commit or back up.

Format: JSON with a random AES-256-GCM key per file, sealed with the
instance's RSA public key (OAEP-SHA256), and the fingerprint of the key it
was made for, so a mismatch gives a clear error instead of garbage."""
import base64
import hashlib
import json
import logging
import os
import re

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import hostpath
import vars

logger = logging.getLogger('credentials')

KEY_FILE = 'instance-key.pem'
KEY_SIZE = 3072
NAME = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(), label=None)


def keys_dir():
    return os.environ.get('KEYS_DIR', '').strip() or \
        os.path.join(vars.data_dir, '.keys')


def secrets_dir():
    return os.environ.get('SECRETS_DIR', '').strip() or \
        os.path.join(vars.data_dir, 'secrets')


def check_name(name):
    if not NAME.match(name or ''):
        raise ValueError('Invalid credential name {0!r}: use lowercase '
                         'letters, digits, _ and -'.format(name))
    return name


def _path(name):
    return os.path.join(secrets_dir(), check_name(name) + '.enc')


def _load_key(create=False):
    path = os.path.join(keys_dir(), KEY_FILE)
    if not os.path.exists(path):
        if not create:
            return None
        os.makedirs(keys_dir(), exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537,
                                       key_size=KEY_SIZE)
        pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(pem)
        logger.warning('Created a new instance key in {0}'.format(
            hostpath.describe(keys_dir())))
        # Only worth saying if there are credentials the new key can't read
        if names():
            logger.warning('Credentials stored for an earlier key ({0}) '
                           'must be set again'.format(', '.join(names())))
        return key
    with open(path, 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _fingerprint(public_key):
    der = public_key.public_bytes(serialization.Encoding.DER,
                                  serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()[:16]


def put(name, value):
    """Encrypt value as credential name (creating the instance key if this
    is the first credential)."""
    if not value:
        raise ValueError('Refusing to store an empty credential')
    public = _load_key(create=True).public_key()
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    sealed = AESGCM(data_key).encrypt(nonce, value.encode('utf-8'),
                                      name.encode('utf-8'))
    record = {
        'version': 1,
        'key': _fingerprint(public),
        'sealed_key': base64.b64encode(public.encrypt(data_key, OAEP)).decode(),
        'nonce': base64.b64encode(nonce).decode(),
        'ciphertext': base64.b64encode(sealed).decode(),
    }
    os.makedirs(secrets_dir(), exist_ok=True)
    with open(_path(name), 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=1)
        f.write('\n')


def get(name):
    """The decrypted credential, or None if it isn't set. Raises
    RuntimeError if it can't be decrypted with this install's key."""
    path = _path(name)
    if not os.path.exists(path):
        return None
    key = _load_key()
    if key is None:
        raise RuntimeError(
            'Credential {0!r} is set, but this install has no key in {1} '
            '(new or reset keys volume?). Set it again: docker compose run '
            '--rm secrets set {0}'.format(name, hostpath.describe(keys_dir())))
    with open(path, encoding='utf-8') as f:
        record = json.load(f)
    if record.get('key') != _fingerprint(key.public_key()):
        raise RuntimeError(
            'Credential {0!r} was encrypted for a different key (the keys '
            'volume changed?). Set it again: docker compose run --rm '
            'secrets set {0}'.format(name))
    try:
        data_key = key.decrypt(base64.b64decode(record['sealed_key']), OAEP)
        value = AESGCM(data_key).decrypt(
            base64.b64decode(record['nonce']),
            base64.b64decode(record['ciphertext']), name.encode('utf-8'))
    except Exception:
        raise RuntimeError('Credential {0!r} is damaged or was renamed; set '
                           'it again'.format(name)) from None
    return value.decode('utf-8')


def names():
    if not os.path.isdir(secrets_dir()):
        return []
    return sorted(f[:-4] for f in os.listdir(secrets_dir())
                  if f.endswith('.enc') and NAME.match(f[:-4]))


def remove(name):
    """Delete credential name; returns False if it wasn't set."""
    path = _path(name)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True
