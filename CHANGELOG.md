# harlequin-snowflake CHANGELOG

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.1.0] - 2026-09-01

- Initial release. Adds a Snowflake adapter for Harlequin, built on the official
  `snowflake-connector-python` driver.
- Supports every authenticator the connector supports, including password,
  `externalbrowser` SSO, key-pair (`snowflake_jwt`), OAuth (authorization code
  and client credentials), programmatic access tokens, MFA, workload identity,
  and native Okta.
- Reads `connections.toml`: a bare connection string names an entry, and the
  connector's default connection is used when nothing else is given.
- Lazy, interactive data catalog for databases, schemas, tables, views,
  materialized views, dynamic tables, Iceberg tables, external tables, event
  tables, and columns, each with a context menu.
- Catalog search across the whole account, for relations, columns, or every
  level.
- Query cancellation, transaction modes, and autocompletion sourced from the
  account's own functions, procedures, and session parameters.
- Fetches result sets as Arrow tables, matching Harlequin's Arrow-backed data
  table. Depends on `snowflake-connector-python[pandas]`, since the connector's
  Arrow support is gated behind that extra; falls back to reading rows for the
  statements Snowflake answers in JSON.
- Defaults `arrow_number_to_decimal` to true, unlike the connector, so `NUMBER`
  columns are not rounded to floats.
