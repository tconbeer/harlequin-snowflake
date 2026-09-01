from __future__ import annotations

import sys
from typing import Any

import pytest
from harlequin.adapter import HarlequinAdapter, HarlequinConnection, HarlequinCursor
from harlequin.catalog import Catalog
from harlequin.exception import HarlequinConnectionError, HarlequinQueryError
from harlequin.options import AbstractOption
from textual_fastdatatable.backend import create_backend

from harlequin_snowflake import adapter as adapter_module
from harlequin_snowflake.adapter import (
    HarlequinSnowflakeAdapter,
    HarlequinSnowflakeConnection,
    arrow_fetch_available,
)

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points


def test_plugin_discovery() -> None:
    PLUGIN_NAME = "snowflake"
    eps = entry_points(group="harlequin.adapter")
    assert eps[PLUGIN_NAME]
    adapter_cls = eps[PLUGIN_NAME].load()
    assert issubclass(adapter_cls, HarlequinAdapter)
    assert adapter_cls == HarlequinSnowflakeAdapter


def test_adapter_declares_its_capabilities() -> None:
    assert HarlequinSnowflakeAdapter.IMPLEMENTS_CANCEL is True
    assert HarlequinSnowflakeAdapter.IMPLEMENTS_CATALOG_SEARCH is True
    # Snowflake has no server-enforced read-only mode, so the adapter does not
    # claim one.
    assert HarlequinSnowflakeAdapter.IMPLEMENTS_READ_ONLY is False
    assert HarlequinSnowflakeAdapter.ADAPTER_DETAILS


def test_every_option_is_wellformed() -> None:
    options = HarlequinSnowflakeAdapter.ADAPTER_OPTIONS
    assert options
    assert all(isinstance(option, AbstractOption) for option in options)
    names = [option.name for option in options]
    assert len(names) == len(set(names))
    # click needs each short declaration to be unique across the whole adapter.
    short_decls = [decl for option in options for decl in option.short_decls]
    assert len(short_decls) == len(set(short_decls))


def test_no_option_shadows_a_harlequin_flag() -> None:
    """Adapter options share one command with Harlequin's own and every other
    installed adapter's, so a short declaration that collides silently shadows
    the other one."""
    from harlequin.cli import build_cli

    cmd = build_cli(["harlequin", "-a", "snowflake", "--help"])
    ours = {
        decl
        for option in HarlequinSnowflakeAdapter.ADAPTER_OPTIONS or []
        for decl in option.short_decls
    }
    theirs: dict[str, str] = {}
    for param in cmd.params:
        if param.name in {
            option.name for option in HarlequinSnowflakeAdapter.ADAPTER_OPTIONS or []
        }:
            continue
        for decl in list(param.opts) + list(param.secondary_opts):
            theirs[decl] = str(param.name)
    collisions = {decl: theirs[decl] for decl in ours if decl in theirs}
    assert not collisions, f"these short flags are already taken: {collisions}"


def test_secrets_are_marked_secret() -> None:
    options = {
        option.name: option
        for option in HarlequinSnowflakeAdapter.ADAPTER_OPTIONS or []
    }
    for name in (
        "password",
        "token",
        "passcode",
        "private_key_file_pwd",
        "oauth_client_secret",
        "proxy_password",
    ):
        assert options[name].secret is True, f"{name} should be marked secret"


def test_arrow_fetch_is_available() -> None:
    """The Arrow fetch path must be reachable in a default installation.

    The connector reaches pyarrow through an optional-dependency shim that only
    resolves when pandas imports; pyarrow alone -- which Harlequin installs on
    its own -- leaves it inert, and every `fetch_arrow_all` raises
    MissingDependencyError. That is why this package depends on the connector's
    `pandas` extra, and this test is what notices if that dependency is dropped.
    """
    assert arrow_fetch_available() is True


def test_init_ignores_unexpected_kwargs() -> None:
    adapter = HarlequinSnowflakeAdapter(
        conn_str=("snowflake://acct",), foo=1, bar="baz", read_only=True
    )
    assert "foo" not in adapter.options or adapter.options["foo"] == 1
    assert "read_only" not in adapter.options


@pytest.mark.parametrize(
    "conn_str,options,expected",
    [
        (("snowflake://me@myorg-acct/DB/SCH",), {}, "myorg-acct/DB.SCH"),
        (("snowflake://me@myorg-acct/DB",), {}, "myorg-acct/DB"),
        (("snowflake://me@myorg-acct",), {}, "myorg-acct"),
        (("snowflake://me@myorg-acct",), {"database": "OTHER"}, "myorg-acct/OTHER"),
        (("my_conn",), {}, "my_conn"),
        ((), {"account": "acct", "schema": "S"}, "acct/.S"),
        ((), {}, None),
    ],
)
def test_connection_id(
    conn_str: tuple[str, ...], options: dict[str, Any], expected: str | None
) -> None:
    adapter = HarlequinSnowflakeAdapter(conn_str=conn_str, **options)
    assert adapter.connection_id == expected


def test_connection_id_survives_a_bad_conn_str() -> None:
    adapter = HarlequinSnowflakeAdapter(conn_str=("one", "two"))
    assert adapter.connection_id is None


def test_connect_raises_connection_error_for_a_bad_account() -> None:
    with pytest.raises(HarlequinConnectionError):
        HarlequinSnowflakeAdapter(
            conn_str=("snowflake://nobody:nothing@harlequin-no-such-account",),
            login_timeout=5,
            network_timeout=5,
        ).connect()


# --------------------------------------------------------------- integration


@pytest.mark.integration
def test_connect(connection: HarlequinSnowflakeConnection) -> None:
    assert isinstance(connection, HarlequinConnection)


@pytest.mark.integration
def test_execute_select(connection: HarlequinSnowflakeConnection) -> None:
    cur = connection.execute("select 1 as a, 'two' as b, null as c")
    assert isinstance(cur, HarlequinCursor)
    # Snowflake types an untyped NULL literal as TEXT
    assert cur.columns() == [("A", "#"), ("B", "s"), ("C", "s")]
    data = cur.fetchall()
    backend = create_backend(data)
    assert backend.column_count == 3
    assert backend.row_count == 1


@pytest.mark.integration
def test_execute_typed_columns(connection: HarlequinSnowflakeConnection) -> None:
    cur = connection.execute(
        """
        select
            1::int as i,
            1.5::number(10, 2) as n,
            'x'::varchar as v,
            true as b,
            current_date() as d,
            current_timestamp() as ts,
            [1, 2]::array as arr,
            {'k': 'v'}::object as obj,
            to_binary('ab', 'hex') as bin
        """
    )
    assert cur is not None
    assert [label for _, label in cur.columns()] == [
        "#",
        "#.#",
        "s",
        "t/f",
        "d",
        "ts",
        "[]",
        "{}",
        "b",
    ]
    assert cur.fetchall() is not None


@pytest.mark.integration
def test_session_statement_returns_a_status_result(
    connection: HarlequinSnowflakeConnection,
) -> None:
    """Snowflake answers a statement that returns no data with a one-row status
    result rather than with nothing, so Harlequin shows it in the data table.
    `alter session` is the read-only way to check that, since this suite never
    writes."""
    cur = connection.execute("alter session set query_tag = 'harlequin-test'")
    assert cur is not None
    assert create_backend(cur.fetchall()).row_count == 1


@pytest.mark.integration
def test_execute_raises_query_error(
    connection: HarlequinSnowflakeConnection,
) -> None:
    with pytest.raises(HarlequinQueryError):
        connection.execute("select not valid sql from")


@pytest.mark.integration
def test_set_limit(connection: HarlequinSnowflakeConnection) -> None:
    cur = connection.execute(
        "select seq4() as n from table(generator(rowcount => 1000))"
    )
    assert cur is not None
    data = cur.set_limit(10).fetchall()
    assert create_backend(data).row_count == 10


@pytest.mark.integration
def test_show_statement_falls_back_from_arrow(
    connection: HarlequinSnowflakeConnection,
) -> None:
    """`SHOW` results come back as JSON, not Arrow, and must still fetch."""
    cur = connection.execute("show terse databases")
    assert cur is not None
    assert cur.columns()
    assert cur.fetchall() is not None


@pytest.mark.integration
def test_rows_fall_back_to_the_same_values_as_arrow(
    connection: HarlequinSnowflakeConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row path is what a JSON result set uses, and must agree with Arrow."""
    query = (
        "select 1 as a, 'two' as b, null as c, 90071992547409.93::number(18, 2) as d"
    )

    cur = connection.execute(query)
    assert cur is not None
    from_arrow = create_backend(cur.fetchall()).get_row_at(0)

    monkeypatch.setattr(adapter_module, "arrow_fetch_available", lambda: False)
    cur = connection.execute(query)
    assert cur is not None
    from_rows = create_backend(cur.fetchall()).get_row_at(0)

    assert [str(value) for value in from_arrow] == [str(value) for value in from_rows]


@pytest.mark.integration
def test_exact_numbers_are_not_rounded_to_floats(
    connection: HarlequinSnowflakeConnection,
) -> None:
    """Snowflake's Arrow default renders NUMBER as float64, which rounds away
    digits past about 15 significant ones. This adapter turns that off."""
    cur = connection.execute("select 90071992547409.93::number(18, 2) as d")
    assert cur is not None
    [[value]] = (create_backend(cur.fetchall()).get_row_at(0),)
    assert str(value) == "90071992547409.93"


@pytest.mark.integration
def test_empty_result_set(connection: HarlequinSnowflakeConnection) -> None:
    cur = connection.execute("select 1 as a where false")
    assert cur is not None
    data = cur.fetchall()
    assert create_backend(data).row_count == 0


@pytest.mark.integration
def test_transaction_modes(connection: HarlequinSnowflakeConnection) -> None:
    start = connection.transaction_mode
    assert start is not None
    other = connection.toggle_transaction_mode()
    assert other is not None
    assert other.label != start.label
    assert {start.label, other.label} == {"Auto", "Manual"}
    # Manual mode is the one that offers commit and rollback.
    manual = other if other.label == "Manual" else start
    assert manual.commit is not None and manual.rollback is not None
    back = connection.toggle_transaction_mode()
    assert back.label == start.label


@pytest.mark.integration
def test_cancel_stops_a_long_query(
    connection: HarlequinSnowflakeConnection,
) -> None:
    """`cancel()` runs on another thread while `execute()` is still blocked."""
    import threading

    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["cursor"] = connection.execute("call system$wait(60, 'SECONDS')")
        except BaseException as e:  # noqa: BLE001
            result["error"] = e

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    # give the statement time to reach the server, then cancel it
    deadline = 30.0
    waited = 0.0
    while waited < deadline and not connection._in_flight:
        threading.Event().wait(0.1)
        waited += 0.1
    threading.Event().wait(2.0)
    connection.cancel()
    worker.join(timeout=deadline)
    assert not worker.is_alive(), "cancel() did not stop the query"
    # a cancelled statement is not an error the user has to see
    assert result.get("cursor") is None
    assert "error" not in result, result.get("error")


@pytest.mark.integration
def test_get_completions(connection: HarlequinSnowflakeConnection) -> None:
    completions = connection.get_completions()
    labels = {c.label for c in completions}
    assert "select" in labels
    assert "qualify" in labels
    # a built-in function, from SHOW FUNCTIONS
    assert "to_timestamp_ntz" in labels or "coalesce" in labels
    # completions arrive sorted by (priority, label), which is what Harlequin
    # relies on to rank them
    assert completions == sorted(completions)


@pytest.mark.integration
def test_get_catalog_is_lazy(connection: HarlequinSnowflakeConnection) -> None:
    catalog = connection.get_catalog()
    assert isinstance(catalog, Catalog)
    assert catalog.items
    assert all(not item.children and not item.loaded for item in catalog.items)  # type: ignore[attr-defined]
