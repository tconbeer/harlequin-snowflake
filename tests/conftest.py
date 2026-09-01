"""Fixtures for the test suite.

The integration tests run against a real Snowflake account and are strictly
read-only: they introspect whatever objects the account already has and never
create, alter, or drop anything. Tests that need a connection are skipped when
none is configured, so the unit tests still run anywhere.

Configure a connection by adding an entry to `~/.snowflake/connections.toml`
and naming it in the `HARLEQUIN_SNOWFLAKE_TEST_CONNECTION` environment
variable, e.g.

    [harlequin_test]
    account = "myorg-myaccount"
    user = "..."
    authenticator = "SNOWFLAKE_JWT"
    private_key_file = "~/.snowflake/rsa_key.p8"
    warehouse = "..."
    role = "..."
"""

from __future__ import annotations

import os
from typing import Generator

import pytest

from harlequin_snowflake.adapter import (
    HarlequinSnowflakeAdapter,
    HarlequinSnowflakeConnection,
)

TEST_CONNECTION_NAME = os.environ.get("HARLEQUIN_SNOWFLAKE_TEST_CONNECTION", "")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: needs a real Snowflake account; read-only.",
    )


@pytest.fixture(scope="session")
def connection_name() -> str:
    if not TEST_CONNECTION_NAME:
        pytest.skip(
            "Set HARLEQUIN_SNOWFLAKE_TEST_CONNECTION to the name of a "
            "connections.toml entry to run the integration tests."
        )
    return TEST_CONNECTION_NAME


@pytest.fixture(scope="session")
def connection(
    connection_name: str,
) -> Generator[HarlequinSnowflakeConnection, None, None]:
    """One session-scoped connection, shared by every integration test.

    Session-scoped because authenticating is the slow part, and because an
    interactive authenticator would otherwise prompt once per test.
    """
    conn = HarlequinSnowflakeAdapter(conn_str=(connection_name,)).connect()
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
    if not schema:
        pytest.skip("The test connection has no current schema.")
    return str(schema)


@pytest.fixture(scope="session")
def a_relation(
    connection: HarlequinSnowflakeConnection,
    current_database: str,
    current_schema: str,
) -> dict[str, str]:
    """The first relation in the session's schema, for the tests that need one."""
    relations = connection._get_relations(current_database, current_schema)
    if not relations:
        pytest.skip(
            f"{current_database}.{current_schema} has no relations to introspect."
        )
    return {
        "database": current_database,
        "schema": current_schema,
        "name": str(relations[0]["name"]),
    }
