# ADR-0008 · Contracts registry namespaced by producing Pod

| Field | Value |
|---|---|
| Status | Proposed — *decided & in effect on `feat/monorepo-integration`; acceptance = cross-Pod ratification* |
| Date | 2026-06-23 |
| Owners | Pod 1 (Generator) · Pod 2 (OTel Collector) |
| Proposer | Victor Urquiola |
| Supersedes | — (refines the DEFINE-era "single `contracts/v1/` SSOT" framing; supersedes nothing) |
| Related | [ADR-0007](0007-bronze-canonical-contract.md) (the read contract this houses) · input contract [`contracts/generator/v1/`](../../contracts/generator/v1/) · read contract [`contracts/collector/v1/pod2-pod3-read-contract.md`](../../contracts/collector/v1/pod2-pod3-read-contract.md) · SDD DEFINE/DESIGN |

> **Decided and in effect — not an open question.** The structure below is already
> implemented on `feat/monorepo-integration` and validated end-to-end (see
> [Consequences](#consequences)): both pipelines run against `contracts/generator/v1/` +
> `contracts/collector/v1/`. `Proposed` reflects only the outstanding **cross-Pod
> ratification** the WoW's ADR gate requires (Pod 1 + the Go owner ack at the sync) — a
> formality given the evidence, not unresolved debate. Build against the new layout now.

## Context

The monorepo introduced a single top-level `contracts/v1/` as the contract "single source
of truth" (SDD DEFINE/DESIGN). In practice it held **only the Pod 1 → Pod 2 input contract**
(`schema/otlp_output.schema.json` + the golden fixture). The `v1` directory read like "the
contracts, version 1," but it versioned *only* the input boundary, and there was **no home
in the registry** for any other boundary.

Two things changed the ground:

1. **The Pod 2 → Pod 3 read contract became first-class.** [ADR-0007](0007-bronze-canonical-contract.md)
   made Pod 3's bronze schema the canonical read contract. The accompanying read-contract
   document had been living under `docs/` — it needed a real home in the registry, versioned
   on its own cadence (it is `1.0.0.1` while the input is `1.0.0`).
2. **Two collectors implement the same contracts.** Rust (reference) and Go both consume the
   input contract and (will) write the read contract. A considered option — per-implementation
   contract directories (`contracts/collector-rust/v1/`, `contracts/collector-go/v1/`) — would
   **re-introduce the very divergence ADR-0007 just resolved**. This was not hypothetical: the
   stale per-collector `services/collector-{rust,go}/contract/` artifacts (a duplicated input
   schema + a read contract still describing the *superseded* hand-rolled schema) had already
   drifted.

A single flat `v1/` cannot express two independently-versioned boundaries with distinct
producers, and per-collector copies invite drift. The registry needs a structure that makes
the **boundary and its owner** explicit while keeping contracts implementation-agnostic.

## Decision

**Namespace `contracts/` by the producing Pod, one shared (implementation-agnostic) contract
per boundary, versioned per boundary by directory:**

```
contracts/
├── generator/v1/     # Pod 1 → Pod 2 INPUT  contract  (producer: generator)
└── collector/v1/     # Pod 2 → Pod 3 READ   contract  (producer: collector)
```

- **`generator/v1/`** — the OTLP output schema + golden fixture. Consumers read it via
  `CONTRACTS_DIR=/contracts/generator/v1`.
- **`collector/v1/`** — the Pod 2 → Pod 3 read contract: a prose document
  (`pod2-pod3-read-contract.md`) + a machine-readable companion
  (`pod2-pod3-read-contract.yaml`). Its **structural** source of truth remains the
  Pod-3-owned bronze DDL (`infra/clickhouse/init.d/01-bronze-otel.sql`, ADR-0007); the
  contract carries the *semantic* layer that points at it.
- **Implementation-agnostic.** There is exactly **one** `collector/` contract that every
  collector implementation (Rust, Go, future) writes into — never a per-language contract.
- **Versioned per boundary.** A breaking change opens `generator/v2/` or `collector/v2/`
  independently; the two boundaries bump on their own cadence.
- **Convention for future producers:** `contracts/<producing-component>/v<n>/`.

## Options considered

| Option | Summary | Verdict |
|---|---|---|
| **A. Keep single `contracts/v1/`** | One flat versioned dir | Rejected — misnomer (only the input lived there); no home for the read contract; one version axis can't serve two boundaries; doesn't scale to new producers |
| **B. Per-implementation** (`contracts/collector-rust/v1/`, `…-go/v1/`) | Each collector owns its contract copy | Rejected — re-introduces the divergence ADR-0007 resolved; contradicts collector interchangeability and ADR-0007's single bronze contract; the stale `services/collector-*/contract/` copies already demonstrated the drift |
| **C. Per-producing-Pod boundary (chosen)** | `generator/` + `collector/`, impl-agnostic, per-boundary versions | Chosen — explicit ownership seam, one contract per boundary regardless of implementation, independent versioning, scales to future producers |

## Trade-offs

**For:** a clear ownership seam per boundary; implementation-agnostic (one contract, N
collectors); independent per-boundary versioning; fixes the `v1`-means-input misnomer;
generalizes to future producing pods.

**Against:** a one-time runtime rewire — `CONTRACTS_DIR` and the golden paths move across
three services — and a cross-Pod blast radius (it relocates Pod 1's published contract and
edits Pod 1 generator code). Both are paid once and were validated end-to-end (below).

## Consequences

- `contracts/v1/{schema,golden}` → `contracts/generator/v1/`; `CONTRACTS_DIR=/contracts/generator/v1`
  in `docker-compose.yml` (×3), `Makefile`, the generator `Dockerfile`, `output_schema.py` +
  `test_golden.py` fallbacks, the Rust `config.rs`/`config.example.yaml`/compose mount and
  both Rust test `golden_path()` helpers.
- The Pod 2 → Pod 3 read contract moves to `contracts/collector/v1/`, gaining a machine-readable
  `pod2-pod3-read-contract.yaml` (a semantic-guarantees descriptor that defers structure to the
  bronze DDL, so it cannot drift from it).
- The stale `services/collector-{rust,go}/contract/` artifacts are removed.
- `contracts/README.md` becomes the per-boundary registry index; `README.md` + `CLAUDE.md`
  describe the registry.
- **Validated end-to-end (2026-06-23):** generator pytest 176; `cargo test` 76 lib + golden;
  `go test`; `make e2e COLLECTOR=rust` → `sentinel.*` bronze 40,200 / 40,200 / 83,400 / 69,300;
  `make e2e COLLECTOR=go` → `default.*` 40,200 / 40,200 / 152,700; 0 generator failures
  (schema resolved from `/contracts/generator/v1`).

> **Reading this later:** the evidence line above is a point-in-time record from 2026-06-23,
> when both collectors existed. `make e2e COLLECTOR=rust|go`, the Go collector and the
> `default.*` schema were all removed in PR #28 (merged 2026-08-12); the database formerly
> called `sentinel` is now `bronze`. The commands are not runnable today — they are kept as
> the evidence that was actually produced. The registry structure this ADR decides is
> unaffected.

## Risks

- **Cross-Pod churn.** Pod 1's generator code and both collectors' env changed. Mitigated by
  the e2e validation and a heads-up to Pod 1 (Vinicius) + the Go owner (Alex) at the sync.
- **Convention adherence.** A future producing pod must follow `contracts/<producer>/v<n>/`;
  documented in `contracts/README.md`.

## Next steps

1. **Acceptance gate** (Proposed → Accepted): cross-Pod ack from Pod 1 + the Go owner at the
   sync. The reorg is already executed and validated — acceptance is a ratification, not more work.
2. Future contracts follow the producer-namespaced convention.
3. If a JSON-consuming tool ever needs it, **generate** `contract.json` from the YAML
   (single edited source — do not hand-maintain a parallel copy).

## References

- [`contracts/README.md`](../../contracts/README.md) — the registry index
- [`contracts/generator/v1/`](../../contracts/generator/v1/) — Pod 1 → Pod 2 input contract
- [`contracts/collector/v1/pod2-pod3-read-contract.md`](../../contracts/collector/v1/pod2-pod3-read-contract.md) + [`.yaml`](../../contracts/collector/v1/pod2-pod3-read-contract.yaml) — Pod 2 → Pod 3 read contract
- [ADR-0007](0007-bronze-canonical-contract.md) — bronze = canonical read schema (the contract `collector/` houses)
