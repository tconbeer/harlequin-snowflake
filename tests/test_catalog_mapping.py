"""How a `SHOW OBJECTS` row picks the catalog item class that represents it."""

from __future__ import annotations

import pytest

from harlequin_snowflake.catalog import (
    DynamicTableCatalogItem,
    EventTableCatalogItem,
    ExternalTableCatalogItem,
    HybridTableCatalogItem,
    IcebergTableCatalogItem,
    MaterializedViewCatalogItem,
    SchemaCatalogItem,
    TableCatalogItem,
    TransientTableCatalogItem,
    ViewCatalogItem,
    relation_item_for_kind,
)


@pytest.fixture
def parent() -> SchemaCatalogItem:
    return SchemaCatalogItem(
        qualified_identifier='"DB"."SCH"',
        query_name='"DB"."SCH"',
        label="SCH",
        type_label="sch",
    )


@pytest.mark.parametrize(
    "row,expected_cls,expected_label",
    [
        ({"kind": "TABLE"}, TableCatalogItem, "t"),
        ({"kind": "VIEW"}, ViewCatalogItem, "v"),
        ({"kind": "MATERIALIZED_VIEW"}, MaterializedViewCatalogItem, "mv"),
        ({"kind": "MATERIALIZED VIEW"}, MaterializedViewCatalogItem, "mv"),
        ({"kind": "TABLE", "is_dynamic": "Y"}, DynamicTableCatalogItem, "dt"),
        ({"kind": "TABLE", "is_dynamic": True}, DynamicTableCatalogItem, "dt"),
        ({"kind": "TABLE", "is_iceberg": "Y"}, IcebergTableCatalogItem, "ice"),
        ({"kind": "TABLE", "is_hybrid": "Y"}, HybridTableCatalogItem, "hy"),
        ({"kind": "EXTERNAL TABLE"}, ExternalTableCatalogItem, "ext"),
        ({"kind": "EVENT TABLE"}, EventTableCatalogItem, "ev"),
        ({"kind": "TRANSIENT TABLE"}, TransientTableCatalogItem, "tr"),
        # `is_dynamic`/`is_iceberg` say N on an ordinary table, and are missing
        # entirely on a Snowflake version that does not report them
        (
            {"kind": "TABLE", "is_dynamic": "N", "is_iceberg": "N"},
            TableCatalogItem,
            "t",
        ),
        ({"kind": "TABLE", "is_dynamic": None}, TableCatalogItem, "t"),
        # a `SHOW COLUMNS` row names no kind at all
        ({}, TableCatalogItem, "t"),
    ],
)
def test_relation_item_for_kind(
    parent: SchemaCatalogItem,
    row: dict[str, object],
    expected_cls: type,
    expected_label: str,
) -> None:
    item = relation_item_for_kind(parent=parent, label="X", row=row)
    assert isinstance(item, expected_cls)
    assert item.type_label == expected_label
    assert item.qualified_identifier == '"DB"."SCH"."X"'
    assert item.query_name == '"SCH"."X"'
    assert item.parent is parent
    assert item.INTERACTIONS


def test_a_view_grants_as_a_view(parent: SchemaCatalogItem) -> None:
    """`SHOW GRANTS ON` needs the object type spelled the way Snowflake spells it."""
    view = relation_item_for_kind(parent=parent, label="V", row={"kind": "VIEW"})
    table = relation_item_for_kind(parent=parent, label="T", row={"kind": "TABLE"})
    assert view.GRANT_OBJECT_TYPE == "view"
    assert table.GRANT_OBJECT_TYPE == "table"


def test_a_quoted_name_stays_quoted(parent: SchemaCatalogItem) -> None:
    item = relation_item_for_kind(
        parent=parent, label='weird"name', row={"kind": "TABLE"}
    )
    assert item.qualified_identifier == '"DB"."SCH"."weird""name"'
