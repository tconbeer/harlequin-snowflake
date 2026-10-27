"""Building SQL text safely, for the statements this adapter writes itself.

Catalog reads, context-menu interactions, and completions have to name objects
the user picked, as identifiers or string literals, so this is where they are
quoted.
"""

from __future__ import annotations

import re

_UNQUOTED_IDENTIFIER = re.compile(r"[A-Z_][A-Z0-9_$]*")
"""A name Snowflake stores as typed when it is written unquoted."""


def quote_identifier(identifier: str) -> str:
    """One identifier, quoted so Snowflake reads it exactly as it is spelled.

    Snowflake folds an unquoted identifier to upper case, and every name here
    was read back from the server in its stored case, so quoting is what keeps
    a lower-case or mixed-case name resolvable.
    """
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def quote_qualified(*names: str) -> str:
    """A dotted name, each part quoted, as in `"db"."schema"."table"`."""
    return ".".join(quote_identifier(name) for name in names)


def editor_identifier(name: str, reserved: frozenset[str]) -> str:
    """A name as a user would type it: lower case unquoted when that resolves.

    An unquoted name folds to upper case, so only a stored name that is already
    upper case, and not a reserved word, survives being written without quotes.
    """
    if _UNQUOTED_IDENTIFIER.fullmatch(name) and name not in reserved:
        return name.lower()
    return quote_identifier(name)


def sql_string(value: str) -> str:
    """One string literal. Snowflake reads a backslash in one as an escape."""
    escaped = value.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def sql_comment(text: str) -> str:
    """A `--` comment holding text on one line, so no part of it runs as SQL.

    The editor splits lines the way `str.splitlines()` does, which breaks on
    more than `\\n`, so every one of those breaks becomes a space.
    """
    return "-- " + " ".join(text.splitlines())


def like_pattern(term: str) -> str:
    """A `SHOW ... LIKE` pattern matching at least every label containing term.

    `SHOW` has no `ESCAPE` clause, and a backslash would escape whatever
    follows it, so each `%`, `_`, or `\\` the user typed becomes `_`, which
    matches the character itself along with every other single character: the
    server returns a superset, and `contains()` narrows it to the exact
    matches.
    """
    body = "".join("_" if character in "%_\\" else character for character in term)
    return f"%{body}%"


def contains(term: str, label: str | None) -> bool:
    """Whether label contains term, matched the way a catalog search matches."""
    return label is not None and term.casefold() in label.casefold()
