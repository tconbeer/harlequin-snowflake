from __future__ import annotations

import json
from typing import Any

import pytest

from harlequin_snowflake.types import (
    column_labels,
    parse_data_type,
    short_type_from_name,
    short_type_from_type_code,
    sql_type_name,
)


@pytest.mark.parametrize(
    "type_name,scale,expected",
    [
        ("TEXT", None, "s"),
        ("FIXED", 0, "#"),
        ("FIXED", 2, "#.#"),
        ("NUMBER", 2, "#.#"),
        ("REAL", None, "#.#"),
        ("BOOLEAN", None, "t/f"),
        ("DATE", None, "d"),
        ("TIMESTAMP_NTZ", None, "ts"),
        ("VARIANT", None, "{}"),
        ("ARRAY", None, "[]"),
        ("VECTOR", None, "[#]"),
        ("SOMETHING_NEW", None, "?"),
        (None, None, "?"),
        ("", None, "?"),
    ],
)
def test_short_type_from_name(
    type_name: str | None, scale: int | None, expected: str
) -> None:
    assert short_type_from_name(type_name, scale=scale) == expected


def test_short_type_from_type_code() -> None:
    # 0 is FIXED and 2 is TEXT in the connector's own field map.
    assert short_type_from_type_code(0, scale=0) == "#"
    assert short_type_from_type_code(0, scale=4) == "#.#"
    assert short_type_from_type_code(2) == "s"
    assert short_type_from_type_code(None) == "?"
    assert short_type_from_type_code(9999) == "?"


@pytest.mark.parametrize(
    "data_type,expected",
    [
        ({"type": "TEXT", "length": 255}, "VARCHAR(255)"),
        ({"type": "TEXT"}, "VARCHAR"),
        ({"type": "FIXED", "precision": 38, "scale": 0}, "NUMBER(38,0)"),
        ({"type": "REAL"}, "FLOAT"),
        ({"type": "TIMESTAMP_NTZ", "scale": 9}, "TIMESTAMP_NTZ(9)"),
        ({"type": "BINARY", "length": 8388608}, "BINARY(8388608)"),
        ({"type": "VARIANT"}, "VARIANT"),
        (
            {"type": "VECTOR", "elementType": "FLOAT", "dimension": 768},
            "VECTOR(FLOAT,768)",
        ),
        ({}, "?"),
    ],
)
def test_sql_type_name(data_type: dict[str, Any], expected: str) -> None:
    assert sql_type_name(data_type) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"type":"TEXT","length":16777216}', {"type": "TEXT", "length": 16777216}),
        ({"type": "TEXT"}, {"type": "TEXT"}),
        ("not json at all", {}),
        ("[1, 2]", {}),
        (None, {}),
        ("", {}),
    ],
)
def test_parse_data_type(raw: Any, expected: dict[str, Any]) -> None:
    assert parse_data_type(raw) == expected


def test_column_labels_reads_a_show_columns_row() -> None:
    raw = json.dumps(
        {
            "type": "FIXED",
            "precision": 38,
            "scale": 2,
            "nullable": True,
        }
    )
    assert column_labels(raw) == ("#.#", "NUMBER(38,2)")


def test_column_labels_survives_an_unparseable_type() -> None:
    assert column_labels("{{{") == ("?", "?")
