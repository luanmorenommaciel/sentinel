# DEC-A1 — Compute form for the deployed services

**Owner** Captain / Commander · **Unblocks** T40, T43 directly; 6 tickets transitively (T40–T44, T48). T22 was removed from this list on 2026-10-05

Evidence tags: **[M]** measured this session · **[S]** measured per `spec/core-spec.md` §11.1, not re-run · **[D]** asserted in a repo document, not independently verified · **[R]** reasoned.

## 1. The question

Which platform runs the collector (long-lived gRPC server), flow-ui (SSE, in-memory state) and the generator (run-to-completion job): Cloud Run, GKE Autopilot, GKE Standard, or GCE VMs with Compose?

## 2. Why it's open

- Nothing in the repo commits to one. No IaC, no k8s, no cloudbuild; `rust-ci.yml:129` is `push: false` (`intent/core-intent.md` §3). `.claude/CLAUDE.md` names GCP as the first cloud target and nothing more (`git show HEAD:.claude/CLAUDE.md`, line 19).
- The platform determines four things the spec leaves parametric: how TLS terminates on hop 1 (`spec` §14.3), whether `:4317` auth is an edge policy (REQ-H-08), what "roll back" means (`design-spec.md:1097`), and the shutdown grace period (`spec` §7.4).
- `intent/design-spec.md:222-264` contains a matrix and a recommendation (Cloud Run + managed ClickHouse). The recommendation's own stated reason is that nobody owns ClickHouse, so it is conditional on DEC-A2, not independent of it.

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **Cloud Run** (services + Jobs) | No mTLS identity inside the collector; flow-ui pinned to `min=max=1`; short shutdown window **[D]** `design-spec.md:254-259`; cannot host ClickHouse | Self-hosting ClickHouse on the same platform |
| **GKE Autopilot / Standard** | A cluster is a second platform someone must own; grace period is tunable **[D]** | Nothing materially; it is the superset |
| **GCE VMs + Compose** | TLS on hop 1 is "ours to build"; the local Compose files become the deploy artifact **[D]** | The edge-termination answer to DEC-A4 (no managed edge exists) |

**Evidence is neutral between the first two.** The deciding input is not in the repo: whether Captain/Commander will accept a second unowned platform (a cluster). If DEC-A2 assigns a ClickHouse owner and self-hosts, GKE becomes the more natural fit (the design-spec says the same, `:249-251`). If DEC-A2 buys managed ClickHouse, Cloud Run is the lower-surface option **[R]**. Decide A2 first or together.

## 4. Established facts

- **[M] The collector ignores SIGTERM.** In a throwaway container from the local image `sentinel-collector-rust:dev` (log-only config, no ClickHouse): `docker kill -s TERM` left it `running` after 4 s; `docker kill -s INT` produced `shutdown signal received` and exit 0; `docker stop -t 12` took 12 s and exited 137 (SIGKILL), with no shutdown log line. Source: `src/main.rs:131-141` registers only `tokio::signal::ctrl_c()`. Image build provenance was not checked; the source agrees with the behaviour. The final-flush path was not exercised (no ClickHouse in the probe).
- **[D]** `spec` §7.4 and `design-spec.md:257` treat "graceful final flush inside the SIGTERM window" as a *trade-off of the platform choice*. On the evidence above it is a **pre-existing defect independent of the platform**: every candidate form stops containers with SIGTERM **[R]** (standard container-runtime behaviour, not looked up here). No ticket covers it (`grep -i sigterm plan/core-plan.md` is empty).
- **[D]** Mode is chosen by config shape (`src/main.rs:60-64`), so a deployed `collector.yaml` missing `grpc:` or `clickhouse:` silently degrades (T40).
- **[D]** Snapshot is per-process (`pipeline.py:136-240`), so flow-ui must be a single instance on any form.
- Buffer: 64 channel slots, `flush_interval_ms` 500, 3 flush attempts, then drop (`buffer.rs:66,70,140-141`, `spec` §7.4). Slot contents under real traffic are not measured.

## 5. What it unblocks

T40 (IaC, migrate-before-ingest, readiness), T43 (edge auth). Transitively T41, T42, T44, T48. T22 (`release.yml`) no longer waits on this decision (see below). Also shapes DEC-A4's edge-termination option.

## 6. What it cannot settle

- Cost, quotas and the platform's real shutdown grace period: none are in the repo and none were invented here. A grace-period figure must come from the chosen platform's documentation, then be compared with a measured worst-case flush time (a measurement nobody has taken).
- The SIGTERM defect needs its own ticket regardless of the answer.
- Plan inconsistency: T22 is blocked by DEC-A1, but `design-spec.md` A.2 calls registry/provenance "independent of both decisions... can land in wave 1". Only the Artifact Registry naming is GCP-specific, so T22 may not need to wait. **Resolved 2026-10-05:** the blocker was removed from T22 in `plan/core-plan.md`, with the rationale in the ticket; T23, T24 and T45's dependency on T22 are therefore no longer behind DEC-A1.
