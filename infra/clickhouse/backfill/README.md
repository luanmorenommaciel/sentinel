# Silver backfill operations

The runner replays historical Bronze partitions into the Silver base tables and
then recomputes the dependent rollups. It uses Bash and `clickhouse-client` only.
The local proof targets ClickHouse 25.4 with plain `MergeTree`; deployed-provider
validation is deferred by the DEC-A2 local-only ruling.

```sh
make backfill-silver FROM=2026-10-01 TO=2026-10-02 PHASE=1
make backfill-silver FROM=2026-10-01 TO=2026-10-02 PHASE=2
```

`TO` is inclusive. The default range is yesterday only. Any `TO` on or after
ClickHouse's current date is refused and recorded in `_meta.backfill_runs`; there
is no override. The live partition procedure is operational: pause ingestion,
wait for in-flight writes to drain, then use a separately reviewed operator
procedure to repair that partition. `backfill-silver` still refuses it while its
date is ClickHouse's current date, even if ingestion is paused; the procedure is
not a runner override. This runner does not automate pausing ingest.

Phase 1 rebuilds `log_events`, `operation_executions`, and `metric_observations`
from the three deterministic base MVs. It never writes to `bronze.otel_traces`.
Phase 2 rebuilds `metric_stats_1m`, `volume_1m`, and
`resource_key_presence_1m`; it requires a successful phase-1 ledger row for each
partition. `call_edges_1m` is refresh-driven and is not backfilled.

The checksum projections in `canonical/` intentionally duplicate the staging
queries in `sql/`. The test target compares each pair so a staging-only change
cannot also redefine the expected checksum and silently bless itself.

Do not run this against a production provider until its partition replacement
behavior has been measured. DEC-A2 currently authorizes only local MergeTree.
