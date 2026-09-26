import io

import pytest

import stdin_value


class Pipe(io.TextIOWrapper):
    def __init__(self, data, tty=False):
        super().__init__(io.BytesIO(data), encoding='utf-8')
        self._tty = tty

    def isatty(self):
        return self._tty


def test_reads_one_line_and_strips_bom_and_crlf():
    pipe = Pipe('﻿Tëst pass 1\r\nsecond line\n'.encode('utf-8'))

    assert stdin_value.read(pipe) == 'Tëst pass 1'


def test_keeps_spaces_inside_and_at_the_ends():
    assert stdin_value.read(Pipe(b' pass word \n')) == ' pass word '


def test_terminal_is_refused():
    with pytest.raises(ValueError, match='not typed at a terminal'):
        stdin_value.read(Pipe(b'x\n', tty=True))


@pytest.mark.parametrize('data', [b'', b'\n', b'\r\n'])
def test_empty_input_is_refused(data):
    with pytest.raises(ValueError, match='nothing was piped in'):
        stdin_value.read(Pipe(data))
