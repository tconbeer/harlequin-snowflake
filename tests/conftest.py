"""Fixtures for the test suite.

The integration tests run against a real Snowflake account and are strictly
read-only: they introspect whatever objects the account already has and never
create, alter, or drop anything. Tests that need a connection are skipped when
none is configured, so the unit tests still run anywhere.

There are two ways to configure one:

* A Harlequin profile in `.harlequin.toml` in the repo root -- the same file
  `make serve` uses. The profile named by `HARLEQUIN_SNOWFLAKE_TEST_PROFILE`,
  or the file's `default_profile`, is used if its adapter is this one.
* An entry in the connector's own `connections.toml`, named by
  `HARLEQUIN_SNOWFLAKE_TEST_CONNECTION`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Generator

import pytest

from harlequin_snowflake.adapter import (
    HarlequinSnowflakeAdapter,
    HarlequinSnowflakeConnection,
)

if sys.version_info < (3, 11):
    import tomli as tomllib
else:
    import tomllib

HARLEQUIN_CONFIG = Path(__file__).parent.parent / ".harlequin.toml"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: needs a real Snowflake account; read-only.",
    )


def _profile_options() -> dict[str, Any] | None:
    """The adapter options in the configured Harlequin profile, if there is one.

    Only keys this adapter declares as options are kept, so that Harlequin's own
    profile settings -- the theme, the keymap, the row limit -- are not passed
    to the connector as connection parameters.
    """
    if not HARLEQUIN_CONFIG.is_file():
        return None
    with HARLEQUIN_CONFIG.open("rb") as f:
        config = tomllib.load(f)
    profiles = config.get("profiles") or {}
    name = os.environ.get("HARLEQUIN_SNOWFLAKE_TEST_PROFILE") or config.get(
        "default_profile"
    )
    profile = profiles.get(name) if name else None
    if not isinstance(profile, dict) or profile.get("adapter") != "snowflake":
        return None
    declared = {
        option.name for option in HarlequinSnowflakeAdapter.ADAPTER_OPTIONS or []
    }
    return {key: value for key, value in profile.items() if key in declared}


@pytest.fixture(scope="session")
def adapter() -> HarlequinSnowflakeAdapter:
    options = _profile_options()
    if options:
        return HarlequinSnowflakeAdapter(conn_str=(), **options)
    connection_name = os.environ.get("HARLEQUIN_SNOWFLAKE_TEST_CONNECTION", "")
    if connection_name:
        return HarlequinSnowflakeAdapter(conn_str=(connection_name,))
    pytest.skip(
        "No Snowflake connection configured. Add a snowflake profile to "
        ".harlequin.toml, or set HARLEQUIN_SNOWFLAKE_TEST_CONNECTION to the "
        "name of a connections.toml entry."
    )


@pytest.fixture(scope="session")
def connection(
    adapter: HarlequinSnowflakeAdapter,
) -> Generator[HarlequinSnowflakeConnection, None, None]:
    """One session-scoped connection, shared by every integration test.

    Session-scoped because authenticating is the slow part, and because an
    interactive authenticator would otherwise prompt once per test.
    """
    conn = adapter.connect()
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def current_database(connection: HarlequinSnowflakeConnection) -> str:
    database = connection.execute_scalar("select current_database()")
    if not database:
        pytest.skip("The test connection has no current database.")
    return str(database)


@pytest.fixture(scope="session")
def current_schema(connection: HarlequinSnowflakeConnection) -> str:
    schema = connection.execute_scalar("select current_schema()")
    if schema:
        return str(schema)
    # A profile may set only a database. Any schema in it will do, since these
    # tests only read.
    schemas = [
        name
        for name in connection._get_schemas(str(connection.conn.database))
        if name.upper() != "INFORMATION_SCHEMA"
    ]
    if not schemas:
        pytest.skip("The test connection's database has no readable schema.")
    return schemas[0]
