from __future__ import annotations

from harlequin.options import (
    FlagOption,
    PathOption,
    SelectOption,
    TextOption,
)

account = TextOption(
    name="account",
    description=(
        "Your Snowflake account identifier, e.g., myorg-myaccount, or the legacy "
        "form xy12345.us-east-1. Required unless it is supplied by the connection "
        "string or by the connections.toml entry this connects with."
    ),
    # -a is Harlequin's own --adapter, so this option only aliases the long form.
    short_decls=["--accountname"],
)

user = TextOption(
    name="user",
    description="The login name of the Snowflake user to connect as.",
    # -u is DuckDB's --allow-unsigned-extensions, which is attached to the
    # same command whenever both adapters are installed.
    short_decls=["-U", "--username"],
)

password = TextOption(
    name="password",
    description=(
        "The password for the Snowflake user. Ignored by authenticators that do "
        "not use one, like externalbrowser or snowflake_jwt."
    ),
    secret=True,
)

role = TextOption(
    name="role",
    description=(
        "The role to activate for the session. Defaults to the user's default role."
    ),
    # -r is Harlequin's own --read-only.
    short_decls=["--rolename"],
)

warehouse = TextOption(
    name="warehouse",
    description=(
        "The virtual warehouse to use for the session. Queries cannot run without "
        "one, so set this unless the user has a default warehouse."
    ),
    short_decls=["-w"],
)

database = TextOption(
    name="database",
    description=(
        "The database to set as the session context. The Data Catalog shows every "
        "database the role can see, so this only decides how unqualified names "
        "resolve."
    ),
    short_decls=["-d", "--dbname"],
)

schema = TextOption(
    name="schema",
    description=(
        "The schema to set as the session context, resolved inside --database."
    ),
    short_decls=["-s", "--schemaname"],
)

# Snowflake spells its authenticators in lower case in connections.toml and in
# upper case in its docs; the connector accepts either, and so does this option,
# since the choices are only a hint to the GUI and the CLI.
authenticator = TextOption(
    name="authenticator",
    description=(
        "How to authenticate. One of: snowflake (user + password), "
        "externalbrowser (browser-based SSO), snowflake_jwt (key pair; see "
        "--private-key-file), oauth (see --token), oauth_authorization_code, "
        "oauth_client_credentials, username_password_mfa (see --passcode), "
        "programmatic_access_token (a PAT in --token or --password), "
        "workload_identity (see --workload-identity-provider), or the URL of an "
        "Okta endpoint, e.g. https://myorg.okta.com."
    ),
    default="snowflake",
)

private_key_file = PathOption(
    name="private_key_file",
    description=(
        "Path to a PEM-encoded private key for key-pair authentication. Implies "
        "--authenticator snowflake_jwt unless another authenticator is set."
    ),
    resolve_path=True,
    exists=False,
    file_okay=True,
    dir_okay=False,
)

private_key_file_pwd = TextOption(
    name="private_key_file_pwd",
    description="The passphrase that decrypts --private-key-file, if it is encrypted.",
    secret=True,
)

token = TextOption(
    name="token",
    description=(
        "The OAuth access token or programmatic access token (PAT) to authenticate "
        "with. Used by the oauth and programmatic_access_token authenticators."
    ),
    secret=True,
)

token_file_path = PathOption(
    name="token_file_path",
    description=(
        "Path to a file containing the OAuth token, read instead of --token. Useful "
        "for the token a Snowpark Container Services workload is given."
    ),
    resolve_path=True,
    exists=False,
    file_okay=True,
    dir_okay=False,
)

passcode = TextOption(
    name="passcode",
    description="The Duo MFA passcode, for the username_password_mfa authenticator.",
    secret=True,
)

passcode_in_password = FlagOption(
    name="passcode_in_password",
    description=(
        "Set if the MFA passcode is appended to the password instead of passed "
        "as --passcode."
    ),
)

oauth_client_id = TextOption(
    name="oauth_client_id",
    description=(
        "The client ID registered with the OAuth provider, for the "
        "oauth_authorization_code and oauth_client_credentials authenticators."
    ),
)

oauth_client_secret = TextOption(
    name="oauth_client_secret",
    description="The client secret that pairs with --oauth-client-id.",
    secret=True,
)

oauth_authorization_url = TextOption(
    name="oauth_authorization_url",
    description=(
        "The OAuth provider's authorization endpoint. Defaults to Snowflake's own, "
        "https://{host}:{port}/oauth/authorize."
    ),
)

oauth_token_request_url = TextOption(
    name="oauth_token_request_url",
    description=(
        "The OAuth provider's token endpoint. Defaults to Snowflake's own, "
        "https://{host}:{port}/oauth/token-request."
    ),
)

oauth_redirect_uri = TextOption(
    name="oauth_redirect_uri",
    description=(
        "The redirect URI the OAuth provider sends the authorization code back to. "
        "Defaults to http://127.0.0.1."
    ),
)

oauth_scope = TextOption(
    name="oauth_scope",
    description=(
        "The scope requested from the OAuth provider. Defaults to the scope implied "
        "by the session's role."
    ),
)

workload_identity_provider = SelectOption(
    name="workload_identity_provider",
    description=(
        "Which cloud's workload identity to attest with, for the workload_identity "
        "authenticator."
    ),
    choices=["AWS", "AZURE", "GCP", "OIDC"],
)

workload_identity_entra_resource = TextOption(
    name="workload_identity_entra_resource",
    description=(
        "The Entra ID resource the Azure workload identity token is requested for."
    ),
)

connection_name = TextOption(
    name="connection_name",
    description=(
        "The name of a connection defined in connections.toml. Every value in that "
        "entry is used, and any option passed here overrides it. A bare connection "
        "string (one with no '://') names a connection the same way."
    ),
    short_decls=["-c"],
)

connections_file_path = PathOption(
    name="connections_file_path",
    description=(
        "Path to the connections.toml to read --connection-name from. Defaults to "
        "the connector's own location, ~/.snowflake/connections.toml."
    ),
    resolve_path=True,
    exists=False,
    file_okay=True,
    dir_okay=False,
)

host = TextOption(
    name="host",
    description=(
        "The Snowflake host to connect to. Derived from --account when not set; "
        "set it for PrivateLink or a non-standard deployment."
    ),
    short_decls=["-h"],
)

port = TextOption(
    name="port",
    description="The port to connect to on --host. Defaults to 443.",
    short_decls=["-p"],
)

protocol = SelectOption(
    name="protocol",
    description=(
        "The protocol to connect with. Only change this for a local test deployment."
    ),
    choices=["https", "http"],
    default="https",
)

region = TextOption(
    name="region",
    description=(
        "DEPRECATED by Snowflake. The region of a legacy account identifier; "
        "prefer spelling the region in --account."
    ),
)

login_timeout = TextOption(
    name="login_timeout",
    description=(
        "How long to keep retrying the login, in seconds. Write as an integer, e.g. 60."
    ),
)

network_timeout = TextOption(
    name="network_timeout",
    description=(
        "How long to keep retrying a request other than the login, in seconds. "
        "Write as an integer. Unset means retry forever."
    ),
)

client_session_keep_alive = FlagOption(
    name="client_session_keep_alive",
    description=(
        "Keep the session alive indefinitely with a heartbeat, so a long-idle "
        "Harlequin session does not have to reauthenticate. Recommended for "
        "authenticators that prompt, like externalbrowser."
    ),
    default=True,
)

client_store_temporary_credential = FlagOption(
    name="client_store_temporary_credential",
    description=(
        "Cache the SSO token on disk so externalbrowser authentication does not "
        "open a browser on every connection."
    ),
)

client_request_mfa_token = FlagOption(
    name="client_request_mfa_token",
    description=(
        "Cache the MFA token on disk so username_password_mfa does not prompt on "
        "every connection."
    ),
)

external_browser_timeout = TextOption(
    name="external_browser_timeout",
    description=(
        "How long to wait for the browser-based SSO handshake, in seconds. Write "
        "as an integer. Defaults to 120."
    ),
)

session_parameters = TextOption(
    name="session_parameters",
    description=(
        "Session parameters to set on connect, as a JSON object, e.g. "
        '\'{"QUERY_TAG": "harlequin", "STATEMENT_TIMEOUT_IN_SECONDS": 300}\'.'
    ),
)

timezone = TextOption(
    name="timezone",
    description=(
        "The session time zone, e.g. America/New_York. Defaults to the account's."
    ),
)

application = TextOption(
    name="application",
    description=(
        "The application name reported to Snowflake, visible in QUERY_HISTORY. "
        "Defaults to Harlequin."
    ),
    default="Harlequin",
)

query_tag = TextOption(
    name="query_tag",
    description=(
        "A QUERY_TAG to set on the session, so this session's queries can be "
        "picked out of QUERY_HISTORY. Shorthand for the same key in "
        "--session-parameters."
    ),
)

proxy_host = TextOption(
    name="proxy_host",
    description="The host of an HTTP proxy to connect through.",
)

proxy_port = TextOption(
    name="proxy_port",
    description="The port of the HTTP proxy named by --proxy-host.",
)

proxy_user = TextOption(
    name="proxy_user",
    description="The user to authenticate to the HTTP proxy as.",
)

proxy_password = TextOption(
    name="proxy_password",
    description="The password for --proxy-user.",
    secret=True,
)

disable_ocsp_checks = FlagOption(
    name="disable_ocsp_checks",
    description=(
        "Skip the OCSP certificate revocation check. Weakens the connection's "
        "guarantees; set it only to work around a broken OCSP responder."
    ),
)

SNOWFLAKE_OPTIONS = [
    account,
    user,
    password,
    role,
    warehouse,
    database,
    schema,
    authenticator,
    private_key_file,
    private_key_file_pwd,
    token,
    token_file_path,
    passcode,
    passcode_in_password,
    oauth_client_id,
    oauth_client_secret,
    oauth_authorization_url,
    oauth_token_request_url,
    oauth_redirect_uri,
    oauth_scope,
    workload_identity_provider,
    workload_identity_entra_resource,
    connection_name,
    connections_file_path,
    host,
    port,
    protocol,
    region,
    login_timeout,
    network_timeout,
    client_session_keep_alive,
    client_store_temporary_credential,
    client_request_mfa_token,
    external_browser_timeout,
    session_parameters,
    timezone,
    application,
    query_tag,
    proxy_host,
    proxy_port,
    proxy_user,
    proxy_password,
    disable_ocsp_checks,
]
