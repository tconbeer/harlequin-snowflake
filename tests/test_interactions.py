"""Every catalog interaction, run against objects with awkward names.

Each test reads the SQL an interaction executed or inserted back into names, by
Snowflake's quoting rules, and checks they name the object it was run on.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import pytest
from fakes import FakeDriver, fake_connection
from harlequin.catalog import CatalogItem
from snowflake_text import qualified_after, read_qualified, string_after

from harlequin_snowflake import interactions
from harlequin_snowflake.catalog import (
    ColumnCatalogItem,
    DatabaseCatalogItem,
    RelationCatalogItem,
    SchemaCatalogItem,
    relation_item_for_kind,
)

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


class Objects:
    """A database, schema, table, and column, each named `name`, and a server."""

    def __init__(
        self,
        name: str,
        respond: Callable[[str, Sequence[Any] | None], list[dict[str, Any]]]
        | None = None,
        kind: str = "TABLE",
    ) -> None:
        self.connection, self.server = fake_connection(respond)
        self.database = DatabaseCatalogItem.from_label(
            label=f"{name}_db", connection=self.connection
        )
        self.schema = SchemaCatalogItem.from_parent(
            parent=self.database, label=f"{name}_sch"
        )
        self.relation: RelationCatalogItem = relation_item_for_kind(
            parent=self.schema, label=f"{name}_tbl", row={"kind": kind}
        )
        self.column = ColumnCatalogItem.from_parent(
            parent=self.relation, label=f"{name}_col", type_label="s"
        )
        self.relation.children = [self.column]
        self.relation.loaded = True
        self.driver = FakeDriver()

    def path(self, depth: int) -> list[str]:
        items: list[CatalogItem] = [self.database, self.schema, self.relation]
        return [item.label for item in items[:depth]]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("scope,depth", [("database", 1), ("schema", 2)])
def test_use_binds_the_name(name: str, scope: str, depth: int) -> None:
    objects = Objects(name)
    item = objects.database if scope == "database" else objects.schema
    action = getattr(interactions, f"execute_use_{scope}_statement")
    action(item, objects.driver.as_driver())
    [(sql, params)] = objects.server.calls
    assert sql == f"use {scope} identifier(?)"
    assert params is not None and read_qualified(params[0])[0] == objects.path(depth)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize(
    "action,kind,object_type,suffix",
    [
        ("execute_drop_database_statement", None, "database", ""),
        ("execute_drop_schema_statement", None, "schema", " cascade"),
        ("execute_drop_table_statement", "TABLE", "table", ""),
        ("execute_drop_view_statement", "VIEW", "view", ""),
        (
            "execute_drop_materialized_view_statement",
            "MATERIALIZED_VIEW",
            "materialized view",
            "",
        ),
        ("execute_drop_dynamic_table_statement", "DYNAMIC TABLE", "dynamic table", ""),
        ("execute_drop_iceberg_table_statement", "ICEBERG TABLE", "iceberg table", ""),
        (
            "execute_drop_external_table_statement",
            "EXTERNAL TABLE",
            "external table",
            "",
        ),
    ],
)
def test_drop_binds_the_name(
    name: str, action: str, kind: str | None, object_type: str, suffix: str
) -> None:
    objects = Objects(name, kind=kind or "TABLE")
    item, depth = {
        "database": (objects.database, 1),
        "schema": (objects.schema, 2),
    }.get(object_type, (objects.relation, 3))
    getattr(interactions, action)(item, objects.driver.as_driver())
    [(sql, params)] = objects.server.calls
    assert sql == f"drop {object_type} identifier(?){suffix}"
    assert params is not None and read_qualified(params[0])[0] == objects.path(depth)
    assert objects.driver.refreshed


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize(
    "action,object_type,depth",
    [
        ("show_database_ddl", "database", 1),
        ("show_schema_ddl", "schema", 2),
        ("show_table_ddl", "table", 3),
        ("show_view_definition", "view", 3),
    ],
)
def test_show_ddl_binds_the_name(
    name: str, action: str, object_type: str, depth: int
) -> None:
    ddl = "create table x (\n    a int\n);"
    objects = Objects(name, respond=lambda sql, params: [{"get_ddl": ddl}])
    item = [objects.database, objects.schema, objects.relation][depth - 1]
    getattr(interactions, action)(item, objects.driver.as_driver())
    [(sql, params)] = objects.server.calls
    assert sql == "select get_ddl(?, ?, true)"
    assert params is not None and params[0] == object_type
    assert read_qualified(params[1])[0] == objects.path(depth)
    [buffer] = objects.driver.buffers
    header, *body = buffer.splitlines()
    assert header.startswith("-- ")
    assert body == ddl.splitlines()


@pytest.mark.parametrize(
    "line_break",
    ["\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", " ", " "],
)
def test_show_ddl_header_cannot_break_out_of_its_comment(line_break: str) -> None:
    """A name holding a line break must not put the rest of it on a SQL line."""
    ddl = "create table x (a int);"
    objects = Objects(
        f"t{line_break}drop table y;", respond=lambda sql, params: [{"get_ddl": ddl}]
    )
    interactions.show_table_ddl(objects.relation, objects.driver.as_driver())
    [buffer] = objects.driver.buffers
    assert buffer.splitlines()[1:] == [ddl]
    assert buffer.splitlines()[0].startswith("-- ")


def test_show_ddl_with_no_result_warns() -> None:
    objects = Objects("t")
    interactions.show_table_ddl(objects.relation, objects.driver.as_driver())
    assert not objects.driver.buffers
    assert objects.driver.notifications[-1][1] == "warning"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize(
    "action,prefix",
    [
        ("show_select_star", "from "),
        ("show_sample", "from "),
        ("show_row_count", "from "),
        ("show_describe_relation", "describe table "),
        ("show_grants", "show grants on table "),
    ],
)
def test_relation_text_names_the_relation(name: str, action: str, prefix: str) -> None:
    objects = Objects(name)
    getattr(interactions, action)(objects.relation, objects.driver.as_driver())
    [buffer] = objects.driver.buffers
    assert qualified_after(buffer, prefix) == objects.path(3)
    assert not objects.server.calls


@pytest.mark.parametrize("name", NAMES)
def test_grants_name_schemas_and_databases(name: str) -> None:
    objects = Objects(name)
    interactions.show_grants(objects.database, objects.driver.as_driver())
    interactions.show_grants(objects.schema, objects.driver.as_driver())
    database_text, schema_text = objects.driver.buffers
    assert qualified_after(database_text, "on database ") == objects.path(1)
    assert qualified_after(schema_text, "on schema ") == objects.path(2)


@pytest.mark.parametrize("name", NAMES)
def test_list_objects_names_the_database_and_schema(name: str) -> None:
    objects = Objects(name)
    interactions.show_list_objects(objects.database, objects.driver.as_driver())
    interactions.show_list_objects(objects.schema, objects.driver.as_driver())
    database_text, schema_text = objects.driver.buffers
    tables = [*objects.path(1), "INFORMATION_SCHEMA", "TABLES"]
    assert qualified_after(database_text, "from ") == tables
    assert "where" not in database_text
    assert qualified_after(schema_text, "from ") == tables
    assert string_after(schema_text, "t.table_schema = ") == objects.schema.label


@pytest.mark.parametrize("name", NAMES)
def test_refresh_history_names_the_dynamic_table(name: str) -> None:
    objects = Objects(name, kind="DYNAMIC TABLE")
    interactions.show_refresh_history(objects.relation, objects.driver.as_driver())
    [buffer] = objects.driver.buffers
    assert qualified_after(buffer, "table(\n    ") == [
        *objects.path(1),
        "INFORMATION_SCHEMA",
        "DYNAMIC_TABLE_REFRESH_HISTORY",
    ]
    name_prefix = string_after(buffer, "name_prefix => ")
    assert read_qualified(name_prefix)[0] == objects.path(3)


@pytest.mark.parametrize("name", NAMES)
def test_value_counts_name_the_column_and_relation(name: str) -> None:
    objects = Objects(name)
    interactions.show_column_value_counts(objects.column, objects.driver.as_driver())
    [buffer] = objects.driver.buffers
    assert qualified_after(buffer, "select\n    ") == [objects.column.label]
    assert qualified_after(buffer, "from ") == objects.path(3)


@pytest.mark.parametrize("name", NAMES)
def test_insert_columns_names_each_column(name: str) -> None:
    objects = Objects(name)
    second = ColumnCatalogItem.from_parent(
        parent=objects.relation, label=f"{name}_2", type_label="#"
    )
    objects.relation.children = [objects.column, second]
    interactions.insert_columns_at_cursor(objects.relation, objects.driver.as_driver())
    [text] = objects.driver.inserted
    first_name, end = read_qualified(text)
    assert first_name == [objects.column.label]
    assert text[end : end + 2] == ",\n"
    assert read_qualified(text, end + 2) == ([second.label], len(text))
