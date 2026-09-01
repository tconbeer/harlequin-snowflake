# harlequin-snowflake

A [Harlequin](https://harlequin.sh) adapter for [Snowflake](https://www.snowflake.com/),
built on the official
[snowflake-connector-python](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector)
driver.

Everything the connector can do, this adapter can do: every authenticator,
`connections.toml`, session parameters, proxies, and Arrow result sets.

## Installation

`harlequin-snowflake` is a Harlequin plug-in. Install it into the same
environment as Harlequin — the simplest way is with `uv`:

```bash
uv tool install 'harlequin[snowflake]'
```

or, into an existing Harlequin installation:

```bash
uv tool install --with harlequin-snowflake harlequin
```

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
will also read from a profile in `~/.config/harlequin/config.toml` or from
`HARLEQUIN_*` environment variables:

```bash
harlequin -a snowflake --account myorg-myaccount --user me --warehouse COMPUTE_WH
```

Run `harlequin --help` for the full list.

### Authentication

Set `--authenticator` (or `authenticator` in `connections.toml`) to any of the
connector's values:

| Authenticator | What it needs |
| --- | --- |
| `snowflake` (default) | `--user` and `--password` |
| `externalbrowser` | `--user`; opens a browser for SSO. Add `--client-store-temporary-credential` so it does not open one every time. |
| `snowflake_jwt` | `--user` and `--private-key-file` (plus `--private-key-file-pwd` if the key is encrypted). Passing `--private-key-file` selects this authenticator on its own. |
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

## What the adapter does

### Data catalog

The catalog lazy-loads a level at a time, so connecting to an account with
thousands of objects is fast: databases first, then a database's schemas when
you expand it, then a schema's relations, then a relation's columns. Tables,
views, materialized views, dynamic tables, Iceberg tables, external tables,
event tables, and hybrid tables are each shown with their own type label and
context menu.

### Catalog search

`IMPLEMENTS_CATALOG_SEARCH` is on: searching finds databases, schemas,
relations, and columns across the whole account without walking the tree, using
`SHOW ... LIKE ... IN ACCOUNT`. Because `SHOW` has no `ESCAPE` clause, a `%` or
`_` you type is sent as a single-character wildcard and the exact matches are
kept — so a term with an underscore in it still means the underscore.

### Interactions

Right-click (or press `.`) on a catalog item:

- **Database** — Use Database, List Objects, Show DDL, Show Grants, Drop Database
- **Schema** — Use Schema, List Objects, Show DDL, Show Grants, Drop Schema
- **Relation** — Insert Columns at Cursor, Preview Data, Describe Relation, Show
  Grants, plus per-kind items: Sample Data, Count Rows, Show DDL, Show View
  Definition, Show Refresh History (dynamic tables), and the matching Drop
- **Column** — Show Value Counts

### Cancel

`IMPLEMENTS_CANCEL` is on. Pressing `ctrl+c` aborts the running statement by the
request ID the connector assigned it — the same mechanism the connector's own
query timeout uses, which means it works while the query is still in flight
rather than only after it returns.

### Transactions

Toggle between `Auto` (autocommit) and `Manual`. In `Manual`, Harlequin shows
commit and rollback buttons.

### Autocompletion

Snowflake's keywords ship with the adapter; functions, procedures, and session
parameters are read from the account itself with `SHOW FUNCTIONS`,
`SHOW PROCEDURES`, and `SHOW PARAMETERS`, so account-defined UDFs are completed
too. A role that cannot list them still gets keywords and catalog completions.

### Results

Result sets are fetched as Arrow tables when Snowflake returns Arrow, which is
most of the time, so types survive the trip and no conversion through Python
objects is needed. `SHOW` and `DESCRIBE` results, which Snowflake returns as
JSON, fall back to rows.

## Development

```bash
make init          # uv sync
make check         # format, lint, type check, test
make test          # unit tests only
make serve         # run Harlequin against CONNECTION
```

The unit tests need no database. The integration tests run against a real
account and are strictly read-only — they introspect what is already there and
never create, alter, or drop anything. Point them at a `connections.toml` entry:

```bash
export HARLEQUIN_SNOWFLAKE_TEST_CONNECTION=my_account
make integration
```

Without that variable, the integration tests skip.

## License

MIT
