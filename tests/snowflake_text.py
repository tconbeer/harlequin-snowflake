"""Reads names and strings back out of SQL text, by Snowflake's documented rules.

A quoted identifier is `"..."` with `""` for a quote; an unquoted one folds to
upper case. A string literal is `'...'` with `''` or `\\'` for a quote and
backslash escapes. The tests use these to check that the text this adapter
writes names the object it was built from, without a Snowflake account.
"""

from __future__ import annotations

import re

_UNQUOTED = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "0": "\0"}


def read_identifier(text: str, start: int = 0) -> tuple[str, int]:
    """One identifier at text[start], and the index just past it."""
    if text[start] != '"':
        match = _UNQUOTED.match(text, start)
        assert match, f"no identifier at {text[start:]!r}"
        return match.group().upper(), match.end()
    name: list[str] = []
    position = start + 1
    while True:
        character = text[position]
        if character == '"':
            if text[position + 1 : position + 2] == '"':
                name.append('"')
                position += 2
                continue
            return "".join(name), position + 1
        name.append(character)
        position += 1


def read_qualified(text: str, start: int = 0) -> tuple[list[str], int]:
    """A dotted name at text[start], as its parts, and the index past it."""
    parts: list[str] = []
    position = start
    while True:
        part, position = read_identifier(text, position)
        parts.append(part)
        if text[position : position + 1] != ".":
            return parts, position
        position += 1


def qualified_after(text: str, prefix: str) -> list[str]:
    """The dotted name that immediately follows the first `prefix` in text."""
    index = text.index(prefix) + len(prefix)
    parts, _ = read_qualified(text, index)
    return parts


def read_string(text: str, start: int = 0) -> tuple[str, int]:
    """One string literal at text[start], unescaped, and the index past it."""
    assert text[start] == "'", f"no string at {text[start:]!r}"
    value: list[str] = []
    position = start + 1
    while True:
        character = text[position]
        if character == "\\":
            following = text[position + 1]
            value.append(_ESCAPES.get(following, following))
            position += 2
        elif character == "'":
            if text[position + 1 : position + 2] == "'":
                value.append("'")
                position += 2
                continue
            return "".join(value), position + 1
        else:
            value.append(character)
            position += 1


def string_after(text: str, prefix: str) -> str:
    """The string literal that immediately follows the first `prefix` in text."""
    value, _ = read_string(text, text.index(prefix) + len(prefix))
    return value
