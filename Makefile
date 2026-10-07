# Sentinel monorepo — Rust end-to-end pipeline.
#
#   make e2e                  # full pipeline with the Rust collector
#   make up / init / generate / down / reset / logs

SCENARIO  ?= baseline
SEED      ?= 42
WINDOW    ?= 5m
# Stream-mode knobs: DURATION is the wall-clock run cap, STEP the tick interval.
DURATION  ?= 60s
STEP      ?= 1s
RATE      ?= 200
# Host-only override for OTLP when another local process owns 4317. The
# collector and Compose-network clients always use the canonical container port.
COLLECTOR_OTLP_HOST_PORT ?= 4317
export COLLECTOR_OTLP_HOST_PORT

.PHONY: help up init migrate generate generate-stream ui down-ui e2e down reset logs ps \
        build test test-generator test-collector-rust test-flow-ui \
        test-generator-integration test-backfill audit-python \
        test-silver sample-silver lint lint-generator lint-collector-rust lint-flow-ui

# Docker runner for per-service build/test/lint — no host toolchains required.
DK_RUN := docker run --rm --user $(shell id -u):$(shell id -g) -v "$(CURDIR)":/w

# The Python image the test targets run in. Overridable so CI can sweep the
# supported interpreters against one Make target rather than re-declaring the
# command per version (REQ-B-03): `PYTHON_IMAGE=python:3.10-slim make test-generator`.
# The generator declares >=3.10 and flow-ui >=3.11, so 3.10 is expected to FAIL
# for flow-ui — that floor is only testable because the image is a variable.
PYTHON_IMAGE ?= python:3.12-slim

help:                ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  SCENARIO=$(SCENARIO)  SEED=$(SEED)  WINDOW=$(WINDOW)  PYTHON_IMAGE=$(PYTHON_IMAGE)"
	@echo "  DURATION=$(DURATION)  STEP=$(STEP)  RATE=$(RATE)  COLLECTOR_OTLP_HOST_PORT=$(COLLECTOR_OTLP_HOST_PORT)"

up:                  ## Start ClickHouse, migrate, then start the Rust collector
	docker compose up -d clickhouse
	@attempt=0; while [ "$$attempt" -lt 30 ]; do \
		if docker compose exec -T clickhouse clickhouse-client -q "SELECT 1" >/dev/null 2>&1; then \
			echo "ClickHouse ready"; break; \
		fi; \
		attempt=$$((attempt + 1)); sleep 2; \
	done; \
	[ "$$attempt" -lt 30 ] || { echo "ClickHouse did not become ready" >&2; exit 1; }
	$(MAKE) migrate
	docker compose up -d --build collector-rust
	@attempt=0; while [ "$$attempt" -lt 30 ]; do \
		if curl -fsS http://127.0.0.1:9090/metrics >/dev/null 2>&1; then \
			echo "collector ready at 127.0.0.1:$(COLLECTOR_OTLP_HOST_PORT) (metrics on 127.0.0.1:9090)"; exit 0; \
		fi; \
		attempt=$$((attempt + 1)); sleep 2; \
	done; \
	echo "collector did not become ready at http://127.0.0.1:9090/metrics" >&2; \
	docker compose logs collector-rust; exit 1

init:                ## No-op: the canonical bronze schema auto-applies on ClickHouse boot
	@echo "Rust → canonical bronze schema (bronze.*) auto-applies on ClickHouse boot via infra/clickhouse/init.d/; nothing to apply"

# One operator interface for the runner (REQ-B-03): CI invokes this target, and
# never a re-declared `migrate.sh` command line. `CH_CLIENT` is injected rather
# than guessed because getting it wrong migrates the wrong database — and it
# carries no `--multiquery` (the script appends that itself) and no credential
# (`ps` shows an argv to every user on the box; the script reads
# `CLICKHOUSE_PASSWORD` instead).
#
# The service name is literally `clickhouse`, as at `:80` — REQ-I-07 depends on
# that name surviving the Compose unification in T12–T15.
# `MIGRATION_PW_FILE` is a PATH to the role password, not the value: migration
# 0002 creates its users with `IDENTIFIED WITH sha256_password BY {pw:String}` and
# the runner supplies the parameter on stdin. Copy
# infra/secrets/ch_password.example to infra/secrets/ch_password (gitignored) once;
# the root stack mounts the same file into the collector and flow-ui.
migrate:             ## Apply ClickHouse DDL migrations, recording each in _meta.schema_migrations
	@test -r infra/secrets/ch_password || { \
		echo "migrate: infra/secrets/ch_password is missing."; \
		echo "  cp infra/secrets/ch_password.example infra/secrets/ch_password"; \
		echo "  then put a password in it (gitignored; SPEC §14.2)."; \
		exit 1; }
	MIGRATION_PW_FILE=infra/secrets/ch_password \
	CH_CLIENT="docker compose exec -T clickhouse clickhouse-client" \
		bash infra/clickhouse/migrate.sh

backfill-silver:      ## Recompute historical Silver partitions (FROM / TO / PHASE)
	CH_CLIENT="docker compose exec -T clickhouse clickhouse-client" \
		bash infra/clickhouse/backfill/backfill.sh $(if $(FROM),FROM=$(FROM)) $(if $(TO),TO=$(TO)) PHASE=$(if $(PHASE),$(PHASE),all)

test-backfill:        ## Verify the backfill runner refuses the live partition
	bash infra/clickhouse/backfill/tests/runner-refusal.test.sh
	bash infra/clickhouse/backfill/tests/canonical-sync.test.sh

generate:            ## Run the generator → OTLP :4317 (SCENARIO / SEED / WINDOW configurable)
	docker compose run --rm generator \
		--scenario $(SCENARIO) --seed $(SEED) --window $(WINDOW) \
		--delivery otlp --otlp-endpoint http://collector:4317

generate-stream:     ## Generate in real time (paced by wall clock) — DURATION / STEP / RATE
	docker compose run --rm generator \
		--mode stream --duration $(DURATION) --step $(STEP) --rate $(RATE) \
		--scenario $(SCENARIO) --seed $(SEED) \
		--delivery otlp --otlp-endpoint http://collector:4317

ui:                  ## Start ClickHouse + flow-ui independently at http://127.0.0.1:8080
	docker compose up -d --build flow-ui
	@attempt=0; while [ "$$attempt" -lt 30 ]; do \
		if curl -fsS http://127.0.0.1:8080/healthz 2>/dev/null; then \
			echo "flow-ui ready at http://127.0.0.1:8080 (collector is optional)"; exit 0; \
		fi; \
		attempt=$$((attempt + 1)); sleep 2; \
	done; \
	echo "flow-ui did not become ready at http://127.0.0.1:8080/healthz" >&2; \
	docker compose logs flow-ui; exit 1

down-ui:             ## Stop only flow-ui
	docker compose stop flow-ui

e2e: up init generate ## Full configurable pipeline (up + init + generate)
	@echo "E2E complete with the Rust collector. Inspect at http://localhost:8123/play"

ps:                  ## Show running services
	docker compose ps

logs:                ## Tail the Rust collector's logs
	docker compose logs -f collector-rust

down:                ## Stop all services
	docker compose down

reset:               ## Stop all services and drop volumes (fresh ClickHouse)
	docker compose down -v

# ── build / test / lint (all run in Docker; no host toolchains needed) ──

build:               ## Build all service images (generator + Rust collector)
	docker compose build

test: test-generator test-collector-rust test-flow-ui  ## Run all unit test suites

test-silver:            ## Verify Bronze→Silver load and Silver read-model invariants
	docker compose exec -T clickhouse clickhouse-client --multiquery < infra/clickhouse/tests/02-silver-layer.test.sql
	@# call_edges_1m is fed by a REFRESH EVERY 1 MINUTE view, so a freshly migrated
	@# database has an empty table until the first scheduled run. Refreshing here is
	@# what makes T29's assertions non-vacuous — the test file asserts non-emptiness
	@# first for exactly that reason.
	docker compose exec -T clickhouse clickhouse-client -q "SYSTEM REFRESH VIEW silver.call_edges_1m_rmv"
	docker compose exec -T clickhouse clickhouse-client -q "SYSTEM WAIT VIEW silver.call_edges_1m_rmv"
	docker compose exec -T clickhouse clickhouse-client --multiquery < infra/clickhouse/tests/03-watcher-models.test.sql

sample-silver:          ## Print representative rows from the Silver models
	docker compose exec -T clickhouse clickhouse-client --multiquery --format PrettyCompact < infra/clickhouse/queries/03-watcher-sample.sql

test-generator-integration:  ## Generator integration suite against a LIVE ClickHouse (needs `make up`)
	@cid=$$(docker compose ps -q clickhouse); \
	if [ -z "$$cid" ]; then \
		echo "test-generator-integration: no running 'clickhouse' service."; \
		echo "  This suite targets the ClickHouse named by CLICKHOUSE_URL and starts none of its"; \
		echo "  own (REQ-B-11, SPEC §9). Run 'make up' first."; \
		exit 1; \
	fi; \
	docker run --rm --user $$(id -u):$$(id -g) -v "$(CURDIR)":/w \
		-w /w/services/generator-python -e HOME=/tmp -e CONTRACTS_DIR=/w/contracts/generator/v1 \
		--network "container:$$cid" -e CLICKHOUSE_URL=http://localhost:8123 \
		$(PYTHON_IMAGE) bash -c "python -m venv /tmp/v && /tmp/v/bin/pip -q install -e . pytest && /tmp/v/bin/python -m pytest tests/integration -q"

test-generator:      ## Generator unit tests (pytest)
	$(DK_RUN) -w /w/services/generator-python -e HOME=/tmp -e CONTRACTS_DIR=/w/contracts/generator/v1 \
		$(PYTHON_IMAGE) bash -c "python -m venv /tmp/v && /tmp/v/bin/pip -q install -e . pytest jsonschema && /tmp/v/bin/python -m pytest tests/unit -q"

test-collector-rust: ## Rust collector tests (cargo test; live-ClickHouse tests are #[ignore]d)
	$(DK_RUN) -w /w/services/collector-rust -e CARGO_HOME=/tmp/cargo -e HOME=/tmp \
		rust:1.96 cargo test --locked

lint: lint-generator lint-collector-rust lint-flow-ui  ## Lint all services

test-flow-ui:        ## flow-ui unit tests (pytest)
	$(DK_RUN) -w /w/services/flow-ui -e HOME=/tmp \
		$(PYTHON_IMAGE) bash -c "python -m venv /tmp/v && /tmp/v/bin/pip -q install -e . pytest && /tmp/v/bin/python -m pytest tests -q"

lint-flow-ui:        ## flow-ui lint (ruff)
	$(DK_RUN) -w /w/services/flow-ui ghcr.io/astral-sh/ruff:latest check src tests scripts

lint-generator:      ## Python lint (ruff)
	$(DK_RUN) -w /w/services/generator-python ghcr.io/astral-sh/ruff:latest check src

audit-python:        ## Python advisories + static security scan (prints findings; non-zero if any)
	@$(DK_RUN) -w /w -e HOME=/tmp $(PYTHON_IMAGE) bash -c '\
		python -m venv /tmp/v >/dev/null && \
		/tmp/v/bin/pip -q install pip-audit bandit && \
		echo "── pip-audit: generator ──" && \
		/tmp/v/bin/pip-audit --progress-spinner off --desc on services/generator-python; \
		echo "── pip-audit: flow-ui ──" && \
		/tmp/v/bin/pip-audit --progress-spinner off --desc on services/flow-ui; \
		echo "── bandit: shipped sources ──" && \
		/tmp/v/bin/bandit -q -r services/generator-python/src services/flow-ui/src'

lint-collector-rust: ## Rust fmt check + clippy
	$(DK_RUN) -w /w/services/collector-rust -e CARGO_HOME=/tmp/cargo -e HOME=/tmp \
		rust:1.96 bash -c "cargo fmt --check && cargo clippy --locked -- -D warnings"
