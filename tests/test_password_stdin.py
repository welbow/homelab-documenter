import io
import json
import os

import pytest

import password_stdin
import pipeline
import vars


class Pipe(io.TextIOWrapper):
    def __init__(self, data, tty=False):
        super().__init__(io.BytesIO(data), encoding='utf-8')
        self._tty = tty

    def isatty(self):
        return self._tty


def test_reads_one_line_and_strips_bom_and_crlf():
    pipe = Pipe('﻿Tëst pass 1\r\nsecond line\n'.encode('utf-8'))

    assert password_stdin.read(pipe) == 'Tëst pass 1'


def test_keeps_spaces_inside_and_at_the_ends():
    assert password_stdin.read(Pipe(b' pass word \n')) == ' pass word '


def test_terminal_is_refused():
    with pytest.raises(ValueError, match='not typed at a terminal'):
        password_stdin.read(Pipe(b'x\n', tty=True))


@pytest.mark.parametrize('data', [b'', b'\n', b'\r\n'])
def test_empty_input_is_refused(data):
    with pytest.raises(ValueError, match='nothing was piped in'):
        password_stdin.read(Pipe(data))


def test_pipeline_drops_an_unused_password(content):
    # Bitwarden is disabled in the test config, so nothing uses it
    with open(os.path.join(content.root, 'conf', 'config.json'), 'w') as f:
        json.dump(content.config, f)

    pipeline.main(data_dir=content.root, bw_password='unused')

    assert vars.bw_password is None
