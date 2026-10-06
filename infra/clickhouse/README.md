# infra/clickhouse

ClickHouse DDL and checks for the `bronze` and `silver` databases. Pod 3 owns the DDL.

| Path | Role |
|------|------|
| `init.d/01-bronze-otel.sql` | bronze DDL, auto-applied on first boot via `docker-entrypoint-initdb.d` |
| `init.d/02-silver-layer.sql` | silver DDL, same mechanism |
| `tests/02-silver-layer.test.sql` | silver assertions, run by `make test-silver` |
| `queries/02-silver-sample.sql` | sample read queries |

Gotcha: `docker-entrypoint-initdb.d` only runs against an empty data volume. After a DDL change, `make reset` before `make up`.

## Compose `include:` path resolution (`[V-4]`, probed 2026-10-05)

Question: does `include:` exist in the installed Compose, and are relative bind-mount sources resolved from the including file's directory or the included file's?

| | |
|---|---|
| Compose version tested | `v5.1.4` (`docker compose version`) |
| Version floor for `include:` | v2.20 (per spec §11 `[V-4]`; not re-verified against older releases) |
| Probe | `outer.yml` includes `inner/inner.yml`; the inner service mounts `../marker/ddl.sql` |
| Observable | `docker compose -f outer.yml config` printed `source: <scratchpad>/v4/marker/ddl.sql` |
| Base used | the **included** file's directory (`inner/` + `../marker`), not the including file's (which would give `<scratchpad>/marker`) |

Both candidate targets were created before running, so the printed path is a resolution Compose chose, not an inference from a missing file.

Variants, same probe layout:

| Form | Resolved `source:` base |
|------|-------------------------|
| `include: [inner/inner.yml]` | included file's directory |
| `include: - path: inner/inner.yml` + `project_directory: .` | including file's directory |
| `extends: {file: inner/inner.yml, service: clickhouse}` | extended file's directory |
| local service of the same name as an included one | `config` exits 0 and the two are **merged field by field**, the local value winning per field; no conflict error |

Re-verified 2026-10-05 on Compose `v5.1.4`, both rows: a decoy `inner/marker/ddl.sql` existed beside `marker/ddl.sql` and `config` printed the latter. In the same-name variant the local `image: …:24.3` replaced the included `…:25.4` while the included `volumes:` survived — so the override is a per-field merge, not a wholesale replacement. That is the sharper form of the REQ-I-07 hazard: a consumer that re-states `image:` keeps the shared mounts and silently runs a different ClickHouse version, which a source-file grep for a single `image:` pin cannot see.

What this means for the single ClickHouse definition:

- The premise in REQ-I-08 that `include:` shifts the base to the including file is false on v5.1.4. Relative paths in the shared file resolve from the shared file, so every consumer gets the same absolute DDL path. Put the shared definition in `infra/clickhouse/` and write its mounts relative to itself (for example `./init.d/...`).
- T12 should use `include:`. `extends:` offers no advantage here: it rebases the same way.
- `services/collector-rust/infra/docker-compose.yml:34` (`../../../infra/clickhouse/init.d/...`) is only affected if that mount moves into the shared file. Its path must then be removed there, not kept.
- REQ-I-07 is not covered by this probe. A same-name local override passes silently, so the CI assert for a service named `clickhouse` still needs to inspect the merged `config` output.
