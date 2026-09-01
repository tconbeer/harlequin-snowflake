"""Building SQL text safely, for the statements this adapter writes itself.

Catalog reads and context-menu interactions have to name objects the user
picked, and Snowflake's `SHOW`, `DESCRIBE`, and `GET_DDL` take those names as
identifiers or string literals rather than as bind parameters, so this is where
they are quoted.
"""

from __future__ import annotations


def quote_identifier(identifier: str) -> str:
    """One identifier, quoted so Snowflake reads it exactly as it is spelled.

    Snowflake folds an unquoted identifier to upper case, and every name here
    was read back from the server in its stored case, so quoting is what keeps
    a lower-case or mixed-case name resolvable.
    """
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def sql_string(value: str) -> str:
    """One string literal, escaped. Snowflake honors backslash escapes."""
    escaped = value.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def like_pattern(term: str) -> str:
    """A `SHOW ... LIKE` pattern matching at least every label containing term.

    `SHOW` has no `ESCAPE` clause, so a `%` or `_` the user typed cannot be made
    literal. Each one becomes `_`, which matches the character itself along with
    every other single character: the server returns a superset, and
    `contains()` narrows it to the exact matches.
    """
    body = "".join("_" if character in "%_" else character for character in term)
    return f"%{body}%"


def contains(term: str, label: str | None) -> bool:
    """Whether label contains term, matched the way a catalog search matches."""
    return label is not None and term.casefold() in label.casefold()
