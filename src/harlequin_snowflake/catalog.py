from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from harlequin.catalog import InteractiveCatalogItem

from harlequin_snowflake.interactions import (
    execute_drop_database_statement,
    execute_drop_dynamic_table_statement,
    execute_drop_external_table_statement,
    execute_drop_iceberg_table_statement,
    execute_drop_materialized_view_statement,
    execute_drop_schema_statement,
    execute_drop_table_statement,
    execute_drop_view_statement,
    execute_use_database_statement,
    execute_use_schema_statement,
    insert_columns_at_cursor,
    show_column_value_counts,
    show_database_ddl,
    show_describe_relation,
    show_grants,
    show_list_objects,
    show_refresh_history,
    show_row_count,
    show_sample,
    show_schema_ddl,
    show_select_star,
    show_table_ddl,
    show_view_definition,
)
from harlequin_snowflake.sql import quote_identifier

if TYPE_CHECKING:
    from harlequin_snowflake.adapter import HarlequinSnowflakeConnection


@dataclass
class ColumnCatalogItem(InteractiveCatalogItem["HarlequinSnowflakeConnection"]):
    INTERACTIONS = [
        ("Show Value Counts", show_column_value_counts),
    ]
    parent: "RelationCatalogItem" | None = None

    @classmethod
    def from_parent(
        cls,
        parent: "RelationCatalogItem",
        label: str,
        type_label: str,
        type_name: str | None = None,
    ) -> "ColumnCatalogItem":
        return cls(
            qualified_identifier=(
                f"{parent.qualified_identifier}.{quote_identifier(label)}"
            ),
            query_name=quote_identifier(label),
            label=label,
            type_label=type_label,
            type_name=type_name,
            connection=parent.connection,
            parent=parent,
            loaded=True,
        )


@dataclass
class RelationCatalogItem(InteractiveCatalogItem["HarlequinSnowflakeConnection"]):
    """A table, view, or any of the other things a schema holds columns in."""

    INTERACTIONS = [
        ("Insert Columns at Cursor", insert_columns_at_cursor),
        ("Preview Data", show_select_star),
        ("Describe Relation", show_describe_relation),
        ("Show Grants", show_grants),
    ]
    GRANT_OBJECT_TYPE: ClassVar[str] = "table"
    """What `SHOW GRANTS ON` calls this kind of object."""

    TYPE_LABEL: ClassVar[str] = "t"
    DEFAULT_TYPE_NAME: ClassVar[str] = "TABLE"
    parent: "SchemaCatalogItem" | None = None

    @classmethod
    def from_parent(
        cls,
        parent: "SchemaCatalogItem",
        label: str,
        type_name: str | None = None,
    ) -> "RelationCatalogItem":
        return cls(
            qualified_identifier=(
                f"{parent.qualified_identifier}.{quote_identifier(label)}"
            ),
            query_name=(f"{quote_identifier(parent.label)}.{quote_identifier(label)}"),
            label=label,
            type_label=cls.TYPE_LABEL,
            type_name=type_name or cls.DEFAULT_TYPE_NAME,
            connection=parent.connection,
            parent=parent,
        )

    def fetch_children(self) -> list[ColumnCatalogItem]:
        if self.parent is None or self.parent.parent is None or self.connection is None:
            return []
        return [
            ColumnCatalogItem.from_parent(
                parent=self,
                label=name,
                type_label=type_label,
                type_name=type_name,
            )
            for name, type_label, type_name in self.connection._get_columns(
                self.parent.parent.label, self.parent.label, self.label
            )
        ]


class TableCatalogItem(RelationCatalogItem):
    INTERACTIONS = RelationCatalogItem.INTERACTIONS + [
        ("Sample Data", show_sample),
        ("Count Rows", show_row_count),
        ("Show DDL", show_table_ddl),
        ("Drop Table", execute_drop_table_statement),
    ]
    TYPE_LABEL = "t"
    DEFAULT_TYPE_NAME = "TABLE"


class TransientTableCatalogItem(TableCatalogItem):
    TYPE_LABEL = "tr"
    DEFAULT_TYPE_NAME = "TRANSIENT TABLE"


class TemporaryTableCatalogItem(TableCatalogItem):
    TYPE_LABEL = "tmp"
    DEFAULT_TYPE_NAME = "TEMPORARY TABLE"


class HybridTableCatalogItem(TableCatalogItem):
    TYPE_LABEL = "hy"
    DEFAULT_TYPE_NAME = "HYBRID TABLE"


class EventTableCatalogItem(TableCatalogItem):
    TYPE_LABEL = "ev"
    DEFAULT_TYPE_NAME = "EVENT TABLE"


class IcebergTableCatalogItem(RelationCatalogItem):
    INTERACTIONS = RelationCatalogItem.INTERACTIONS + [
        ("Sample Data", show_sample),
        ("Count Rows", show_row_count),
        ("Show DDL", show_table_ddl),
        ("Drop Iceberg Table", execute_drop_iceberg_table_statement),
    ]
    TYPE_LABEL = "ice"
    DEFAULT_TYPE_NAME = "ICEBERG TABLE"


class ExternalTableCatalogItem(RelationCatalogItem):
    INTERACTIONS = RelationCatalogItem.INTERACTIONS + [
        ("Count Rows", show_row_count),
        ("Show DDL", show_table_ddl),
        ("Drop External Table", execute_drop_external_table_statement),
    ]
    TYPE_LABEL = "ext"
    DEFAULT_TYPE_NAME = "EXTERNAL TABLE"


class DynamicTableCatalogItem(RelationCatalogItem):
    INTERACTIONS = RelationCatalogItem.INTERACTIONS + [
        ("Count Rows", show_row_count),
        ("Show DDL", show_table_ddl),
        ("Show Refresh History", show_refresh_history),
        ("Drop Dynamic Table", execute_drop_dynamic_table_statement),
    ]
    TYPE_LABEL = "dt"
    DEFAULT_TYPE_NAME = "DYNAMIC TABLE"


class ViewCatalogItem(RelationCatalogItem):
    INTERACTIONS = RelationCatalogItem.INTERACTIONS + [
        ("Show View Definition", show_view_definition),
        ("Drop View", execute_drop_view_statement),
    ]
    GRANT_OBJECT_TYPE = "view"
    TYPE_LABEL = "v"
    DEFAULT_TYPE_NAME = "VIEW"


class MaterializedViewCatalogItem(RelationCatalogItem):
    INTERACTIONS = RelationCatalogItem.INTERACTIONS + [
        ("Count Rows", show_row_count),
        ("Show View Definition", show_view_definition),
        ("Drop Materialized View", execute_drop_materialized_view_statement),
    ]
    GRANT_OBJECT_TYPE = "materialized view"
    TYPE_LABEL = "mv"
    DEFAULT_TYPE_NAME = "MATERIALIZED VIEW"


@dataclass
class SchemaCatalogItem(InteractiveCatalogItem["HarlequinSnowflakeConnection"]):
    INTERACTIONS = [
        ("Use Schema", execute_use_schema_statement),
        ("List Objects", show_list_objects),
        ("Show DDL", show_schema_ddl),
        ("Show Grants", show_grants),
        ("Drop Schema", execute_drop_schema_statement),
    ]
    GRANT_OBJECT_TYPE: ClassVar[str] = "schema"
    parent: "DatabaseCatalogItem" | None = None

    @classmethod
    def from_parent(
        cls, parent: "DatabaseCatalogItem", label: str
    ) -> "SchemaCatalogItem":
        identifier = f"{parent.qualified_identifier}.{quote_identifier(label)}"
        return cls(
            qualified_identifier=identifier,
            query_name=identifier,
            label=label,
            type_label="sch",
            type_name="SCHEMA",
            connection=parent.connection,
            parent=parent,
        )

    def fetch_children(self) -> list[RelationCatalogItem]:
        if self.parent is None or self.connection is None:
            return []
        return [
            relation_item_for_kind(parent=self, label=str(row["name"]), row=row)
            for row in self.connection._get_relations(self.parent.label, self.label)
            if row.get("name")
        ]


@dataclass
class DatabaseCatalogItem(InteractiveCatalogItem["HarlequinSnowflakeConnection"]):
    INTERACTIONS = [
        ("Use Database", execute_use_database_statement),
        ("List Objects", show_list_objects),
        ("Show DDL", show_database_ddl),
        ("Show Grants", show_grants),
        ("Drop Database", execute_drop_database_statement),
    ]
    GRANT_OBJECT_TYPE: ClassVar[str] = "database"

    @classmethod
    def from_label(
        cls, label: str, connection: "HarlequinSnowflakeConnection"
    ) -> "DatabaseCatalogItem":
        identifier = quote_identifier(label)
        return cls(
            qualified_identifier=identifier,
            query_name=identifier,
            label=label,
            type_label="db",
            type_name="DATABASE",
            connection=connection,
        )

    def fetch_children(self) -> list[SchemaCatalogItem]:
        if self.connection is None:
            return []
        return [
            SchemaCatalogItem.from_parent(parent=self, label=name)
            for name in self.connection._get_schemas(self.label)
        ]


def _is_yes(value: Any) -> bool:
    """Whether a `SHOW` result's Y/N flag says yes.

    Snowflake spells these `Y`/`N`, but a JSON result can hand back a real
    boolean, and a column that this account's Snowflake version does not have
    arrives as None.
    """
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in ("Y", "YES", "TRUE")


def relation_item_for_kind(
    parent: SchemaCatalogItem, label: str, row: dict[str, Any]
) -> RelationCatalogItem:
    """The class that matches a `SHOW OBJECTS` (or `SHOW COLUMNS`) row.

    `kind` separates tables from views; the flags beside it separate the kinds
    of table that Snowflake reports as plain `TABLE`. A row that names no kind
    at all -- a `SHOW COLUMNS` row, which does not have the column -- lands on
    the plain table, which carries the interactions every relation supports.
    """
    kind = str(row.get("kind") or "").strip().upper().replace("_", " ")

    if "MATERIALIZED" in kind:
        return MaterializedViewCatalogItem.from_parent(
            parent=parent, label=label, type_name=kind
        )
    if "VIEW" in kind:
        return ViewCatalogItem.from_parent(parent=parent, label=label, type_name=kind)
    if _is_yes(row.get("is_dynamic")) or "DYNAMIC" in kind:
        return DynamicTableCatalogItem.from_parent(
            parent=parent, label=label, type_name="DYNAMIC TABLE"
        )
    if _is_yes(row.get("is_iceberg")) or "ICEBERG" in kind:
        return IcebergTableCatalogItem.from_parent(
            parent=parent, label=label, type_name="ICEBERG TABLE"
        )
    if _is_yes(row.get("is_hybrid")) or "HYBRID" in kind:
        return HybridTableCatalogItem.from_parent(
            parent=parent, label=label, type_name="HYBRID TABLE"
        )
    if _is_yes(row.get("is_event")) or "EVENT" in kind:
        return EventTableCatalogItem.from_parent(
            parent=parent, label=label, type_name="EVENT TABLE"
        )
    if "EXTERNAL" in kind:
        return ExternalTableCatalogItem.from_parent(
            parent=parent, label=label, type_name="EXTERNAL TABLE"
        )
    if "TEMPORARY" in kind:
        return TemporaryTableCatalogItem.from_parent(
            parent=parent, label=label, type_name="TEMPORARY TABLE"
        )
    if "TRANSIENT" in kind:
        return TransientTableCatalogItem.from_parent(
            parent=parent, label=label, type_name="TRANSIENT TABLE"
        )
    return TableCatalogItem.from_parent(
        parent=parent, label=label, type_name=kind or None
    )
