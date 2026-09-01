"""Turns what the user typed into keyword arguments for `snowflake.connector`.

Harlequin hands an adapter a connection string and a flat dict of options; the
connector takes one dict of connection parameters, and also knows how to read
a `connections.toml` entry on its own. This module is the seam between the two,
so that `adapter.py` only ever sees a finished dict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import parse_qsl, unquote, urlsplit

from harlequin.exception import HarlequinConfigError, HarlequinConnectionError

_INT_PARAMS = frozenset(
    {
        "port",
        "login_timeout",
        "network_timeout",
        "socket_timeout",
        "external_browser_timeout",
        "client_prefetch_threads",
        "master_validity_in_seconds",
        "client_session_keep_alive_heartbeat_frequency",
    }
)
"""Connector parameters that must be an int, not the string a CLI hands over."""

_BOOL_PARAMS = frozenset(
    {
        "passcode_in_password",
        "client_session_keep_alive",
        "client_store_temporary_credential",
        "client_request_mfa_token",
        "disable_ocsp_checks",
        "autocommit",
        "validate_default_parameters",
        "oauth_disable_pkce",
        "oauth_enable_refresh_tokens",
        "oauth_enable_single_use_refresh_tokens",
    }
)

_PATH_PARAMS = frozenset({"private_key_file", "token_file_path"})
"""Parameters the connector wants as a string path, tilde already expanded."""

_TRUE = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSE = frozenset({"0", "false", "f", "no", "n", "off"})

_IDENTIFYING_PARAMS = ("account", "host", "user", "private_key_file", "token")
"""Params whose presence means the user named a connection themselves.

If none of them is set and no connection name was given, the connector's own
default connection is what the user meant, the same as a bare `snowflake.connector
.connect()`.
"""


def _to_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise HarlequinConfigError(
        msg=f"Cannot interpret {value!r} as a true/false value.",
        title=f"Harlequin received an invalid value for {name}.",
    )


def _to_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise HarlequinConfigError(
            msg=f"Cannot interpret {value!r} as a number.",
            title=f"Harlequin received an invalid value for {name}.",
        )
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise HarlequinConfigError(
            msg=f"Cannot interpret {value!r} as a number.",
            title=f"Harlequin received an invalid value for {name}.",
        ) from e


def _to_session_parameters(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as e:
        raise HarlequinConfigError(
            msg=f"Cannot parse {value!r} as JSON.",
            title="Harlequin received an invalid value for session_parameters.",
        ) from e
    if not isinstance(parsed, dict):
        raise HarlequinConfigError(
            msg=(
                "session_parameters must be a JSON object, not "
                f"{type(parsed).__name__}."
            ),
            title="Harlequin received an invalid value for session_parameters.",
        )
    return parsed


def coerce_param(name: str, value: Any) -> Any:
    """One option, as the type the connector expects for it.

    Options can arrive as strings from the command line, as typed values from a
    config file, and as either from a URL's query string, so every path through
    this module funnels through here.
    """
    if name in _BOOL_PARAMS:
        return _to_bool(name, value)
    if name in _INT_PARAMS:
        return _to_int(name, value)
    if name == "session_parameters":
        return _to_session_parameters(value)
    if name in _PATH_PARAMS:
        return str(Path(str(value)).expanduser())
    return value


def parse_conn_str(conn_str: Sequence[str]) -> tuple[str | None, dict[str, Any]]:
    """Splits the connection string into a connection name and connector params.

    A string with a scheme is a URL, spelled the way snowflake-sqlalchemy spells
    one: `snowflake://user:password@account/database/schema?warehouse=wh&role=r`.
    Anything else names an entry in connections.toml, so that
    `harlequin -a snowflake my_dev_account` is all a configured user has to type.

    Returns: (connection_name, params), either of which may be empty.
    """
    if len(conn_str) > 1:
        raise HarlequinConnectionError(
            msg=(
                "Cannot provide multiple connection strings to the Snowflake "
                f"adapter. Received {list(conn_str)}."
            ),
            title="Harlequin could not connect to Snowflake.",
        )
    raw = conn_str[0].strip() if conn_str and conn_str[0] else ""
    if not raw:
        return None, {}
    if "://" not in raw:
        return raw, {}

    parts = urlsplit(raw)
    if parts.scheme not in ("snowflake", "snowflake+connector"):
        raise HarlequinConnectionError(
            msg=(
                f"Unrecognized scheme {parts.scheme!r} in the connection string. "
                "Use snowflake://user:password@account/database/schema, or the "
                "name of a connections.toml entry."
            ),
            title="Harlequin could not connect to Snowflake.",
        )

    params: dict[str, Any] = {}
    # `hostname` lower-cases what it returns, which is right for an account
    # identifier -- Snowflake matches them case-insensitively -- and wrong for a
    # user, so the user comes from the raw netloc instead.
    if parts.hostname:
        params["account"] = parts.hostname
    if parts.username:
        params["user"] = unquote(parts.username)
    if parts.password:
        params["password"] = unquote(parts.password)
    if parts.port:
        params["port"] = parts.port

    path_parts = [unquote(p) for p in parts.path.split("/") if p]
    if len(path_parts) > 2:
        raise HarlequinConnectionError(
            msg=(
                f"Could not read {parts.path!r} as a database and schema. The path "
                "of a Snowflake connection string is /database/schema."
            ),
            title="Harlequin could not connect to Snowflake.",
        )
    for key, value in zip(("database", "schema"), path_parts, strict=False):
        params[key] = value

    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        params[key.strip().lower()] = coerce_param(key.strip().lower(), value)

    return None, params


def _default_connection_name(connections_file_path: Path | None) -> str | None:
    """The connection the connector would pick on its own, if it can pick one.

    Read here rather than left to the connector because Harlequin always has at
    least one parameter of its own to pass (the application name), and the
    connector only consults its default connection when it is passed nothing.
    """
    try:
        from snowflake.connector.config_manager import CONFIG_MANAGER

        if connections_file_path is not None:
            for i, slice_ in enumerate(CONFIG_MANAGER._slices):
                if slice_.section == "connections":
                    CONFIG_MANAGER._slices[i] = slice_._replace(
                        path=connections_file_path
                    )
                    CONFIG_MANAGER.read_config()
                    break
        name = CONFIG_MANAGER["default_connection_name"]
        connections = CONFIG_MANAGER["connections"]
    except Exception:
        # No connections.toml, an unreadable one, or a connector that spells any
        # of this differently: there is no default connection to fall back to,
        # which is not an error until the connection itself fails.
        return None
    if isinstance(name, str) and isinstance(connections, dict) and name in connections:
        return name
    return None


def build_connect_kwargs(
    conn_str: Sequence[str], options: dict[str, Any]
) -> dict[str, Any]:
    """Every argument `snowflake.connector.connect()` should be called with.

    Precedence, lowest first: the connections.toml entry (which the connector
    itself merges in), then the connection string, then the options Harlequin
    collected from the command line, config file, or env variables. An option
    that was not set is left out entirely, so the connector's own default and
    the connections.toml entry both survive.
    """
    connection_name, kwargs = parse_conn_str(conn_str)

    query_tag = options.pop("query_tag", None)
    named_connection = options.pop("connection_name", None)
    connections_file = options.pop("connections_file_path", None)

    for key, value in options.items():
        if value is None or value == "":
            continue
        kwargs[key] = coerce_param(key, value)

    if named_connection:
        if connection_name and connection_name != named_connection:
            raise HarlequinConfigError(
                msg=(
                    f"The connection string names connection {connection_name!r} "
                    f"and --connection-name names {named_connection!r}. Pass one "
                    "or the other."
                ),
                title="Harlequin received conflicting Snowflake options.",
            )
        connection_name = str(named_connection)

    if query_tag:
        session_parameters = dict(kwargs.get("session_parameters") or {})
        session_parameters.setdefault("QUERY_TAG", query_tag)
        kwargs["session_parameters"] = session_parameters

    # A private key file is only ever used for key-pair auth, so supplying one
    # is enough to say which authenticator was meant. `authenticator` has a
    # default, so it arrives set even when the user never mentioned it.
    if kwargs.get("private_key_file") and (
        str(kwargs.get("authenticator", "snowflake")).casefold() == "snowflake"
    ):
        kwargs["authenticator"] = "SNOWFLAKE_JWT"

    connections_file_path = (
        Path(str(connections_file)).expanduser() if connections_file else None
    )
    if connection_name is None and not any(
        kwargs.get(param) for param in _IDENTIFYING_PARAMS
    ):
        connection_name = _default_connection_name(connections_file_path)

    if connection_name is not None:
        kwargs["connection_name"] = connection_name
    if connections_file_path is not None:
        kwargs["connections_file_path"] = connections_file_path

    return kwargs
