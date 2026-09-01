from __future__ import annotations

import pytest

from harlequin_snowflake.sql import (
    contains,
    like_pattern,
    quote_identifier,
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
