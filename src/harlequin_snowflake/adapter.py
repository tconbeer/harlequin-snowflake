from __future__ import annotations

import threading
from itertools import cycle
from typing import TYPE_CHECKING, Any, Sequence

from harlequin import (
    HarlequinAdapter,
    HarlequinCompletion,
    HarlequinConnection,
    HarlequinCursor,
    HarlequinTransactionMode,
)
from harlequin.catalog import Catalog, CatalogSearchKind, CatalogSearchResult
from harlequin.exception import HarlequinConnectionError, HarlequinQueryError
from snowflake.connector import DictCursor, SnowflakeConnection
from snowflake.connector import connect as snowflake_connect
from snowflake.connector.cursor import SnowflakeCursor
from snowflake.connector.errors import Error as SnowflakeError

from harlequin_snowflake.catalog import (
    ColumnCatalogItem,
    DatabaseCatalogItem,
    RelationCatalogItem,
    SchemaCatalogItem,
    relation_item_for_kind,
)
from harlequin_snowflake.cli_options import SNOWFLAKE_OPTIONS
from harlequin_snowflake.completions import get_completions
from harlequin_snowflake.conn_config import build_connect_kwargs, parse_conn_str
from harlequin_snowflake.sql import contains, like_pattern, quote_identifier, sql_string
from harlequin_snowflake.types import column_labels, short_type_from_type_code

if TYPE_CHECKING:
    from textual_fastdatatable.backend import AutoBackendType

CANCELLED_ERRNOS = frozenset({604, 606})
"""Snowflake's error codes for a statement that was aborted, not one that failed.

604 is `SQL execution canceled`, which is what `cancel()` provokes; 606 is the
same thing for an asynchronous job. A cancel is the user's own doing, so it is
reported as an empty result rather than as a query error.
"""


class HarlequinSnowflakeCursor(HarlequinCursor):
    def __init__(
        self, conn: HarlequinSnowflakeConnection, cur: SnowflakeCursor
    ) -> None:
        self.conn = conn
        self.cur = cur
        # copied, since the description is gone once the cursor is closed, and
        # columns() may be called after fetchall() closes it.
        self.description = list(cur.description or [])
        self._limit: int | None = None

    def columns(self) -> list[tuple[str, str]]:
        return [
            (
                col.name,
                short_type_from_type_code(col.type_code, scale=col.scale),
            )
            for col in self.description
        ]

    def set_limit(self, limit: int) -> HarlequinSnowflakeCursor:
        self._limit = limit
        return self

    def fetchall(self) -> AutoBackendType | None:
        try:
            table = self._fetch_arrow()
            if table is not None:
                return table
            if self._limit is None:
                return self.cur.fetchall()
            return self.cur.fetchmany(self._limit)
        except SnowflakeError as e:
            if getattr(e, "errno", None) in CANCELLED_ERRNOS:
                return None
            raise HarlequinQueryError(
                msg=f"{e.__class__.__name__}: {e}",
                title="Harlequin encountered an error while executing your query.",
            ) from e
        except Exception as e:
            raise HarlequinQueryError(
                msg=f"{e.__class__.__name__}: {e}",
                title="Harlequin encountered an error while executing your query.",
            ) from e
        finally:
            self.conn._forget(self.cur)
            self.cur.close()

    def _fetch_arrow(self) -> AutoBackendType | None:
        """The result set as an Arrow table, or None if this one is not Arrow.

        Snowflake returns most result sets in Arrow, which carries the column
        types with it and skips a conversion through Python objects. `SHOW` and
        `DESCRIBE` statements, `PUT`/`GET`, and an installation without the
        Arrow extension all come back as JSON instead, which the caller reads
        the ordinary way.
        """
        if getattr(self.cur, "_query_result_format", None) != "arrow":
            return None
        import pyarrow as pa

        try:
            if self._limit is None:
                return self.cur.fetch_arrow_all(force_return_table=True)
            batches: list[pa.Table] = []
            rows = 0
            for batch in self.cur.fetch_arrow_batches():
                batches.append(batch)
                rows += batch.num_rows
                if rows >= self._limit:
                    break
            if not batches:
                return self.cur.fetch_arrow_all(force_return_table=True)
            return pa.concat_tables(batches).slice(0, self._limit)
        except NotImplementedError:
            return None


class HarlequinSnowflakeConnection(HarlequinConnection):
    def __init__(
        self,
        conn_str: Sequence[str],
        *_: Any,
        init_message: str = "",
        options: dict[str, Any],
    ) -> None:
        self.init_message = init_message
        self.connect_kwargs = build_connect_kwargs(conn_str=conn_str, options=options)
        try:
            self.conn: SnowflakeConnection = snowflake_connect(**self.connect_kwargs)
        except Exception as e:
            raise HarlequinConnectionError(
                msg=f"{e.__class__.__name__}: {e}",
                title="Harlequin could not connect to Snowflake.",
            ) from e

        # every in-flight statement, so that cancel() knows what to abort. A
        # cursor is added before it is executed and removed when its results are
        # fetched, so the window it is cancellable in is the window it is running.
        self._in_flight: dict[SnowflakeCursor, str] = {}
        self._in_flight_lock = threading.Lock()

        self._transaction_modes = cycle(
            [
                HarlequinTransactionMode(label="Auto"),
                HarlequinTransactionMode(
                    label="Manual", commit=self.commit, rollback=self.rollback
                ),
            ]
        )
        self.toggle_transaction_mode()

    # ------------------------------------------------------------------ queries

    def execute(self, query: str) -> HarlequinCursor | None:
        cur = self.conn.cursor()
        self._remember(cur, query)
        try:
            cur.execute(query)
        except SnowflakeError as e:
            self._forget(cur)
            cur.close()
            if getattr(e, "errno", None) in CANCELLED_ERRNOS:
                return None
            raise HarlequinQueryError(
                msg=f"{e.msg or e}",
                title="Harlequin encountered an error while executing your query.",
            ) from e
        except Exception as e:
            self._forget(cur)
            cur.close()
            raise HarlequinQueryError(
                msg=f"{e.__class__.__name__}: {e}",
                title="Harlequin encountered an error while executing your query.",
            ) from e

        if cur.description:
            return HarlequinSnowflakeCursor(self, cur)
        self._forget(cur)
        cur.close()
        return None

    def cancel(self) -> None:
        """Aborts every statement `execute()` has running.

        The abort is addressed by the request ID the connector generated for the
        statement, which it sets before it sends the statement and which is
        therefore already readable from another thread while `execute()` is
        still blocked waiting for results -- the same mechanism the connector's
        own query timeout uses. The query ID would only be known once the
        statement had already finished.
        """
        with self._in_flight_lock:
            in_flight = list(self._in_flight.items())
        for cur, query in in_flight:
            request_id = getattr(cur, "_request_id", None)
            if request_id is None:
                continue
            try:
                self.conn._cancel_query(query, request_id)
            except Exception:
                # The statement finished on its own, or the connection is gone.
                # Either way there is nothing left to cancel.
                continue

    def _remember(self, cur: SnowflakeCursor, query: str) -> None:
        with self._in_flight_lock:
            self._in_flight[cur] = query

    def _forget(self, cur: SnowflakeCursor) -> None:
        with self._in_flight_lock:
            self._in_flight.pop(cur, None)

    def _query(self, sql: str) -> list[dict[str, Any]]:
        """One metadata query, as a list of rows keyed by lower-cased column name.

        Every catalog read goes through here, on its own cursor, so that it can
        run while the editor's own query is still running. Snowflake names the
        columns of a `SHOW` result in lower case already, but a `select` names
        them however it was written, so they are folded here.
        """
        try:
            with self.conn.cursor(DictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        except SnowflakeError as e:
            raise HarlequinQueryError(
                msg=f"{e.msg or e}",
                title="Snowflake raised an error while reading the catalog:",
            ) from e
        return [
            {str(key).lower(): value for key, value in row.items()}
            for row in rows
            if isinstance(row, dict)
        ]

    # ------------------------------------------------------------------- catalog

    def get_catalog(self) -> Catalog:
        return Catalog(
            items=[
                DatabaseCatalogItem.from_label(label=name, connection=self)
                for name in self._get_databases()
            ]
        )

    def _get_databases(self) -> list[str]:
        rows = self._query("show terse databases")
        return sorted(str(row["name"]) for row in rows if row.get("name"))

    def _get_schemas(self, database: str) -> list[str]:
        rows = self._query(
            f"show terse schemas in database {quote_identifier(database)}"
        )
        return sorted(str(row["name"]) for row in rows if row.get("name"))

    def _get_relations(self, database: str, schema: str) -> list[dict[str, Any]]:
        """The relations in one schema, each with the fields that name its kind.

        `SHOW OBJECTS` is one round trip for tables and views together, and it
        reports the flags that separate a dynamic table or an Iceberg table from
        an ordinary one, which `information_schema.tables` does not.
        """
        rows = self._query(
            "show objects in schema "
            f"{quote_identifier(database)}.{quote_identifier(schema)}"
        )
        return sorted(rows, key=lambda row: str(row.get("name") or ""))

    def _get_columns(
        self, database: str, schema: str, relation: str
    ) -> list[tuple[str, str, str]]:
        """One relation's columns, as (name, type_label, type_name).

        `SHOW COLUMNS` works the same on a table, a view, and every other kind
        of relation the catalog shows, which is why it is preferred here to
        `DESCRIBE`, and it reports the type as JSON, which `column_labels()`
        turns into the two labels the catalog wants.
        """
        rows = self._query(
            "show columns in "
            f"{quote_identifier(database)}.{quote_identifier(schema)}"
            f".{quote_identifier(relation)}"
        )
        columns: list[tuple[str, str, str]] = []
        for row in rows:
            name = row.get("column_name")
            if not name:
                continue
            type_label, type_name = column_labels(row.get("data_type"))
            columns.append((str(name), type_label, type_name))
        return columns

    # -------------------------------------------------------------------- search

    def search_catalog(
        self, term: str, kind: CatalogSearchKind = "all"
    ) -> list[CatalogSearchResult]:
        if not term:
            return []
        pattern = sql_string(like_pattern(term))
        databases: dict[str, DatabaseCatalogItem] = {}
        schemas: dict[tuple[str, str], SchemaCatalogItem] = {}
        relations: dict[tuple[str, str, str], RelationCatalogItem] = {}
        found: list[tuple[tuple[str, str, str, str], CatalogSearchResult]] = []

        def database_item(name: str) -> DatabaseCatalogItem:
            if name not in databases:
                databases[name] = DatabaseCatalogItem.from_label(
                    label=name, connection=self
                )
            return databases[name]

        def schema_item(database: str, schema: str) -> SchemaCatalogItem:
            key = (database, schema)
            if key not in schemas:
                schemas[key] = SchemaCatalogItem.from_parent(
                    parent=database_item(database), label=schema
                )
            return schemas[key]

        def relation_item(row: dict[str, Any]) -> RelationCatalogItem | None:
            database = row.get("database_name")
            schema = row.get("schema_name")
            name = row.get("table_name") or row.get("name")
            if not (database and schema and name):
                return None
            key = (str(database), str(schema), str(name))
            if key not in relations:
                relations[key] = relation_item_for_kind(
                    parent=schema_item(str(database), str(schema)),
                    label=str(name),
                    row=row,
                )
            return relations[key]

        if kind == "all":
            for row in self._query(f"show terse databases like {pattern}"):
                name = row.get("name")
                if not contains(term, name):
                    continue
                found.append(
                    (
                        (str(name), "", "", ""),
                        CatalogSearchResult(item=database_item(str(name))),
                    )
                )
            for row in self._query(f"show terse schemas like {pattern} in account"):
                database, name = row.get("database_name"), row.get("name")
                if not (database and contains(term, name)):
                    continue
                found.append(
                    (
                        (str(database), str(name), "", ""),
                        CatalogSearchResult(
                            item=schema_item(str(database), str(name)),
                            parents=(str(database),),
                        ),
                    )
                )

        if kind in ("all", "relations"):
            for row in self._query(f"show objects like {pattern} in account"):
                if not contains(term, row.get("name")):
                    continue
                item = relation_item(row)
                if item is None:
                    continue
                found.append(
                    (
                        (
                            str(row["database_name"]),
                            str(row["schema_name"]),
                            item.label,
                            "",
                        ),
                        CatalogSearchResult(
                            item=item,
                            parents=(
                                str(row["database_name"]),
                                str(row["schema_name"]),
                            ),
                        ),
                    )
                )

        if kind in ("all", "columns"):
            for row in self._query(f"show columns like {pattern} in account"):
                column = row.get("column_name")
                if not contains(term, column):
                    continue
                parent = relation_item(row)
                if parent is None:
                    continue
                type_label, type_name = column_labels(row.get("data_type"))
                found.append(
                    (
                        (
                            str(row["database_name"]),
                            str(row["schema_name"]),
                            parent.label,
                            str(column),
                        ),
                        CatalogSearchResult(
                            item=ColumnCatalogItem.from_parent(
                                parent=parent,
                                label=str(column),
                                type_label=type_label,
                                type_name=type_name,
                            ),
                            parents=(
                                str(row["database_name"]),
                                str(row["schema_name"]),
                                parent.label,
                            ),
                        ),
                    )
                )

        # an item's own path sorts it under its ancestors, since the levels it
        # does not have are empty strings and those sort first.
        found.sort(key=lambda pair: pair[0])
        return [result for _, result in found]

    # --------------------------------------------------------------- completions

    def get_completions(self) -> list[HarlequinCompletion]:
        return get_completions(self)

    # ----------------------------------------------------------------- lifecycle

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            # Harlequin is quitting; a connection that is already gone is fine.
            pass

    @property
    def transaction_mode(self) -> HarlequinTransactionMode:
        return self._transaction_mode

    def toggle_transaction_mode(self) -> HarlequinTransactionMode:
        self._transaction_mode = next(self._transaction_modes)
        self.conn.autocommit(self._transaction_mode.label == "Auto")
        return self._transaction_mode

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def execute_scalar(self, sql: str) -> Any:
        """The first column of the first row a statement returns, or None."""
        rows = self._query(sql)
        if not rows:
            return None
        return next(iter(rows[0].values()), None)


class HarlequinSnowflakeAdapter(HarlequinAdapter):
    ADAPTER_OPTIONS = SNOWFLAKE_OPTIONS
    IMPLEMENTS_CANCEL = True
    IMPLEMENTS_CATALOG_SEARCH = True
    # Snowflake has no read-only session or transaction mode for the server to
    # enforce, so this adapter does not offer a guarantee it could not keep.
    # Grant the connecting role only the privileges it should have instead.
    IMPLEMENTS_READ_ONLY = False
    ADAPTER_DETAILS = (
        "**harlequin-snowflake** connects with the official "
        "[snowflake-connector-python](https://docs.snowflake.com"
        "/en/developer-guide/python-connector/python-connector) driver, so "
        "every authenticator, `connections.toml` entry, and session parameter "
        "the connector supports works here."
    )

    def __init__(
        self,
        conn_str: Sequence[str],
        **options: Any,
    ) -> None:
        self.conn_str = conn_str
        # Only the options the user actually set are kept, so that a
        # connections.toml entry and the connector's own defaults survive.
        self.options = {
            key: value
            for key, value in options.items()
            if value is not None and value != "" and key != "read_only"
        }

    @property
    def connection_id(self) -> str | None:
        """The account and session context, which is what a cached catalog is for."""
        try:
            named, from_conn_str = parse_conn_str(self.conn_str)
        except Exception:
            return None
        kwargs = {**from_conn_str, **self.options}
        account = kwargs.get("account") or named or kwargs.get("connection_name")
        if not account:
            return None
        database = kwargs.get("database") or ""
        schema = kwargs.get("schema") or ""
        return f"{account}/{database}.{schema}".rstrip("/.")

    def connect(self) -> HarlequinSnowflakeConnection:
        return HarlequinSnowflakeConnection(self.conn_str, options=dict(self.options))
