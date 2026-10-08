---
id: T-20261007-python-ci
title: "Gate the two Python services in CI with ruff and pytest"
status: done
format_version: 3
profile: standard
effort: S
budget_iterations: 15
agent: any
parent: intent/intent.md
depends_on: []
supersedes: (none)

touches_paths:
  - .github/workflows/python-ci.yml
creates_paths:
  - .github/workflows/python-ci.yml
source_note: "intent/intent.md §3 Candidate B; scope narrowed to ruff + pytest by owner decision 2026-10-07"
created: 2026-10-08T02:20:29Z
tags: [ci, python, pod1, flow-ui]
owner: (none)
priority: P2
severity: refactor
due_date: (none)
precondition: (none)
blocked_reason: (none)
security_class: (none)
source_action_item: (none)
tracker_ref: github:34
execution_backend: any
signed_off: true
signed_off_by: adilsoncesar
signed_off_at: 2026-10-08T02:27:00Z
accepted: true
accepted_by: adilsoncesar
accepted_at: 2026-10-08T02:37:02Z
evidence_refs:
  - "Makefile sha256 6dbc419236beb9c6 — defines test-generator, test-flow-ui, lint-generator, lint-flow-ui"
  - "rust-ci.yml sha256 626420616eb01988 — the path-scoping and gate-mapping model to mirror"
  - "generator-python/pyproject.toml sha256 96722bcebfba0e03 — setuptools, py>=3.10, has tool.ruff"
  - "flow-ui/pyproject.toml sha256 9fd64f405e4bf44a — hatch, dependency-groups, py>=3.11, no ruff config"
  - "repo HEAD 3af2ee7 — .github/workflows holds only rust-ci.yml and pr-linked-issue.yml"
signed_off_sig: hmac-sha256-v3:76f99aca:4193a4489e513875f400462b1bde736dddb0c8982cbddd8f68354f2202c11fe2
accepted_tier: 1
accepted_attempt_id: 58278636-5473-4184-94fa-5b681153f937
accepted_authorization_ref: hmac-sha256-v3:76f99aca:4193a4489e513875f400462b1bde736dddb0c8982cbddd8f68354f2202c11fe2
acceptance_record_digest: sha256:a4653f06f0916b9b2bd71372388eb40d8fb79bb2b87acc735f7063857dda432d
---

# "Gate the two Python services in CI with ruff and pytest"

> **Why:** `services/generator-python` and `services/flow-ui` carry pytest suites and ruff
> configuration that no workflow invokes, so a PR breaking either service passes CI. Issue #34
> names this gap; `intent/intent.md` §3 Candidate B records that the suites, Docker runners and
> Make targets already exist and only the workflow file is missing.

---

## Goal

A single `.github/workflows/python-ci.yml` runs ruff and pytest for both Python services on
pull requests and on pushes to `main`, path-scoped so that a Rust-only or docs-only change does
not trigger it. It mirrors the structure already proven by `rust-ci.yml`: explicit `paths:`
filters, a `concurrency` group that cancels superseded runs, and a header comment mapping each
job to the gate it satisfies. The four commands it runs are the ones the `Makefile` already
defines, so local and CI results cannot diverge.

---

## Context

Scope is **ruff + pytest only**, fixed by owner decision on 2026-10-07. The Crew B WoW names
seven gates, but no mypy, bandit, safety or coverage configuration exists anywhere in the tree —
those require new config, not a workflow, and remain separate candidates. See
`intent/intent.md` §3 for the full candidate inventory and the standing exclusions.

The two services are not symmetric, and the workflow must not pretend they are: generator is
setuptools-based with `requires-python >=3.10` and a `[tool.ruff]` block; flow-ui is
hatch-based with `dependency-groups` and `requires-python >=3.11` and no ruff configuration of
its own. Both existing Make targets standardise on `python:3.12-slim`, which satisfies both
floors.

A workflow file alone does not block a merge — that requires branch protection, which
`.claude/CLAUDE.md` lists under *Open*. This task delivers the running gate, not its
enforcement.

---

## Behavior

- **B-1** — GIVEN a pull request touching `services/generator-python/**` or
  `services/flow-ui/**` WHEN `python-ci` runs THEN ruff and pytest both execute for each of the
  two services, and a non-zero exit from any of the four fails the workflow.
- **B-2** — GIVEN a pull request touching only `services/collector-rust/**` or only `docs/**`
  WHEN CI runs THEN `python-ci` does not trigger, matching the polyglot path-scoping rule
  `rust-ci.yml` already follows.

---

## Success Criteria

Each criterion is a runnable bash function returning 0 (pass) or non-zero (fail).
Each MUST be terminal (deterministic, idempotent, non-flaky).

```bash
# eval-1: the workflow exists, is named python-ci, and both services are gated by ruff AND pytest
eval_1() {
  f=.github/workflows/python-ci.yml
  [ -f "$f" ] || return 1
  grep -Eq '^name:[[:space:]]*python-ci$' "$f" || return 1
  for svc in generator-python flow-ui; do
    grep -q "services/$svc" "$f" || return 1
  done
  grep -q 'ruff' "$f" || return 1
  grep -Eq 'pytest' "$f" || return 1
  return 0
}

# eval-2: the workflow is path-scoped on both pull_request and push, and never gates the Rust subtree
eval_2() {
  f=.github/workflows/python-ci.yml
  [ -f "$f" ] || return 1
  grep -q 'pull_request:' "$f" || return 1
  grep -q 'push:' "$f" || return 1
  [ "$(grep -c '^[[:space:]]*paths:' "$f")" -ge 2 ] || return 1
  grep -q '.github/workflows/python-ci.yml' "$f" || return 1
  grep -q 'services/collector-rust' "$f" && return 1
  return 0
}

# eval-3: the gates actually gate — no continue-on-error, and the YAML parses
eval_3() {
  f=.github/workflows/python-ci.yml
  [ -f "$f" ] || return 1
  grep -Eq 'continue-on-error:[[:space:]]*true' "$f" && return 1
  grep -q 'concurrency:' "$f" || return 1
  python3 - "$f" <<'PY' || return 1
import sys
raw = open(sys.argv[1], 'rb').read()
sys.exit(1 if (b'\t' in raw or not raw.strip()) else 0)
PY
  return 0
}
```

---

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: python-ci exists and runs ruff + pytest for both Python services
    runnable: bash
    check_type: deterministic
    verifies: [B-1]
    terminal: true
    expected_duration_sec: 5
  - id: eval_2
    description: triggers are path-scoped on pull_request and push and exclude the Rust subtree
    runnable: bash
    check_type: deterministic
    verifies: [B-2]
    terminal: true
    expected_duration_sec: 5
  - id: eval_3
    description: no continue-on-error, concurrency declared, file is tab-free and parses
    runnable: bash
    check_type: deterministic
    verifies: [B-1, B-2]
    terminal: true
    expected_duration_sec: 5

retry_policy:
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context

agent_contract:
  version: 2
  read: [intent, behavior, contract, guardrails, operations]
  produce:
    - config
  required_tools: [git, bash]
  timeout_minutes: 30
  sandbox_type: host
  output_artifacts:
    - .github/workflows/python-ci.yml
  mcp_dependencies: []
  emit:
    - pass
    - fail
    - retry_with_reason
    - parked_with_context
  backend_metadata: {}
```

---

## Exit Check

```bash
# Final proof-of-done. Returns 0 only when ALL evals pass.
eval_1 && eval_2 && eval_3
```

---

## Rollback Plan

(none — this task is append-only or additive with no destructive changes)

---

## Observability Hooks

- **Expected duration:** under 5 minutes per run; the two pytest suites are 16 test files total
- **Key metric:** `python-ci` conclusion on pull requests touching the two service paths
- **Alert condition:** the workflow does not appear on a PR that edits either service — a
  `paths:` filter is wrong, which fails silently by never running
- **Log tail:** `gh run list --workflow=python-ci.yml` and `gh run view <id> --log-failed`

---

## Anti-Patterns

- **Don't invoke the Docker-based `make` targets from CI** — `DK_RUN` builds a container and a
  fresh venv per target to spare the host a toolchain, which a GitHub runner does not need.
  Use `actions/setup-python` pinned to 3.12 and install each service directly.
- **Don't add `continue-on-error` to make a red gate green** — a reporting-only gate is
  indistinguishable from the gap this task closes. Fix the code or narrow the ruff selection
  explicitly in `pyproject.toml`.
- **Don't widen into mypy, bandit, safety, coverage or markdownlint** — all four are absent
  from the tree and out of scope by owner decision; adding them here hides a config change
  inside a workflow change.

---

## Do-Not-Touch

Files the executor MUST NOT modify:

- `.github/workflows/rust-ci.yml`
- `.github/workflows/pr-linked-issue.yml`
- `Makefile`
- `services/*/src/**` and `services/*/tests/**`

---

## Open Questions

Things the executor should resolve DURING build, not assume:

1. **Lint scope asymmetry** — `lint-generator` checks only `src`, while `lint-flow-ui` checks
   `src tests scripts`. Bringing generator to parity may surface pre-existing findings in its
   `tests/`. Run ruff over the wider scope first; if it is not clean, keep each service at its
   current Make-target scope and record why, rather than fixing lint findings inside this task.
2. **One workflow or a matrix** — the two services differ in build backend (setuptools vs
   hatch) and dependency declaration (`[project.optional-dependencies]` vs
   `[dependency-groups]`), so a naive matrix needs a per-service install step. Prefer two jobs
   in one workflow if the matrix needs branching on service name.
