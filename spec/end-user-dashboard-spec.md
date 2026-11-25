# End-user error-span dashboard specification

Status: proposed for review. Source: `intend.md`. Scope: local Docker Compose and Make, in accordance with `plan/decisions/DEC-2026-10-06-local-scope.md`.

## Purpose and scope

- **REQ-SCOPE-1** Provide a separate read-only dashboard for internal operators, with an overview understandable to business stakeholders.
- **REQ-SCOPE-2** Present spans whose `StatusCode` is `Error` as error spans. Do not present them as authoritative alerts. Alert management and persisted alert models are outside this release.
- **REQ-SCOPE-3** Use Vite, React and TypeScript for the browser UI, and a TypeScript Node.js API for ClickHouse access. Keep credentials and SQL server-side.
- **REQ-SCOPE-4** Run within the existing local Compose stack, with host ports bound to loopback. Production hosting, remote access, user authentication, and TLS are outside this local release.

## Data and security

- **REQ-DATA-1** Query `bronze.otel_traces` with a dedicated ClickHouse identity granted only the SELECT access needed on that table. Configure its credentials server-side and do not commit secrets.
- **REQ-DATA-2** Use parameterized query values and bound time ranges; do not accept SQL or database identifiers from the client.
- **REQ-DATA-3** Do not return resource or span attribute values unless their exact keys appear in a server-side allowlist. The initial allowlist is empty; this applies to every API response and error log.
- **REQ-DATA-4** Show service name, span name, status, timestamp, duration, trace ID and span ID. Do not expose status messages or other free-text fields by default.
- **REQ-DATA-5** Treat times as instants in UTC at the API boundary; render them in the viewer's local timezone with the timezone identified.

## User experience

- **REQ-UI-1** Default to the last 24 hours; offer last hour, 24 hours, 7 days and 30 days. Refresh every 60 seconds and on manual request.
- **REQ-UI-2** Filter by time range, service and span name. Apply the same filters to the total count, trend, service ranking and list.
- **REQ-UI-3** Show the error-span total, a time trend with automatically selected bucket size, and services ranked by error-span count.
- **REQ-UI-4** Show error spans newest first, 50 per page, with page navigation; show the fields in REQ-DATA-4 in an accessible detail view and permit copying trace and span IDs.
- **REQ-UI-5** Add a HyperDX link only if an existing reliable link format is verified; otherwise provide copyable identifiers.
- **REQ-UI-6** Distinguish loading, empty results and failed data loads. On failure provide retry and do not present stale data as current.
- **REQ-UI-7** Support current desktop browsers and usable tablet/mobile layouts, keyboard navigation, labeled controls and readable contrast.

## API contract

- **REQ-API-1** Provide read-only HTTP endpoints for the overview and paginated span list. Requests accept a preset time window and optional service and span filters; list requests accept a page number. Reject invalid or oversized inputs with HTTP 400.
- **REQ-API-2** Return structured JSON with counts, UTC bucket timestamps, service counts, pagination metadata and the permitted span fields. No endpoint accepts arbitrary SQL or modifies stored telemetry.
- **REQ-API-3** A ClickHouse failure yields a non-sensitive error response and a server error status, distinguishable from a successful empty result. Browser-accessible responses and logs must not contain credentials or unapproved attributes.
- **REQ-API-4** Limit the maximum selected window to 30 days. Resolve each overview and page request against explicit start and end instants, and return those instants so the UI can identify the interval queried.

## Verification

- **REQ-TEST-1** Develop behavior test-first; cover filtering, counts, pagination, time boundaries, empty results, database failure, attribute exclusion and input validation. Verify database grants against a real local ClickHouse instance.
- **REQ-TEST-2** Verify the UI's overview, filtering, details, refresh, empty and error states, and keyboard navigation with representative data.
- **REQ-TEST-3** Measure overview and list loading against the project's generated sample data on the local stack. The initial target is three seconds; report the data volume, measurement method and actual results rather than claiming an unmeasured guarantee.
- **REQ-TEST-4** Run applicable repository checks (`make test`, `make lint`, `make build`, and `scripts/ci/run-invariants.sh`), report actual results, and review changes against the spec and repository standards. Run silver checks if silver schemas are changed.

## Design decisions and remaining implementation choices

Raw bronze spans directly contain the requested fields and avoid defining an alert model. A narrow Node.js API keeps database access and attribute filtering out of the browser. An empty attribute allowlist favors safe initial behavior; approving useful keys is a future user decision. Trend bucket thresholds, exact endpoint shapes, page consistency under concurrent ingestion, Compose wiring, test fixtures and performance measurement procedure must be made explicit in the implementation plan while preserving the requirements above.
