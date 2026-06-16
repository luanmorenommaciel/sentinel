# Contract Review — Pod 1 → Pod 2 OTLP Output, v1.0.0

| Field | Value |
|---|---|
| Reviewer | Victor Urquiola (Pod 2 — Collector) |
| Reviewed | `001-otel-data-generator` branch, current HEAD |
| Scope | `contract/schema/otlp_output.schema.json` + companions |
| Date | 2026-06-01 |
| Status | Draft — for Pod 1 discussion |

## TL;DR

Excellent foundation. **4 blocking issues** (B1–B4), **6 non-blocking concerns** (N1–N6), **6 suggestions** (S1–S6). Ready to merge into `main` after the blockers are addressed or explicitly deferred.

## What's strong (lead with this)

1. **Versioned end-to-end.** `contract_version` in every emitted signal, semver-validated, with `VersionedContract` Pydantic base. Sync 02 D8 ("contracts versioned") satisfied.
2. **JSON Schema 2020-12 with `if/then/else` discrimination.** Modern, validator-portable. Pod 2 can derive Rust types via `schemars` or Go types via `jsonschema-cli` without re-spec.
3. **Sentinel-specific resource attrs required** (`sentinel.synthetic`, `sentinel.scenario`, `sentinel.run_id`). Pod 2 can filter/route on these without parsing payloads.
4. **Golden dataset with deterministic seed** (`baseline_seed42.jsonl`). Exactly what Pod 2 needs for unit + integration tests against a known-good fixture. **This is the single most useful artifact for me as a downstream consumer.**
5. **GCP-faithful resource attributes researched** against OTel semantic conventions + Cloud Monitoring metric names. Honest about being unverified vs a live tenant (trust-but-verify A9).
6. **Topology graph integrity validated** (`_depends_on_exist`, `_unique_names`). The dependency DAG is structurally sound — no orphaned edges, no name collisions.
7. **Five named scenarios** + `extends`/`phases` hint at a clean DSL for failure injection. Black Friday + stalled_job + latency_degradation alone cover the Latency + Volume Watcher demo cases.
8. **Honest scope boundaries** — `clickhouse_schema.yaml` headers explicitly mark it DEV-ONLY for the rejected direct path; Pod 3 owns the canonical ClickStack schema.

## Blocking concerns

### B1 — `attributes` / `resource_attributes` typed as `{type: "string"}` lose OTel fidelity

OTel attribute values are a union of `string | bool | int | double | []string | []bool | []int | []double | bytes`. The contract forces everything to `string`. Consequences:

- Numeric attributes get stringified at the boundary (`"42"` not `42`)
- Pod 2 must detect-and-cast on receive, with no schema signal for *which* attribute is numeric
- Cloud Monitoring labels (port numbers, queue depths) lose their type identity
- Real GCP OTLP (the eventual replacement) will deliver non-string values → Pod 2 will hit a schema break when the generator swaps out

**Proposal:**

```json
"attributes": {
  "type": "object",
  "additionalProperties": {
    "oneOf": [
      {"type": "string"},
      {"type": "boolean"},
      {"type": "number"},
      {"type": "array", "items": {"type": "string"}}
    ]
  }
}
```

Or document the stringification policy explicitly: *"all OTel attribute values are stringified at this boundary; downstream consumers MUST re-parse."* Either is fine — the implicit string-only contract today will surprise Pod 2 when real cloud data lands.

### B2 — Metric `type` enum missing `histogram`

Current: `enum: ["gauge", "sum"]`. OTel has at least: Counter (sum), UpDownCounter (sum), Gauge, Histogram, ExponentialHistogram. The **Latency Watcher (W05, per spec)** explicitly tracks `p50/p95/p99` — that's histogram territory. Cloud Monitoring emits histogram metrics for distribution-shaped data (request latency, payload size).

If the generator can't emit histograms yet, fine — but the *contract* should reserve the enum value so Pod 2 isn't blindsided by a v1.1.0 break:

```json
"type": {"type": "string", "enum": ["gauge", "sum", "histogram"]}
```

(Even if `output_schema.py` raises on histogram today.)

### B3 — Span `status_code` enum missing `UNSET`

OTLP spec defines three: `UNSET`, `OK`, `ERROR`. Default is `UNSET`. The contract enforces `["OK", "ERROR"]` only — meaning the generator must explicitly choose one, and Pod 2 can't represent OTel's default state. When real spans land from GCP, every span without an explicit status will fail validation.

**Proposal:** `enum: ["UNSET", "OK", "ERROR"]`. Generator picks OK/ERROR; default contract path accepts UNSET.

### B4 — Contract version `1.0.0` at Sync 02 is premature

Semver 1.0.0 commits to backward-compatibility from this point forward. We're three syncs in; the consumer (Pod 2) hasn't shipped a single line of code; the producer hasn't survived its first real consumer iteration.

**Recommendation:** start at **`0.1.0`**, bump to `1.0.0` after the first Pod 1↔Pod 2 round-trip validates that the contract holds at a real load.

This is more than cosmetic. If we hit B1/B2/B3 above and have to break the wire shape, we'll be writing a `2.0.0` ADR in week 3 — signaling churn we don't actually have.

## Non-blocking concerns

### N1 — `signal_type: "span"` vs ClickHouse table `otel_traces`

The signal type says "span" but the storage shape says "traces." Both are correct OTel-isms (signals are spans; the storage is traces) — but the inconsistency will trip readers. Either standardize the wire term to "trace" or document the relationship explicitly. Pod 3 owns the storage table name, so this is mostly an FYI.

### N2 — No `maxProperties` on `attributes`

OTel SDKs cap span attributes (typically 128). Without a contract cap, a buggy producer can emit pathologically large attribute maps that crash the Collector's batcher. Suggest `maxProperties: 128` on both attribute maps.

### N3 — `time_unix_nano` lacks `maximum`

Anomaly detection cares about clock skew. A timestamp 50 years in the future is itself an anomaly worth flagging at boundary. Suggest a soft cap (e.g., `now + 1h` worth of nanos) or document this is a Watcher concern, not a contract concern.

### N4 — `trace_id` / `span_id` regex is lowercase-only

`^[0-9a-f]{32}$`. OTLP doesn't forbid uppercase. If anything ever sends `^[0-9A-F]{32}$`, we reject valid data. Either normalize on the producer side (add a test) or accept both: `^[0-9a-fA-F]{32}$`. First option is cleaner.

### N5 — Schema `$id` is not resolvable

`https://sentinel/contract/otlp_output.schema.json` 404s. Either point at the GitHub raw URL once merged, or use a `urn:` scheme. Cosmetic but matters when external tooling (or future open-sourcing) tries to dereference.

### N6 — No `examples` block in the schema

JSON Schema supports `examples: [...]`. The golden file has them already — adding two or three to the schema makes self-documentation possible and helps tooling generate test data. Trivial addition.

## Suggestions

### S1 — Publish `.proto` definitions too

Pod 2 going Rust (per ADR-0004 proposal on `feat/rust-otel-collector`) prefers `prost`-generated types from `.proto` files for performance — same as Go would. The JSON Schema is the human-readable contract; the `.proto` is the binary wire contract. If Pod 1 is willing to commit to both, the Collector's deserialization stays zero-copy.

If you're already using `opentelemetry-proto` upstream and just serializing to JSON for transport, perfect — say so in the schema description. Pod 2 can subscribe to the protobuf wire directly when we swap to gRPC.

### S2 — Document attribute-key semantic conventions

The schema requires `cloud.provider` and `service.name` (great) but doesn't reference the OTel semantic-conventions spec the keys come from. A `description` field pointing at <https://opentelemetry.io/docs/specs/semconv/> would make the contract self-describing for future Astronauts.

### S3 — Multi-cloud key conflict

Right now `resource_attributes` required keys are GCP-centric (`cloud.provider: gcp`). When Pod 1 adds Azure (per the Sync 02 roadmap), what changes? The schema is currently un-cloud-aware. Two options:

1. Keep the schema generic; let `cloud.provider` be the discriminator
2. Add a per-cloud `allOf` branch (mirroring how `signal_type` discriminates)

Option 1 is simpler and what the existing schema implies. Just confirm.

### S4 — Make scenarios extensible

`scenarios/baseline.yaml` has `extends: null` and `phases: []`. The mechanic is clearly there (inheritance + phases), but `baseline` is empty. Worth documenting the shape of a non-trivial scenario (e.g., `failure_spike.yaml`) in a README so Pod 2 knows what to expect from non-baseline runs.

### S5 — Add a `validate-fixture` CI gate

The golden file `baseline_seed42.jsonl` is the contract's executable test. Suggest a CI gate that runs every PR:

```bash
jq -c '.' contract/golden/baseline_seed42.jsonl | \
  while read line; do echo "$line" | ajv validate -s contract/schema/otlp_output.schema.json -d /dev/stdin; done
```

If schema and golden diverge, CI fails on the producer's PR. That's the contract failsafe Pod 2 needs.

### S6 — Versioning policy doc

Once the contract is `1.0.0` (real), what's the bump policy? `MAJOR` = breaking wire change, `MINOR` = additive field, `PATCH` = doc fix? A 10-line `contract/VERSIONING.md` covers this. Pod 2's consumer code keys its compatibility window on this.

## What Pod 2 commits to do *because* of this contract

Concrete commitments from the Collector side, for the record:

1. **Derive a Rust type from this schema** in `services/collector-rust/` using `schemars` (or hand-rolled `serde` matching the schema). PR follows once B1–B4 are resolved.
2. **Run the golden dataset through the Collector** as a fixture test in CI — same data must produce the same ClickHouse rows every time.
3. **Validate `contract_version`** on every received signal; reject mismatched versions explicitly (with the version in the error) rather than corrupting downstream.
4. **Surface contract-violation counts** as Collector meta-telemetry, so Pod 1 sees them in the Watcher feedback loop.

## Recommended next steps

1. **Pod 1 PR amendments** addressing B1–B4 (or explicit rejections-with-reasoning for any we want to defer). Ideally one commit, easy to review.
2. **Convert this review to PR comments** so the thread lives on the contract PR.
3. **Merge to `main`** once B1–B4 are resolved or explicitly deferred with an Issue per deferral.
4. **Pod 2 opens a sibling PR** with the Rust consumer types derived from the schema — proves the contract is consumable.

## References

- Pod 1 PR / branch: `001-otel-data-generator`
- Files reviewed:
  - `contract/schema/otlp_output.schema.json`
  - `contract/provider_profiles/gcp.yaml`
  - `contract/topology/default.yaml`
  - `contract/scenarios/baseline.yaml`
  - `contract/golden/baseline_seed42.jsonl`
  - `contract/clickhouse_schema.yaml`
  - `src/otelgen/contract/output_schema.py`
  - `src/otelgen/contract/models.py`
- Sync 02 D8 — "Contract-driven development between every component"
- OTel attribute spec — <https://opentelemetry.io/docs/specs/otel/common/#attribute>
- OTel semantic conventions — <https://opentelemetry.io/docs/specs/semconv/>
- ADR-0004 (Pod 2 Collector language) — `feat/rust-otel-collector` branch

---

*Authored with `Co-Authored-By: Claude Opus 4.7` per the Crew B attribution contract.*
