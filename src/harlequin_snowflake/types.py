"""How Snowflake's types are spelled, and the short labels the catalog shows.

Two places need this: a cursor, which learns a column's type as the integer
type code in its description, and the catalog, which learns it as the JSON blob
`SHOW COLUMNS` puts in its `data_type` field. Both end up here so that the same
column is labeled the same way whichever one found it.
"""

from __future__ import annotations

import json
from typing import Any

_SHORT_TYPES = {
    "ARRAY": "[]",
    "BINARY": "b",
    "BOOLEAN": "t/f",
    "DATE": "d",
    "FILE": "f",
    "FIXED": "#",
    "GEOGRAPHY": "geo",
    "GEOMETRY": "geo",
    "INTERVAL_DAY_TIME": "|-|",
    "INTERVAL_YEAR_MONTH": "|-|",
    "MAP": "{}",
    "OBJECT": "{}",
    "REAL": "#.#",
    "TEXT": "s",
    "TIME": "t",
    "TIMESTAMP": "ts",
    "TIMESTAMP_LTZ": "ts",
    "TIMESTAMP_NTZ": "ts",
    "TIMESTAMP_TZ": "ts",
    "VARIANT": "{}",
    "VECTOR": "[#]",
}
"""Short labels, keyed by the internal type names the connector reports.

These are the names in `snowflake.connector.constants.FIELD_ID_TO_NAME`, which
are the ones `SHOW COLUMNS` uses too -- not the names SQL uses, so `VARCHAR` is
`TEXT` and `NUMBER` is `FIXED` here. `sql_type_name()` maps the other way.
"""

_SQL_ALIASES = {
    "FIXED": "NUMBER",
    "REAL": "FLOAT",
    "TEXT": "VARCHAR",
}
"""The internal names whose SQL spelling differs, for `type_name`."""

_UNKNOWN = "?"


def short_type_from_name(type_name: str | None, scale: int | None = None) -> str:
    """The 1-3 character label for a type the connector named.

    A NUMBER is `#` when it counts and `#.#` when it measures, which is the one
    distinction a scale can make here.
    """
    if not type_name:
        return _UNKNOWN
    normalized = type_name.strip().upper()
    if normalized in ("FIXED", "NUMBER", "NUMERIC", "DECIMAL") and scale:
        return "#.#"
    return _SHORT_TYPES.get(normalized, _UNKNOWN)


def short_type_from_type_code(type_code: int | None, scale: int | None = None) -> str:
    """The label for a column of a result set, which names its type by number."""
    if type_code is None:
        return _UNKNOWN
    from snowflake.connector.constants import FIELD_ID_TO_NAME

    # FIELD_ID_TO_NAME is a defaultdict(str), so an unknown code reads as "",
    # which `short_type_from_name` already reports as unknown.
    return short_type_from_name(FIELD_ID_TO_NAME[type_code], scale=scale)


def parse_data_type(raw: Any) -> dict[str, Any]:
    """The `data_type` field of a `SHOW COLUMNS` row, as a dict.

    Snowflake returns it as a JSON string. A row whose type does not parse is
    not worth failing a whole catalog fetch over, so it comes back empty and is
    labeled unknown.
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def sql_type_name(data_type: dict[str, Any]) -> str:
    """A parsed `SHOW COLUMNS` type, spelled the way SQL spells it.

    e.g. `{"type": "TEXT", "length": 255}` is `VARCHAR(255)`. This is what the
    catalog reports as an item's `type_name`, so it reads like something the
    user could paste into a DDL statement.
    """
    internal = str(data_type.get("type") or "").upper()
    if not internal:
        return _UNKNOWN
    name = _SQL_ALIASES.get(internal, internal)

    if internal == "FIXED":
        precision = data_type.get("precision")
        scale = data_type.get("scale")
        if precision is not None and scale is not None:
            return f"{name}({precision},{scale})"
        return name
    if internal in ("TEXT", "BINARY"):
        length = data_type.get("length")
        return f"{name}({length})" if length is not None else name
    if internal in (
        "TIME",
        "TIMESTAMP",
        "TIMESTAMP_LTZ",
        "TIMESTAMP_NTZ",
        "TIMESTAMP_TZ",
    ):
        scale = data_type.get("scale")
        return f"{name}({scale})" if scale is not None else name
    if internal == "VECTOR":
        element = str(data_type.get("elementType") or "").upper()
        dimension = data_type.get("dimension")
        if element and dimension is not None:
            return f"{name}({element},{dimension})"
        return name
    return name


def column_labels(raw_data_type: Any) -> tuple[str, str]:
    """Both labels for a `SHOW COLUMNS` row: (type_label, type_name)."""
    data_type = parse_data_type(raw_data_type)
    return (
        short_type_from_name(data_type.get("type"), scale=data_type.get("scale")),
        sql_type_name(data_type),
    )
