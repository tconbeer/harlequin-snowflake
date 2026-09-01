# harlequin-snowflake

A [Harlequin](https://harlequin.sh) adapter for [Snowflake](https://www.snowflake.com/),
built on the official
[snowflake-connector-python](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector)
driver.

Everything the connector can do, this adapter can do: every authenticator,
`connections.toml`, session parameters, proxies, and Arrow result sets.

## Installation

`harlequin-snowflake` is a Harlequin plug-in, so it has to live in the same
environment as Harlequin itself. With `uv`:

```bash
uv tool install --with harlequin-snowflake harlequin
```

Into an existing Harlequin install:

```bash
uv tool install --upgrade --with harlequin-snowflake harlequin
```

Or with pip, into whatever environment Harlequin is in:

```bash
pip install harlequin-snowflake
```

Harlequin finds the adapter through its `harlequin.adapter` entry point; there
is nothing else to configure.

## Usage

```bash
harlequin -a snowflake <connection>
```

### Connecting

There are three ways to say which account to connect to, and they can be mixed;
an option always overrides what the connection string said.

**A `connections.toml` entry, by name.** This is the recommended way, and the
same file the Snowflake CLI and every other Snowflake tool reads. Put this in
`~/.snowflake/connections.toml`:

```toml
[my_account]
account = "myorg-myaccount"
user = "me@example.com"
authenticator = "externalbrowser"
warehouse = "COMPUTE_WH"
role = "ANALYST"
database = "ANALYTICS"
schema = "PUBLIC"
```

then:

```bash
harlequin -a snowflake my_account
```

A connection string with no `://` in it names an entry this way. `--connection-name`
does the same thing, and `--connections-file-path` points at a file somewhere
other than `~/.snowflake/connections.toml`.

**Nothing at all.** With no connection string and no account options, the
adapter uses the connector's own default connection — the entry named by
`default_connection_name` in `config.toml`, or by the
`SNOWFLAKE_DEFAULT_CONNECTION_NAME` environment variable:

```bash
harlequin -a snowflake
```

**A connection string.** Spelled the way `snowflake-sqlalchemy` spells one:

```bash
harlequin -a snowflake "snowflake://me:my-password@myorg-myaccount/ANALYTICS/PUBLIC?warehouse=COMPUTE_WH&role=ANALYST"
```

The path is `/database/schema`, and any connector parameter can go in the query
string.

**Options.** Every connection parameter is also a CLI option, which Harlequin
will also read from `HARLEQUIN_*` environment variables:

```bash
harlequin -a snowflake --account myorg-myaccount --user me --warehouse COMPUTE_WH
```

Run `harlequin --help` for the full list.

**A Harlequin profile.** Anything you would pass on the command line can live in
a profile instead, in `~/.config/harlequin/config.toml` or in a `.harlequin.toml`
beside the project you are working in. With a `default_profile`, `harlequin` on
its own is the whole command:

```toml
default_profile = "dev"

[profiles.dev]
adapter = "snowflake"
theme = "harlequin"
keymap_name = ["vscode"]
viewer_max_rows = 100_000

account = "myorg-myaccount"
user = "me@example.com"
role = "ANALYST"
warehouse = "COMPUTE_WH"
database = "ANALYTICS"
schema = "PUBLIC"

# key-pair auth; --private-key-file selects it on its own
private_key_file = "~/.snowflake/rsa_key.p8"
private_key_file_pwd = "..."

[profiles.sso]
adapter = "snowflake"
account = "myorg-myaccount"
user = "me@example.com"
authenticator = "externalbrowser"
client_store_temporary_credential = true
warehouse = "COMPUTE_WH"
```

```bash
harlequin              # the default profile
harlequin -P sso       # a named one
```


### Authentication

Set `--authenticator` (or `authenticator` in `connections.toml`) to any of the
connector's values:

| Authenticator | What it needs |
| --- | --- |
| `snowflake` (default) | `--user` and `--password` |
| `externalbrowser` | `--user`; opens a browser for SSO. Add `--client-store-temporary-credential` so it does not open one every time. |
| `snowflake_jwt` (key pair) | `--user` and `--private-key-file` (plus `--private-key-file-pwd` if the key is encrypted). Passing `--private-key-file` selects this authenticator on its own. |
| `oauth` | `--token`, or `--token-file-path` |
| `oauth_authorization_code` | `--oauth-client-id`, `--oauth-client-secret`, and optionally the URL options |
| `oauth_client_credentials` | `--oauth-client-id`, `--oauth-client-secret`, `--oauth-token-request-url` |
| `programmatic_access_token` | `--user` and the PAT in `--token` |
| `username_password_mfa` | `--user`, `--password`, and `--passcode` (or `--passcode-in-password`). Add `--client-request-mfa-token` to cache the token. |
| `workload_identity` | `--workload-identity-provider` (`AWS`, `AZURE`, `GCP`, or `OIDC`) |
| `https://myorg.okta.com` | `--user` and `--password`, for native Okta |

Secrets — `--password`, `--token`, `--passcode`, `--private-key-file-pwd`,
`--oauth-client-secret`, `--proxy-password` — are marked secret, so Harlequin
never prints them back.

### Read-only

Snowflake has no server-enforced read-only session or transaction, so this
adapter does not offer `--read-only`: it would be a promise it could not keep.
Connect with a role that has only the privileges you want instead.

## Interactions

Right-click (or press `.`) on a catalog item:

- **Database** — Use Database, List Objects, Show DDL, Show Grants, Drop Database
- **Schema** — Use Schema, List Objects, Show DDL, Show Grants, Drop Schema
- **Relation** — Insert Columns at Cursor, Preview Data, Describe Relation, Show
  Grants, plus per-kind items: Sample Data, Count Rows, Show DDL, Show View
  Definition, Show Refresh History (dynamic tables), and the matching Drop
- **Column** — Show Value Counts

## Development

```bash
make init          # uv sync
make check         # format, lint, type check, test
make test          # unit tests only
make serve         # run Harlequin on the default profile
```

The unit tests need no database. The integration tests run against a real
account and are strictly read-only — they introspect what is already there and
never create, alter, or drop anything.

They take their connection from a `snowflake` profile in `.harlequin.toml` in
the repo root — the same file `make serve` uses — or, failing that, from the
`connections.toml` entry named by `HARLEQUIN_SNOWFLAKE_TEST_CONNECTION`. With
neither, they skip.

```bash
make integration
```

## License

MIT
