from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harlequin import HarlequinCompletion
from harlequin.exception import HarlequinQueryError

if TYPE_CHECKING:
    from harlequin_snowflake.adapter import HarlequinSnowflakeConnection

_KEYWORD_PATH = Path(__file__).parent / "keywords.tsv"


def _keyword_completions() -> list[HarlequinCompletion]:
    """The dialect's keywords, from the list bundled with this adapter.

    Snowflake has no queryable table of keywords the way it has one of
    functions, so the list is shipped as a file, sourced from
    https://docs.snowflake.com/en/sql-reference/reserved-keywords.
    """
    completions: list[HarlequinCompletion] = []
    with _KEYWORD_PATH.open("r") as f:
        reader = csv.reader(f, delimiter="\t")
        _header = next(reader)
        for keyword, kind in reader:
            completions.append(
                HarlequinCompletion(
                    label=keyword.lower(),
                    type_label="kw",
                    value=keyword.lower(),
                    priority=100 if kind == "reserved" else 1000,
                    context=None,
                )
            )
    return completions


def _routine_completions(
    conn: "HarlequinSnowflakeConnection",
) -> list[HarlequinCompletion]:
    """Every function and procedure the session can call.

    `SHOW FUNCTIONS` and `SHOW PROCEDURES` report the built-ins along with the
    ones this account defines, so one round trip each covers both. A
    user-defined routine is namespaced under its schema, which is what makes it
    a member completion after the user types that schema's name.
    """
    completions: list[HarlequinCompletion] = []
    for statement, default_label in (
        ("show functions", "fn"),
        ("show procedures", "proc"),
    ):
        try:
            rows = conn._query(statement)
        except HarlequinQueryError:
            # A role without the privilege to list these still gets keyword and
            # catalog completions; it does not get an error on startup.
            continue
        for row in rows:
            label = row.get("name")
            if not label or not isinstance(label, str) or len(label) > 40:
                continue
            completions.append(
                HarlequinCompletion(
                    label=label.lower(),
                    type_label=_routine_type_label(row, default_label),
                    value=label.lower(),
                    priority=1000,
                    context=_routine_context(row),
                )
            )
    return completions


def _routine_type_label(row: dict[str, Any], default: str) -> str:
    if str(row.get("is_aggregate") or "").upper().startswith("Y"):
        return "agg"
    if str(row.get("is_table_function") or "").upper().startswith("Y"):
        return "tf"
    return default


def _routine_context(row: dict[str, Any]) -> str | None:
    """The schema that qualifies a routine, or None for a built-in.

    Snowflake reports a built-in with no schema at all, or with the
    `INFORMATION_SCHEMA` of the current database for the table functions that
    live there; neither should force the user to type a prefix.
    """
    schema = row.get("schema_name")
    if not schema or not isinstance(schema, str):
        return None
    if schema.upper() in ("", "INFORMATION_SCHEMA"):
        return None
    return str(schema)


def _parameter_completions(
    conn: "HarlequinSnowflakeConnection",
) -> list[HarlequinCompletion]:
    """Session parameters, for completing what follows `alter session set`."""
    try:
        rows = conn._query("show parameters in session")
    except HarlequinQueryError:
        return []
    return [
        HarlequinCompletion(
            label=str(row["key"]).lower(),
            type_label="set",
            value=str(row["key"]).lower(),
            priority=2000,
            context=None,
        )
        for row in rows
        if row.get("key")
    ]


def get_completions(
    conn: "HarlequinSnowflakeConnection",
) -> list[HarlequinCompletion]:
    return sorted(
        [
            *_keyword_completions(),
            *_routine_completions(conn),
            *_parameter_completions(conn),
        ]
    )
