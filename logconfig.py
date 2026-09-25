import logging
import os

DEFAULT_LEVEL = 'INFO'

# Config keys whose values must never reach the log
SENSITIVE_WORDS = ('secret', 'password', 'token', 'client_id', 'clientid',
                   'apikey', 'api_key')
MASK = '********'

logger = logging.getLogger('logconfig')


def env_level():
    """The LOG_LEVEL environment variable, or None if unset or empty."""
    return os.environ.get('LOG_LEVEL', '').strip() or None


def set_level(name):
    """Set the root logger to the named level (e.g. INFO). Returns False,
    leaving the level unchanged, if the name isn't a logging level."""
    level = logging.getLevelName(str(name).strip().upper())
    if not isinstance(level, int):
        logger.warning('Unknown log level {0!r}; keeping {1}'.format(
            name, logging.getLevelName(logging.getLogger().level)))
        return False
    logging.getLogger().setLevel(level)
    return True


def redact(value):
    """Copy of a config structure with every sensitive value masked.
    Nested blocks are searched rather than masked whole, so a plugin
    section like "BitwardenPasswords" stays readable."""
    if isinstance(value, dict):
        return {k: MASK if not isinstance(v, (dict, list))
                and any(w in str(k).lower() for w in SENSITIVE_WORDS)
                else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
