# Decision rulings — 2026-10-06

These Commander rulings supersede the open questions in DEC-A1, DEC-A2, DEC-A4, and
DEC-I2 for the current implementation cycle.

## DEC-A1 and DEC-A2: local runtime only

Everything runs locally using Docker and Make files. The supported runtime is the
repository's Docker Compose stack. This does not select Cloud Run, Kubernetes, VMs,
another remote host, or a production ClickHouse owner. ClickHouse stays on the pinned
local 25.4 MergeTree engine; deployed-provider validation remains deferred. T40, T41,
T43, and the local-secret portion of T44 are complete only within this scope.

## DEC-A4: defer TLS

The Commander authorized skipping TLS now and revisiting it in the future. T42 is
deferred; no in-process, edge, or sidecar design is selected, and future deployment TLS
requirements are not waived. Local host ports bind to loopback and service-to-service
traffic remains on the private Compose network.

## DEC-I2: update docs with each implementation PR

Documentation updates belong in the same implementation PR that changes the behavior.
The separate T45–T48 documentation wave is dissolved; each wave's doc work is absorbed
into its implementation work. If concurrent legs would touch the same documentation
path, serialize those legs to preserve ADR-0009 R1's disjoint-path rule. This keeps the
live pull-request instruction to fix invalidated documentation in the same change. The
current README records Silver models, backfill operation, and local runtime boundaries.
