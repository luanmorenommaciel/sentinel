# End-user error-span dashboard implementation plan

> Execution: use the `executing-plans` skill, working through each task with a failing behavioral test before its implementation and recording verification evidence.

**Goal:** Deliver a local read-only dashboard for exploring ClickHouse error spans.

**Architecture:** A React/Vite frontend calls a narrow Node.js API over the local Compose network. The API queries `bronze.otel_traces` as a dedicated SELECT-only identity and returns explicitly selected fields; attribute maps are never returned with the initial empty allowlist.

**Tech stack:** TypeScript, React, Vite, Node.js, ClickHouse, Docker Compose and Make.

**Spec:** `spec/end-user-dashboard-spec.md`; approved intent: `intend.md`.

## Global constraints

- Local Compose and Make only; loopback host binding; no remote deployment, TLS, authentication or authoritative alert model.
- Status `Error` defines an error span. Keep queries parameterized, credentials server-side and unapproved attributes absent from responses and logs.
- Presets: 1 hour, 24 hours (default), 7 days, 30 days. Refresh every 60 seconds and manually. Page size 50.
- API responses represent timestamps in UTC; UI renders local time and identifies the timezone. Target three seconds against generated local sample data, recording actual measurements.
- Follow repository worktree/leg ownership rules and preserve existing user changes. No destructive volume reset or external publication.

## Review focus

1. Values containing quotes or SQL syntax remain data, never query structure (T01).
2. Attribute maps and status messages containing secrets never escape the server, including failures (T01).
3. A timestamp at the lower bound is included and one at the upper bound excluded; all dashboard panels use the same explicit interval (T01–T02).
4. Equal timestamps, empty pages and new ingestion do not cause nondeterministic ordering; the UI reports the queried interval (T01–T02).
5. A failed refresh cannot be mistaken for an empty successful result or fresh data (T02).

## Interfaces and layout

Create `services/end-user-dashboard/` with `api/`, `web/`, package configuration, tests and Dockerfile. API is the sole ClickHouse consumer. Create its owned API contract at `contracts/end-user-dashboard/v1/openapi.yaml`; keep credential provisioning in `infra/clickhouse/` using existing migration and secret-file patterns. Integrate with `docker-compose.yml`, `Makefile`, `.env.example` and live README. Tasks that touch shared files are sequential.

The API exposes `GET /api/overview` and `GET /api/spans`, with `from`, `to`, optional exact `service` and `span` filters, plus `page` on spans. Both endpoints validate UTC instants, `from < to`, maximum 30-day interval, bounded filter lengths and positive page numbers. Return the explicit interval. Overview returns `total`, `bucketSeconds`, `trend` (`timestamp`, `count`) and `services` (`name`, `count`). Spans returns `items` (`timestamp`, `serviceName`, `spanName`, `statusCode`, `durationNs`, `traceId`, `spanId`), `page`, `pageSize`, `total`, `from` and `to`. A shared UI refresh constructs one interval and uses it for both calls. Sort by timestamp descending, then trace ID and span ID descending; use 50 rows per page. An invalid request returns 400 and an unavailable database returns a sanitized 503 JSON error. The exact response schema is owned by the OpenAPI contract and must encode these fields.

## Task 1: T01 — Contract and secure data API

**Leg:** `leg/dashboard/api-v1`; **blocked by:** none. **Owns:** `services/end-user-dashboard/api/`, root package configuration in `services/end-user-dashboard/`, `contracts/end-user-dashboard/v1/`. Shared infrastructure is deferred to T03.

- [ ] Define the versioned OpenAPI contract and fixtures for both endpoints using the interfaces above, including validation errors and 503. Bound filter values and page; prohibit arbitrary SQL.
- [ ] Write and run failing API tests for valid filtering, identical bounds, half-open intervals, stable ordering, page 2, malformed ranges, and an injected quote. Add a sentinel secret in attribute maps/status message and assert it does not appear in any response or error.
- [ ] Implement a read-only query adapter and handlers using parameterized ClickHouse queries and explicit column selection. Generate UTC trend buckets sized for each preset, fill empty intervals with zero, and group service counts with deterministic tie ordering. Never select attribute maps or status message while the allowlist is empty.
- [ ] Run the API suite and contract validation; record the red and green output. Add a real-ClickHouse integration test with seeded rows proving filters, aggregation, ordering and exclusion, to be run with T03's local stack.
- [ ] Proof: `cd services/end-user-dashboard && npm test -- --run` passes for API tests; validate the OpenAPI file with the selected project's local validator and record its exact command and output.

## Task 2: T02 — Browser experience

**Leg:** `leg/dashboard/ui-v1`; **blocked by:** T01 contract. **Owns:** `services/end-user-dashboard/web/` and its UI tests; coordinate shared package files after T01.

- [ ] Write and run failing UI tests for initial 24-hour overview, changing service/span filters, 50-row page navigation, local timezone label, detail/copy controls, empty results, a failed request with retry, and a 60-second refresh using fake time.
- [ ] Implement the responsive React interface against T01's contract. Use a shared absolute interval for both requests; avoid presenting a previous interval's response as current after filter changes. Render accessible labels, focus and contrast. Show HyperDX links only after verifying an existing stable format; otherwise copy IDs.
- [ ] Run UI tests and the production build. Verify keyboard and mobile/desktop layout in a browser; record what was actually inspected.
- [ ] Proof: `cd services/end-user-dashboard && npm test -- --run` and `npm run build` pass; browser checks cover the listed states.

## Task 3: T03 — Local integration and least privilege

**Leg:** `leg/dashboard/local-v1`; **blocked by:** T01, T02. **Owns:** dashboard Dockerfile, `infra/clickhouse/migrations/` and its init symlink as required, relevant local-secret provisioning, `docker-compose.yml`, `Makefile`, `.env.example`, README and integration tests. Serialize all shared-file edits.

- [ ] Write failing checks for loopback binding, dedicated account access to `bronze.otel_traces`, rejection of INSERT and other-table SELECT, and credential absence from images/logs. Follow existing migration numbering, idempotency and password-file provisioning conventions.
- [ ] Wire the service into Compose and Make, including health/readiness and configurable host port. Run under the existing private network; browser reaches the Node service on loopback. Document local startup, access, the empty allowlist and limitations.
- [ ] Run the real-ClickHouse integration test from T01 and the permission checks. Generate the repository's standard sample data, record row count and measurement method, and measure overview and list; report whether each meets three seconds.
- [ ] Proof: `make up`, the dashboard integration and access checks, and `docker compose config` pass on the local stack. Do not reset existing volumes to make a failure disappear.

## Task 4: T04 — Full verification and review

**Leg:** `leg/dashboard/review-v1`; **blocked by:** T01–T03. **Owns:** verification notes only; fixes return to the responsible paths sequentially.

- [ ] Run `make test`, `make lint`, `make build`, and `scripts/ci/run-invariants.sh`; run `make test-silver` if silver schemas were changed. Record commands, outputs and failures without treating local results as CI evidence.
- [ ] Review the complete diff against both repository conventions and every numbered spec requirement, including access grants, secret filtering and current live documentation. Fix substantive findings with regression tests; repeat affected checks.
- [ ] Proof: test results, browser/integration evidence, measured timings and two-axis review findings are recorded. Report any unverified checks or failed target explicitly.
