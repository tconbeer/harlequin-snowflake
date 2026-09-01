from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING, Sequence

from harlequin.catalog import CatalogItem
from harlequin.exception import HarlequinQueryError

from harlequin_snowflake.sql import quote_identifier, sql_string

if TYPE_CHECKING:
    from harlequin.driver import HarlequinDriver

    from harlequin_snowflake.adapter import HarlequinSnowflakeConnection
    from harlequin_snowflake.catalog import (
        ColumnCatalogItem,
        DatabaseCatalogItem,
        RelationCatalogItem,
        SchemaCatalogItem,
    )


def _use(
    item: "SchemaCatalogItem" | "DatabaseCatalogItem",
    driver: "HarlequinDriver",
    scope: str,
) -> None:
    if item.connection is None:
        return
    try:
        item.connection.execute(f"use {scope} {item.qualified_identifier}")
    except HarlequinQueryError:
        driver.notify(f"Could not switch to {item.label}", severity="error")
        raise
    else:
        driver.notify(f"Session context switched to {item.label}")


def execute_use_database_statement(
    item: "DatabaseCatalogItem", driver: "HarlequinDriver"
) -> None:
    _use(item, driver, "database")


def execute_use_schema_statement(
    item: "SchemaCatalogItem", driver: "HarlequinDriver"
) -> None:
    _use(item, driver, "schema")


def _drop(
    item: CatalogItem,
    driver: "HarlequinDriver",
    object_type: str,
    connection: "HarlequinSnowflakeConnection" | None,
    cascade: bool = False,
) -> None:
    def _execute() -> None:
        if connection is None:
            return
        suffix = " cascade" if cascade else ""
        try:
            connection.execute(
                f"drop {object_type} {item.qualified_identifier}{suffix}"
            )
        except HarlequinQueryError:
            driver.notify(
                f"Could not drop {object_type} {item.label}", severity="error"
            )
            raise
        else:
            driver.notify(f"Dropped {object_type} {item.label}")
            driver.refresh_catalog()

    driver.confirm_and_execute(callback=_execute)


def execute_drop_database_statement(
    item: "DatabaseCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "database", item.connection)


def execute_drop_schema_statement(
    item: "SchemaCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "schema", item.connection, cascade=True)


def execute_drop_table_statement(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "table", item.connection)


def execute_drop_view_statement(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "view", item.connection)


def execute_drop_materialized_view_statement(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "materialized view", item.connection)


def execute_drop_dynamic_table_statement(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "dynamic table", item.connection)


def execute_drop_iceberg_table_statement(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "iceberg table", item.connection)


def execute_drop_external_table_statement(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    _drop(item, driver, "external table", item.connection)


def show_select_star(item: "RelationCatalogItem", driver: "HarlequinDriver") -> None:
    driver.insert_text_in_new_buffer(
        dedent(
            f"""
            select *
            from {item.qualified_identifier}
            limit 100
            """.strip("\n")
        )
    )


def show_sample(item: "RelationCatalogItem", driver: "HarlequinDriver") -> None:
    """A uniform sample, which reads far less than the head of a large table."""
    driver.insert_text_in_new_buffer(
        dedent(
            f"""
            select *
            from {item.qualified_identifier} sample (100 rows)
            """.strip("\n")
        )
    )


def show_row_count(item: "RelationCatalogItem", driver: "HarlequinDriver") -> None:
    driver.insert_text_in_new_buffer(
        dedent(
            f"""
            select count(*) as row_count
            from {item.qualified_identifier}
            """.strip("\n")
        )
    )


def show_describe_relation(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    driver.insert_text_in_new_buffer(f"describe table {item.qualified_identifier}")


def show_grants(item: CatalogItem, driver: "HarlequinDriver") -> None:
    object_type = getattr(item, "GRANT_OBJECT_TYPE", "table")
    driver.insert_text_in_new_buffer(
        f"show grants on {object_type} {item.qualified_identifier}"
    )


def _insert_ddl(
    item: CatalogItem,
    driver: "HarlequinDriver",
    connection: "HarlequinSnowflakeConnection" | None,
    object_type: str,
) -> None:
    """Runs `GET_DDL` and puts the statement it returns in a new buffer.

    The DDL is fetched rather than left for the user to run, so that the buffer
    holds the definition itself and not a query that would return it.
    """
    if connection is None:
        return
    query = (
        f"select get_ddl({sql_string(object_type)}, "
        f"{sql_string(item.qualified_identifier)}, true)"
    )
    try:
        cur = connection.execute(query)
    except HarlequinQueryError:
        driver.notify(f"Could not get the DDL for {item.label}", severity="error")
        raise
    if cur is None:
        return
    result = cur.fetchall()
    if result is None:
        return
    try:
        ddl = list(result)[0][0]
    except (IndexError, KeyError, TypeError):
        driver.notify(f"Snowflake returned no DDL for {item.label}", severity="warning")
        return
    driver.insert_text_in_new_buffer(f"-- DDL for {item.query_name}\n{ddl}")


def show_database_ddl(item: "DatabaseCatalogItem", driver: "HarlequinDriver") -> None:
    _insert_ddl(item, driver, item.connection, "database")


def show_schema_ddl(item: "SchemaCatalogItem", driver: "HarlequinDriver") -> None:
    _insert_ddl(item, driver, item.connection, "schema")


def show_table_ddl(item: "RelationCatalogItem", driver: "HarlequinDriver") -> None:
    _insert_ddl(item, driver, item.connection, "table")


def show_view_definition(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    _insert_ddl(item, driver, item.connection, "view")


def show_list_objects(
    item: "SchemaCatalogItem" | "DatabaseCatalogItem", driver: "HarlequinDriver"
) -> None:
    """A query over the database's own `information_schema`, scoped to the item.

    `type(item).__name__` rather than `isinstance`, because importing the
    catalog classes here at run time would close an import cycle.
    """
    parent = getattr(item, "parent", None)
    if type(item).__name__ == "SchemaCatalogItem" and parent is not None:
        database, predicate = (
            parent.label,
            f"where t.table_schema = {sql_string(item.label)}",
        )
    else:
        database, predicate = item.label, ""

    driver.insert_text_in_new_buffer(
        dedent(
            f"""
            select
                t.table_catalog,
                t.table_schema,
                t.table_name,
                t.table_type,
                t.row_count,
                t.bytes,
                t.created,
                t.last_altered,
                t.comment
            from {quote_identifier(database)}.information_schema.tables as t
            {predicate}
            order by t.table_schema, t.table_name
            """.strip("\n")
        )
    )


def show_refresh_history(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    """A dynamic table's refresh history, which is how it is usually debugged."""
    if item.parent is None or item.parent.parent is None:
        driver.notify(
            f"Could not describe {item.label} due to a missing schema reference.",
            severity="error",
        )
        return
    driver.insert_text_in_new_buffer(
        dedent(
            f"""
            select *
            from table(
                {item.parent.parent.qualified_identifier}
                .information_schema.dynamic_table_refresh_history(
                    name_prefix => {sql_string(item.qualified_identifier)}
                )
            )
            order by data_timestamp desc
            """.strip("\n")
        )
    )


def insert_columns_at_cursor(
    item: "RelationCatalogItem", driver: "HarlequinDriver"
) -> None:
    if item.loaded:
        cols: Sequence[CatalogItem] = item.children
    else:
        cols = item.fetch_children()
    driver.insert_text_at_selection(text=",\n".join(c.query_name for c in cols))


def show_column_value_counts(
    item: "ColumnCatalogItem", driver: "HarlequinDriver"
) -> None:
    """The most common values of one column -- the usual first look at a field."""
    if item.parent is None:
        driver.notify(
            f"Could not profile {item.label} due to a missing table reference.",
            severity="error",
        )
        return
    driver.insert_text_in_new_buffer(
        dedent(
            f"""
            select
                {item.query_name} as value,
                count(*) as n
            from {item.parent.qualified_identifier}
            group by 1
            order by n desc
            limit 100
            """.strip("\n")
        )
    )
