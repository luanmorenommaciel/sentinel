# End User Dashboard — Working Intent

**Status:** In progress — interview stage. This document records confirmed direction, verified repository facts, and decisions still open. It is not a final design or implementation specification.

## 1. Purpose and users

The dashboard will let business stakeholders and internal operators see alerts backed by Sentinel telemetry in ClickHouse. The information the user named includes resource attributes, span attributes, service names, span names, and status codes.

The first release should be read-only. Internal operators are the primary audience, with a clear overview that business stakeholders can also understand.

## 2. Confirmed direction

- Build a new end-user dashboard UI using Vite and Node.js.
- Keep the first release read-only.
- Help users understand error-span counts and trends, identify services with the most errors, and investigate spans and permitted attributes.
- Build a separate dashboard alongside the existing interfaces, reusing ClickHouse data.
- Target the existing local Docker Compose stack first; document production needs separately.
- Show spans with an `Error` status as **error spans**; do not label every error span an authoritative alert.
- Use a Node.js read-only API to query ClickHouse, keeping database credentials and queries server-side.
- Restrict the local dashboard to trusted local users and exclude sensitive attribute values; the specific keys and access mechanism remain open.
- Show alert-related data from ClickHouse, including resource attributes, span attributes, service names, span names, and status codes.
- Open on the last 24 hours, offer alternative time ranges, refresh every 60 seconds, and provide a manual refresh control.
- Let operators filter by time range, service name, and span name; sort error spans newest first; and open a detail view with status, timestamp, trace identifiers, and permitted attributes.
- Use an explicit allowlist for displayed attribute keys. Hide all unlisted keys until they are reviewed.
- Bind the first release to localhost for trusted local use. Authentication and remote access are deferred to a later deployment.
- Use React and TypeScript with Vite for the UI, and TypeScript for the Node.js API.
- Offer last hour, 24 hours, 7 days, and 30 days as time-range presets.
- Start with an empty attribute allowlist. Show no resource or span attribute values until individual keys are approved.
- Distinguish an empty result from an unavailable ClickHouse connection, and offer retry for a connection error.
- Show total error spans, a trend over the selected time range, and services ranked by error-span count; apply selected filters consistently.
- Paginate the result list at 50 spans per page, newest first.
- Support current desktop browsers and usable tablet/mobile layouts, keyboard navigation, readable contrast, and labeled controls.
- Target overview and list loading within three seconds on the local stack with the project's generated sample data; reassess using measured evidence if needed.
- Automatically choose trend bucket intervals for the selected range; display timestamps in the user's local timezone and identify the timezone.
- Read first-release span data from `bronze.otel_traces` through the Node.js API.
- Include trace and span identifiers, duration, and status in details. Link to HyperDX only if an existing reliable link format can be verified; otherwise make identifiers available to copy.
- Use a dedicated ClickHouse account with only the `SELECT` access needed by the dashboard, with credentials in server-side configuration.

The API shape and any future authoritative alert source are not yet decided.

## 3. Verified repository baseline

### Existing read surfaces

- `services/flow-ui` is an existing FastAPI application. Its browser client does not connect directly to ClickHouse; the server reads ClickHouse and the collector, holds an in-memory snapshot, and serves HTML plus SSE updates. It currently presents pipeline-focused boards.
- HyperDX is also configured in the local Compose stack for operator search, traces, and dashboards. Its ClickHouse connection uses a SELECT-only account.
- The repository documents the existing stack as local Docker Compose. Deployment and hosting for this proposed dashboard are not established here.

### Relevant ClickHouse data

- `bronze.otel_traces` stores one row per span. Relevant columns include `Timestamp`, `ServiceName`, `SpanName`, `StatusCode`, `StatusMessage`, `ResourceAttributes` (`Map(String, String)`), and `SpanAttributes` (`Map(String, String)`). Its TTL is 30 days.
- `silver.operation_executions` derives from bronze traces and exposes corresponding fields as `event_time`, `service_name`, `operation_name`, `status_code`, `resource_attributes`, and `operation_attributes`, with duration and trace/span identifiers. Its TTL is also 30 days.
- The checked-in ClickHouse migrations do not define an alert/event table. Existing flow-ui watcher states are computed by the UI service from telemetry/read models; watcher read models are described in their migration as inputs, not verdicts. The first release instead displays error spans.

Evidence: `infra/clickhouse/migrations/0001_bronze_otel.sql`, `0004_silver_layer.sql`, `0005_silver_watcher_models.sql`, `services/flow-ui/ARCHITECTURE.md`, `services/flow-ui/src/flow_ui/pipeline.py`, and `README.md`.

## 4. Open decisions

### Alert meaning and source

The first release displays error-status spans as error spans. Existing watcher verdicts and a persisted alert model are not selected for this release; their inclusion would require a separate decision.

### User-visible behavior

The default time range is the last 24 hours. Users can select other ranges; data refreshes every 60 seconds and on demand. Operators can filter by time range, service name, and span name, review newest error spans first, and open a detail view containing status, timestamp, trace identifiers, and permitted attributes.

### Application boundary and technology roles

**[OPEN]** Resolve:

- The API shape and exact ClickHouse grants used by the Node.js service.

### Access and data boundaries

The local release binds to localhost. Displayed attributes use an explicit reviewed-key allowlist, initially empty; unlisted keys are hidden. The repository's synthetic generator emits resource keys including `service.name`, `sentinel.synthetic`, `sentinel.scenario`, `sentinel.run_id`, `cloud.provider`, `cloud.account.id`, `cloud.region`, `cloud.availability_zone`, `cloud.platform`, and component-specific cloud or Kubernetes identifiers, plus span keys `component.name`, `component.type`, and `error`. These are observed keys, not an approved allowlist. Define user/tenant boundaries and the ClickHouse identity and grants before implementation.

### Delivery and operation

**[OPEN]** Define Compose integration, required health checks, logging/metrics, operational ownership, and production needs. The first delivery targets the local stack.

### Acceptance

**[OPEN]** Specify the generated sample data and measurement procedure for the three-second local target, and define remaining acceptance criteria for usefulness and data freshness.

## 5. SDLC path requested

The user requested the repository's grill → intent → spec → plan → TDD → code-review process. This file is the incomplete intent artifact for the first stage. After the open decisions are resolved and the intent is reviewed:

1. Write a formal spec with numbered `REQ-<area>-<n>` requirements and a neighboring design rationale document.
2. Build an implementation plan with ticket-level proof criteria.
3. Implement each ticket test-first (TDD), then verify the required project checks.
4. Review against repository standards and the approved spec before completion.

No UI, API, or database implementation requirements are authorized by this working draft.

## 6. Next interview round

The proposed intent is ready for user review. The specification and plan must resolve remaining implementation details, including API contracts, exact grants, test data, and the performance measurement procedure without inventing product requirements.

