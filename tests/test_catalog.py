from __future__ import annotations

import pytest
from harlequin.catalog import CatalogSearchResult, InteractiveCatalogItem

from harlequin_snowflake.adapter import HarlequinSnowflakeConnection
from harlequin_snowflake.catalog import (
    ColumnCatalogItem,
    DatabaseCatalogItem,
    RelationCatalogItem,
    SchemaCatalogItem,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def database_item(
    connection: HarlequinSnowflakeConnection, current_database: str
) -> DatabaseCatalogItem:
    catalog = connection.get_catalog()
    matches = [item for item in catalog.items if item.label == current_database]
    assert matches, f"{current_database} is missing from the catalog"
    item = matches[0]
    assert isinstance(item, DatabaseCatalogItem)
    return item


@pytest.fixture(scope="session")
def schema_item(
    database_item: DatabaseCatalogItem, current_schema: str
) -> SchemaCatalogItem:
    matches = [
        item for item in database_item.fetch_children() if item.label == current_schema
    ]
    assert matches, f"{current_schema} is missing from the catalog"
    return matches[0]


def test_catalog_top_level(connection: HarlequinSnowflakeConnection) -> None:
    catalog = connection.get_catalog()
    assert catalog.items
    for item in catalog.items:
        assert isinstance(item, DatabaseCatalogItem)
        assert isinstance(item, InteractiveCatalogItem)
        assert item.type_label == "db"
        assert item.qualified_identifier == f'"{item.label}"'
        # children are lazy, so nothing below the top level is loaded yet
        assert not item.children
        assert not item.loaded
    labels = [item.label for item in catalog.items]
    assert labels == sorted(labels)


def test_database_children_are_schemas(
    database_item: DatabaseCatalogItem, current_database: str
) -> None:
    schemas = database_item.fetch_children()
    assert schemas
    for schema in schemas:
        assert isinstance(schema, SchemaCatalogItem)
        assert schema.parent is database_item
        assert schema.type_label == "sch"
        assert schema.qualified_identifier == f'"{current_database}"."{schema.label}"'
        assert not schema.loaded


def test_schema_children_are_relations(schema_item: SchemaCatalogItem) -> None:
    relations = schema_item.fetch_children()
    if not relations:
        pytest.skip(f"{schema_item.qualified_identifier} has no relations.")
    for relation in relations:
        assert isinstance(relation, RelationCatalogItem)
        assert relation.parent is schema_item
        assert relation.type_name
        assert relation.qualified_identifier.startswith(
            schema_item.qualified_identifier
        )
        # the query name is schema-qualified, since the session's database is
        # already the one the item lives in
        assert relation.query_name.count(".") == 1
        assert not relation.loaded
    labels = [relation.label for relation in relations]
    assert labels == sorted(labels)


def test_relation_children_are_columns(schema_item: SchemaCatalogItem) -> None:
    relations = schema_item.fetch_children()
    if not relations:
        pytest.skip(f"{schema_item.qualified_identifier} has no relations.")
    relation = relations[0]
    columns = relation.fetch_children()
    assert columns, f"{relation.qualified_identifier} reported no columns"
    for column in columns:
        assert isinstance(column, ColumnCatalogItem)
        assert column.parent is relation
        # a column is a leaf; Harlequin must not try to expand it
        assert column.loaded
        assert column.type_label
        assert column.type_name
        assert column.query_name == f'"{column.label}"'
        assert column.qualified_identifier == (
            f'{relation.qualified_identifier}."{column.label}"'
        )


def test_every_catalog_item_has_interactions(
    schema_item: SchemaCatalogItem, database_item: DatabaseCatalogItem
) -> None:
    relations = schema_item.fetch_children()
    if not relations:
        pytest.skip(f"{schema_item.qualified_identifier} has no relations.")
    items = [database_item, schema_item, relations[0], *relations[0].fetch_children()]
    for item in items:
        assert item.INTERACTIONS, f"{type(item).__name__} has no interactions"
        for label, callback in item.INTERACTIONS:
            assert label and callable(callback)


def test_search_finds_a_relation_by_name(
    connection: HarlequinSnowflakeConnection, schema_item: SchemaCatalogItem
) -> None:
    relations = schema_item.fetch_children()
    if not relations:
        pytest.skip(f"{schema_item.qualified_identifier} has no relations.")
    target = relations[0].label
    results = connection.search_catalog(target, kind="relations")
    assert results
    for result in results:
        assert isinstance(result, CatalogSearchResult)
        # search only reports items whose label really contains the term
        assert target.casefold() in result.item.label.casefold()
        assert len(result.parents) == 2
    assert any(
        result.item.label == target
        and result.parents == (schema_item.parent.label, schema_item.label)  # type: ignore[union-attr]
        for result in results
    )


def test_search_finds_a_column_by_name(
    connection: HarlequinSnowflakeConnection, schema_item: SchemaCatalogItem
) -> None:
    relations = schema_item.fetch_children()
    if not relations:
        pytest.skip(f"{schema_item.qualified_identifier} has no relations.")
    columns = relations[0].fetch_children()
    target = columns[0].label
    results = connection.search_catalog(target, kind="columns")
    assert results
    for result in results:
        assert target.casefold() in result.item.label.casefold()
        assert len(result.parents) == 3


def test_search_all_reports_ancestors_before_descendants(
    connection: HarlequinSnowflakeConnection, current_database: str
) -> None:
    results = connection.search_catalog(current_database, kind="all")
    assert results
    seen: set[tuple[str, ...]] = set()
    for result in results:
        path = (*result.parents, result.item.label)
        # every ancestor path that this search also matched came first
        for depth in range(1, len(result.parents) + 1):
            ancestor = tuple(result.parents[:depth])
            if any(candidate[: len(ancestor)] == ancestor for candidate in seen):
                continue
        seen.add(path)
    depths = [len(result.parents) for result in results]
    assert min(depths) == 0, "an `all` search should report the database itself"


def test_search_for_nothing_finds_nothing(
    connection: HarlequinSnowflakeConnection,
) -> None:
    assert connection.search_catalog("") == []
    assert connection.search_catalog("zzz_no_such_object_zzz_harlequin") == []


def test_search_does_not_treat_underscores_as_wildcards(
    connection: HarlequinSnowflakeConnection,
) -> None:
    """A `_` in the term is literal, even though `SHOW ... LIKE` has no ESCAPE."""
    results = connection.search_catalog("zzz_qq", kind="relations")
    for result in results:
        assert "zzz_qq" in result.item.label.casefold()
