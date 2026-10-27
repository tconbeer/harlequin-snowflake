from __future__ import annotations

import pytest
from snowflake_text import read_identifier, read_qualified, read_string

from harlequin_snowflake.sql import (
    contains,
    editor_identifier,
    like_pattern,
    quote_identifier,
    quote_qualified,
    sql_comment,
    sql_string,
)


@pytest.mark.parametrize(
    "identifier,expected",
    [
        ("FOO", '"FOO"'),
        ("lower case", '"lower case"'),
        ('has"quote', '"has""quote"'),
        ("", '""'),
    ],
)
def test_quote_identifier(identifier: str, expected: str) -> None:
    assert quote_identifier(identifier) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("foo", "'foo'"),
        ("it's", "'it''s'"),
        ("back\\slash", "'back\\\\slash'"),
    ],
)
def test_sql_string(value: str, expected: str) -> None:
    assert sql_string(value) == expected


@pytest.mark.parametrize(
    "term,expected",
    [
        ("foo", "%foo%"),
        # `SHOW` has no ESCAPE clause, so a metacharacter the user typed becomes
        # a single-character wildcard, which still matches the character itself.
        ("a_b", "%a_b%"),
        ("50%", "%50_%"),
    ],
)
def test_like_pattern(term: str, expected: str) -> None:
    assert like_pattern(term) == expected


def test_like_pattern_is_a_superset_of_contains() -> None:
    """Every label the pattern is meant to find is one `contains` keeps."""
    assert contains("foo", "MY_FOO_TABLE")
    assert contains("FOO", "my_foo_table")
    assert not contains("a_b", "axb_")
    assert not contains("50%", "50X")
    assert not contains("foo", None)


AWKWARD_NAMES = [
    "plain",
    "MixedCase",
    'double"quote',
    "single'quote",
    "back`tick",
    "close]bracket",
    "back\\slash",
    "trailing\\",
    "dot.ted",
    "with space",
    "semi;colon",
    'x"; drop table y; --',
    "new\nline",
    "",
]


@pytest.mark.parametrize("name", AWKWARD_NAMES)
def test_quote_identifier_reads_back_as_the_name(name: str) -> None:
    quoted = quote_identifier(name)
    assert read_identifier(quoted) == (name, len(quoted))


@pytest.mark.parametrize("name", AWKWARD_NAMES)
def test_quote_qualified_reads_back_as_its_parts(name: str) -> None:
    qualified = quote_qualified("DB", name, f"{name}2")
    assert read_qualified(qualified) == (["DB", name, f"{name}2"], len(qualified))


@pytest.mark.parametrize("value", [*AWKWARD_NAMES, "\\'", "''", "\\\\'"])
def test_sql_string_reads_back_as_the_value(value: str) -> None:
    literal = sql_string(value)
    assert read_string(literal) == (value, len(literal))


@pytest.mark.parametrize(
    "name,expected",
    [
        ("MY_FN", "my_fn"),
        ("FN$2", "fn$2"),
        ("_PRIVATE", "_private"),
        # anything an unquoted name would not fold back to keeps its quotes
        ("myFunc", '"myFunc"'),
        ("lower", '"lower"'),
        ("2FAST", '"2FAST"'),
        ("WITH SPACE", '"WITH SPACE"'),
        ('MY"FN', '"MY""FN"'),
        ("SELECT", '"SELECT"'),
    ],
)
def test_editor_identifier(name: str, expected: str) -> None:
    assert editor_identifier(name, reserved=frozenset({"SELECT"})) == expected


@pytest.mark.parametrize(
    "line_break",
    ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", " ", " "],
)
def test_sql_comment_stays_on_one_line(line_break: str) -> None:
    comment = sql_comment(f"DDL for x{line_break}drop table y")
    assert comment.splitlines() == [comment]
    assert comment.startswith("-- ")


def test_like_pattern_neutralizes_a_backslash() -> None:
    """A backslash in a `LIKE` pattern escapes what follows it."""
    assert like_pattern("a\\b") == "%a_b%"
    assert like_pattern("ends\\") == "%ends_%"
    assert contains("a\\b", "X_A\\B")
