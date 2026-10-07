# ADR-0011 · HyperDX as a second read-layer UI, wired directly to ClickHouse

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 2026-10-07 |
| Owners | Pod 3 |
| Proposer | Sentinel team |
| Supersedes | — |
| Related | ADR-0007 · ADR-0010 · `docs/ci-gates.md` · DEC-2026-10-06 (local scope) · DEC-I2 |

## Context

flow-ui shows the pipeline watching itself: four fixed boards over the collector's `/metrics` and read-only views of `bronze.*` and `silver.*`. It is not a place to search logs, follow a trace, or build an ad-hoc chart over the telemetry itself. HyperDX (ClickStack's UI) is that tool, and it already speaks the otel-collector-contrib ClickHouse schema that bronze is defined as (ADR-0007).

The constraint is that this stack has one ClickHouse and one ingestion path. HyperDX is distributed in four shapes, and only one fits:

| Variant | Bundles | Fit |
|---|---|---|
| `clickhouse/clickstack-all-in-one`, `hyperdx/hyperdx-all-in-one` | ClickHouse, Mongo, OTel collector, UI/API | **No.** A second ClickHouse (already forbidden by invariant 01, which names this image) and a second ingestion path |
| `clickhouse/clickstack-local`, `hyperdx/hyperdx-local` | ClickHouse, collector, UI, no auth, browser-local state | **No.** Same bundled ClickHouse and collector |
| `hyperdx/hyperdx` (UI + API only) | nothing; needs `MONGO_URI` and an external ClickHouse | **Yes** |
| `clickstack-otel-collector` | the ingest collector | **No.** collector-rust is the only ingestion path |

## Decision

Run `hyperdx/hyperdx:2.40.0` (UI + API) and `mongo:5.0.32-focal` (the version HyperDX's own Compose file pins) in the root `docker-compose.yml`, beside flow-ui, and point HyperDX at the existing `clickhouse` service over HTTP `:8123`. No HyperDX collector runs; nothing is written to ClickHouse by HyperDX.

- **Mongo is required, and is metadata only.** The UI/API image keeps users, saved searches, dashboards and alerts there. A variant without Mongo exists only as the bundled local image, which is excluded above. Mongo has no host port and lives on the private Compose network, in the named volume `hyperdx_mongo_data`.
- **A dedicated read-only user.** Migration `0007_hyperdx_role.sql` creates role `sentinel_hyperdx` with `SELECT` on `bronze.*`, `silver.*`, `system.tables` and `system.columns`, and user `sentinel_hyperdx_u` with `SETTINGS readonly = 2`. `readonly = 2` still refuses every write and DDL statement but lets HyperDX attach its per-query settings, which `readonly = 1` rejects. It follows the 0002 pattern: `sha256_password`, password as `{pw:String}` from the same mounted secret file.
- **The password stays a file path.** HyperDX only bootstraps its first connection from a `DEFAULT_CONNECTIONS` env var whose JSON carries the password inline. `infra/hyperdx/entrypoint.sh` builds that value at container start from `CLICKHOUSE_PASSWORD_FILE` and then hands off to the image's own `/etc/local/entry.sh`, so the secret is not in the Compose file or in `docker inspect`. Invariant 10 asserts the Compose file never carries it.
- **Sources are versioned files.** `infra/hyperdx/sources.json` maps Logs, Traces and Metrics onto `bronze.otel_logs`, `bronze.otel_traces` and the gauge/sum/histogram tables. Logs use `TimestampTime` as the query timestamp (it is in the table's sort key and partition-friendly) and `Timestamp` for display.
- **Port.** Host `127.0.0.1:8081` (override `HYPERDX_HOST_PORT`), container `8080`. 8080 is flow-ui's, and invariant 03 forbids a duplicate. The API's own port `8000` is not published: the browser reaches it through the app's proxy.
- **Independent, like flow-ui.** `make hyperdx` starts ClickHouse, migrates, then starts HyperDX; `make down-hyperdx` stops it. Nothing in the pipeline depends on it, and it does not need the collector.

## Options considered

1. **UI/API image + Mongo, direct to ClickHouse (chosen).**
2. **All-in-one or local image, with its ClickHouse ignored or pointed away.** The image still starts its own ClickHouse and collector and still publishes `4317`, colliding with ours. Rejected.
3. **Run HyperDX's collector and have collector-rust (or the generator) export to it.** A second ingestion path and a second schema (`default.*` in HyperDX's own DDL) alongside bronze. Rejected by the requirement to read bronze directly.
4. **Reuse `sentinel_reader_u`.** Fewer objects, but HyperDX queries are then indistinguishable from flow-ui's in `system.query_log`, and a grant either UI needs widens both. Rejected.
5. **Wait for env-var-free source provisioning.** No file or API provisions sources without a registered user; `DEFAULT_SOURCES` is the supported bootstrap. Taken as is.

## Trade-offs

- A second metadata store (Mongo) to run, for a feature the pipeline does not depend on.
- `DEFAULT_CONNECTIONS` and `DEFAULT_SOURCES` apply only to an **empty** Mongo, at the moment the first account is created. After editing `sources.json`, `make reset-hyperdx` drops the volume, along with accounts and saved views. Live edits made in the UI are not written back to the file.
- HyperDX keeps the ClickHouse password in its Mongo connection record. The password never leaves the machine, but the "file path only" rule holds for the Compose and image layers, not for HyperDX's own database.
- Authentication is HyperDX's own local account. There is no TLS (DEC-A4) and the port is loopback-only.
- The password file is shared with the other three ClickHouse users (existing 0002 pattern). Per-user secrets would need a per-user prelude in `migrate.sh`.

## Consequences

- `docker-compose.yml` gains `hyperdx` and `hyperdx-mongo`; `Makefile` gains `hyperdx`, `down-hyperdx`, `reset-hyperdx`, `test-hyperdx`; `make test` includes `test-hyperdx`.
- `infra/hyperdx/tests/test_sources.py` treats the bronze DDL as the oracle for every column in `sources.json`, so a DDL rename fails a test rather than an empty UI page.
- Invariant `10-hyperdx-is-read-only` joins the harness.
- No change to bronze, silver, the collector, or the contracts.
- Histogram metrics are mapped because the table exists, but there is still no v1.0.0 contract type for them (see README *Open*); the exponential-histogram and summary tables are not mapped.

## Risks

- **Image drift.** The tag is pinned (`2.40.0`); the `DEFAULT_*` bootstrap is HyperDX's, not a stable contract. A bump needs a re-check of source field names, and `make test-hyperdx` will not catch HyperDX renaming one.
- **Large silver reads.** HyperDX can issue arbitrary `SELECT`s as `sentinel_hyperdx_u`. No quota or `max_execution_time` is set; local scope only.
- **Unverified in CI.** GitHub Actions has not run since 2026-10-05. The `test-hyperdx` target is not yet in a workflow.

## Verification (2026-10-07, local, Docker Desktop, ClickHouse 25.4.13.22)

On a clean project: `make hyperdx` migrated (`0007` applied), HyperDX reached healthy, registering the first account created the connection and the three sources from the files, and through HyperDX's own `/api/clickhouse-proxy` the session ran as `sentinel_hyperdx_u`, listed the bronze tables, read an `otel_logs` row and `silver.volume_1m`, and was refused `INSERT`, `CREATE TABLE` and `SELECT` from `system.users` with `ACCESS_DENIED`. Not exercised: the browser UI itself (Search/Trace pages) and any data volume beyond one row.

## Next steps

- Pod 3 sign-off on a second reader of silver.
- Add `test-hyperdx` to a path-filtered workflow once Actions runs again.
- Decide whether `sentinel_hyperdx_u` wants a quota profile before any non-local use.

## References

- HyperDX compose and config (`DEFAULT_CONNECTIONS`, `DEFAULT_SOURCES`, `MONGO_URI`): https://github.com/hyperdxio/hyperdx (`docker-compose.yml`, `packages/api/src/config.ts`, release 2.40.0)
- ClickStack HyperDX-only deployment: https://clickhouse.com/docs/use-cases/observability/clickstack/deployment/hyperdx-only
- `infra/clickhouse/migrations/0002_roles.sql`, `0007_hyperdx_role.sql` · `infra/hyperdx/` · `scripts/ci/invariants.d/10-hyperdx-is-read-only.sh`
