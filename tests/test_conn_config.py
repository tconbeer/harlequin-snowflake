from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harlequin.exception import HarlequinConfigError, HarlequinConnectionError

from harlequin_snowflake.conn_config import (
    build_connect_kwargs,
    coerce_param,
    parse_conn_str,
)


def test_empty_conn_str() -> None:
    assert parse_conn_str(()) == (None, {})
    assert parse_conn_str(("",)) == (None, {})
    assert parse_conn_str(("   ",)) == (None, {})


def test_bare_string_names_a_connections_toml_entry() -> None:
    assert parse_conn_str(("my_dev_account",)) == ("my_dev_account", {})


def test_url_parses_into_connector_params() -> None:
    name, params = parse_conn_str(
        ("snowflake://me:s3cret@myorg-myacct/MY_DB/MY_SCHEMA?warehouse=WH&role=DEV",)
    )
    assert name is None
    assert params == {
        "account": "myorg-myacct",
        "user": "me",
        "password": "s3cret",
        "database": "MY_DB",
        "schema": "MY_SCHEMA",
        "warehouse": "WH",
        "role": "DEV",
    }


def test_url_percent_decodes_credentials() -> None:
    _, params = parse_conn_str(("snowflake://my%40user:p%2Fw%40rd@acct",))
    assert params["user"] == "my@user"
    assert params["password"] == "p/w@rd"


def test_url_may_name_only_an_account() -> None:
    assert parse_conn_str(("snowflake://myorg-myacct",)) == (
        None,
        {"account": "myorg-myacct"},
    )


def test_url_coerces_typed_query_params() -> None:
    _, params = parse_conn_str(
        ("snowflake://acct?login_timeout=45&client_session_keep_alive=false",)
    )
    assert params["login_timeout"] == 45
    assert params["client_session_keep_alive"] is False


@pytest.mark.parametrize(
    "conn_str",
    [
        ("postgresql://foo/bar",),
        ("snowflake://acct/db/schema/extra",),
    ],
)
def test_bad_url_raises_connection_error(conn_str: tuple[str, ...]) -> None:
    with pytest.raises(HarlequinConnectionError):
        parse_conn_str(conn_str)


def test_multiple_conn_strs_raise() -> None:
    with pytest.raises(HarlequinConnectionError):
        parse_conn_str(("one", "two"))


@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("port", "443", 443),
        ("login_timeout", 30, 30),
        ("client_session_keep_alive", "yes", True),
        ("client_session_keep_alive", "OFF", False),
        ("client_session_keep_alive", True, True),
        ("session_parameters", '{"QUERY_TAG": "x"}', {"QUERY_TAG": "x"}),
        ("role", "SYSADMIN", "SYSADMIN"),
    ],
)
def test_coerce_param(name: str, value: Any, expected: Any) -> None:
    assert coerce_param(name, value) == expected


@pytest.mark.parametrize(
    "name,value",
    [
        ("port", "not-a-number"),
        ("client_session_keep_alive", "maybe"),
        ("session_parameters", "not json"),
        ("session_parameters", "[1, 2]"),
    ],
)
def test_coerce_param_rejects_bad_values(name: str, value: Any) -> None:
    with pytest.raises(HarlequinConfigError):
        coerce_param(name, value)


def test_coerce_param_expands_a_path() -> None:
    expanded = coerce_param("private_key_file", "~/keys/rsa.p8")
    assert expanded == str(Path.home() / "keys" / "rsa.p8")


def test_options_override_the_connection_string() -> None:
    kwargs = build_connect_kwargs(
        conn_str=("snowflake://me@acct/DB?role=DEV",),
        options={"role": "SYSADMIN", "warehouse": "WH"},
    )
    assert kwargs["role"] == "SYSADMIN"
    assert kwargs["warehouse"] == "WH"
    assert kwargs["database"] == "DB"


def test_unset_options_are_left_out() -> None:
    """The connector's own defaults and connections.toml both have to survive."""
    kwargs = build_connect_kwargs(
        conn_str=("snowflake://acct",),
        options={"role": None, "warehouse": "", "user": "me"},
    )
    assert "role" not in kwargs
    assert "warehouse" not in kwargs
    assert kwargs["user"] == "me"


def test_a_private_key_file_implies_key_pair_auth() -> None:
    kwargs = build_connect_kwargs(
        conn_str=("snowflake://me@acct",),
        options={"private_key_file": "/keys/rsa.p8", "authenticator": "snowflake"},
    )
    assert kwargs["authenticator"] == "SNOWFLAKE_JWT"


def test_an_explicit_authenticator_wins_over_the_key_file() -> None:
    kwargs = build_connect_kwargs(
        conn_str=("snowflake://me@acct",),
        options={
            "private_key_file": "/keys/rsa.p8",
            "authenticator": "externalbrowser",
        },
    )
    assert kwargs["authenticator"] == "externalbrowser"


def test_query_tag_becomes_a_session_parameter() -> None:
    kwargs = build_connect_kwargs(
        conn_str=("snowflake://acct",), options={"query_tag": "harlequin"}
    )
    assert kwargs["session_parameters"] == {"QUERY_TAG": "harlequin"}


def test_query_tag_does_not_clobber_session_parameters() -> None:
    kwargs = build_connect_kwargs(
        conn_str=("snowflake://acct",),
        options={
            "query_tag": "harlequin",
            "session_parameters": '{"QUERY_TAG": "mine", "TIMEZONE": "UTC"}',
        },
    )
    assert kwargs["session_parameters"] == {"QUERY_TAG": "mine", "TIMEZONE": "UTC"}


def test_connection_name_passes_through() -> None:
    kwargs = build_connect_kwargs(conn_str=("my_conn",), options={})
    assert kwargs["connection_name"] == "my_conn"


def test_conflicting_connection_names_raise() -> None:
    with pytest.raises(HarlequinConfigError):
        build_connect_kwargs(
            conn_str=("from_conn_str",), options={"connection_name": "from_option"}
        )


def test_matching_connection_names_do_not_raise() -> None:
    kwargs = build_connect_kwargs(
        conn_str=("same",), options={"connection_name": "same"}
    )
    assert kwargs["connection_name"] == "same"


def test_exact_decimals_are_the_default() -> None:
    """Snowflake's own default renders NUMBER as float64 and rounds it."""
    kwargs = build_connect_kwargs(conn_str=("snowflake://acct",), options={})
    assert kwargs["arrow_number_to_decimal"] is True


@pytest.mark.parametrize("value,expected", [("false", False), ("true", True)])
def test_exact_decimals_can_be_turned_off(value: str, expected: bool) -> None:
    from_option = build_connect_kwargs(
        conn_str=("snowflake://acct",), options={"arrow_number_to_decimal": value}
    )
    from_url = build_connect_kwargs(
        conn_str=(f"snowflake://acct?arrow_number_to_decimal={value}",), options={}
    )
    assert from_option["arrow_number_to_decimal"] is expected
    assert from_url["arrow_number_to_decimal"] is expected


def test_an_identified_account_does_not_fall_back_to_a_default_connection() -> None:
    kwargs = build_connect_kwargs(
        conn_str=(), options={"account": "acct", "user": "me"}
    )
    assert "connection_name" not in kwargs
