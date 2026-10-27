"""The statements catalog loading, search, and completions send, for awkward names."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import fake_connection
from snowflake_text import qualified_after, read_qualified, string_after

from harlequin_snowflake.catalog import DatabaseCatalogItem

NAMES = [
    "plain",
    "MixedCase",
    'double"quote',
    "single'quote",
    "back`tick",
    "close]bracket",
    "back\\slash",
    "dot.ted",
    "with space",
    "semi;colon",
    'x"; drop table y; --',
]


@pytest.mark.parametrize("name", NAMES)
def test_catalog_loading_names_each_level(name: str) -> None:
    database, schema, relation = f"{name}_db", f"{name}_sch", f"{name}_tbl"

    def respond(sql: str) -> list[dict[str, Any]]:
        if sql.startswith("show terse databases"):
            return [{"name": database}]
        if sql.startswith("show terse schemas"):
            return [{"name": schema}]
        if sql.startswith("show objects"):
            return [{"name": relation, "kind": "TABLE"}]
        return [{"column_name": f"{name}_col", "data_type": '{"type":"TEXT"}'}]

    connection, server = fake_connection(respond)
    [database_item] = connection.get_catalog().items
    assert isinstance(database_item, DatabaseCatalogItem)
    [schema_item] = database_item.fetch_children()
    [relation_item] = schema_item.fetch_children()
    [column_item] = relation_item.fetch_children()

    sqls = server.calls
    assert qualified_after(sqls[1], "in database ") == [database]
    assert qualified_after(sqls[2], "in schema ") == [database, schema]
    assert qualified_after(sqls[3], "show columns in ") == [database, schema, relation]

    assert read_qualified(relation_item.qualified_identifier)[0] == [
        database,
        schema,
        relation,
    ]
    assert read_qualified(relation_item.query_name)[0] == [schema, relation]
    assert read_qualified(column_item.qualified_identifier)[0] == [
        database,
        schema,
        relation,
        f"{name}_col",
    ]


@pytest.mark.parametrize("term", [*NAMES, "50%", "a_b", "ends\\"])
def test_search_patterns_are_literals_of_the_term(term: str) -> None:
    connection, server = fake_connection()
    assert connection.search_catalog(term, kind="all") == []
    assert len(server.calls) == 4
    for sql in server.calls:
        pattern = string_after(sql, " like ")
        assert pattern.startswith("%") and pattern.endswith("%")
        body = pattern[1:-1]
        assert len(body) == len(term)
        # every character is the term's own, or a one-character wildcard
        # standing in for one `LIKE` would otherwise read as syntax
        for typed, sent in zip(term, body, strict=True):
            assert sent == typed or (sent == "_" and typed in "%_\\")


@pytest.mark.parametrize("name", NAMES)
def test_search_results_name_what_the_server_reported(name: str) -> None:
    database, schema, relation = f"{name}_db", f"{name}_sch", f"{name}_tbl"

    def respond(sql: str) -> list[dict[str, Any]]:
        if sql.startswith("show objects"):
            return [
                {
                    "database_name": database,
                    "schema_name": schema,
                    "name": relation,
                    "kind": "VIEW",
                }
            ]
        return []

    connection, _ = fake_connection(respond)
    [result] = connection.search_catalog(name, kind="relations")
    assert read_qualified(result.item.qualified_identifier)[0] == [
        database,
        schema,
        relation,
    ]


@pytest.mark.parametrize(
    "name,schema,expected",
    [
        ("UPPER", "", "upper"),
        ("CURRENT_DATE", "", "current_date"),
        ("MY_FN", "S", "my_fn"),
        ("myFunc", "S", '"myFunc"'),
        ("my fn", "S", '"my fn"'),
        ('my"fn', "S", '"my""fn"'),
        # a reserved word would be read as the keyword, not the routine
        ("SELECT", "S", '"SELECT"'),
    ],
)
def test_routine_completion_values_resolve(
    name: str, schema: str, expected: str
) -> None:
    def respond(sql: str) -> list[dict[str, Any]]:
        if sql == "show functions":
            return [{"name": name, "schema_name": schema}]
        return []

    connection, _ = fake_connection(respond)
    [completion] = [c for c in connection.get_completions() if c.type_label == "fn"]
    assert completion.value == expected
