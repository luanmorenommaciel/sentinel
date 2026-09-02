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

.PHONY: help up init generate generate-stream ui e2e down reset logs ps \
        build test test-generator test-collector-rust test-flow-ui \
        test-silver sample-silver lint lint-generator lint-collector-rust lint-flow-ui

# Docker runner for per-service build/test/lint — no host toolchains required.
DK_RUN := docker run --rm --user $(shell id -u):$(shell id -g) -v "$(CURDIR)":/w

help:                ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  SCENARIO=$(SCENARIO)  SEED=$(SEED)  WINDOW=$(WINDOW)"
	@echo "  DURATION=$(DURATION)  STEP=$(STEP)  RATE=$(RATE)   (generate-stream)"

up:                  ## Start ClickHouse + the Rust collector
	docker compose up -d --build clickhouse collector-rust

init:                ## No-op: the canonical bronze schema auto-applies on ClickHouse boot
	@echo "Rust → canonical bronze schema (bronze.*) auto-applies on ClickHouse boot via infra/clickhouse/init.d/; nothing to apply"

generate:            ## Run the generator → OTLP :4317 (SCENARIO / SEED / WINDOW configurable)
	docker compose run --rm generator \
		--scenario $(SCENARIO) --seed $(SEED) --window $(WINDOW) \
		--delivery otlp --otlp-endpoint http://collector:4317

generate-stream:     ## Generate in real time (paced by wall clock) — DURATION / STEP / RATE
	docker compose run --rm generator \
		--mode stream --duration $(DURATION) --step $(STEP) --rate $(RATE) \
		--scenario $(SCENARIO) --seed $(SEED) \
		--delivery otlp --otlp-endpoint http://collector:4317

ui:                  ## Start the flow visualizer on http://localhost:8080
	docker compose up -d --build flow-ui
	@echo "flow-ui → http://localhost:8080"

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

sample-silver:          ## Print representative rows from the Silver models
	docker compose exec -T clickhouse clickhouse-client --multiquery --format PrettyCompact < infra/clickhouse/queries/02-silver-sample.sql

test-generator:      ## Generator unit tests (pytest)
	$(DK_RUN) -w /w/services/generator-python -e HOME=/tmp -e CONTRACTS_DIR=/w/contracts/generator/v1 \
		python:3.12-slim bash -c "python -m venv /tmp/v && /tmp/v/bin/pip -q install -e . pytest jsonschema && /tmp/v/bin/python -m pytest tests/unit -q"

test-collector-rust: ## Rust collector tests (cargo test; live-ClickHouse tests are #[ignore]d)
	$(DK_RUN) -w /w/services/collector-rust -e CARGO_HOME=/tmp/cargo -e HOME=/tmp \
		rust:1.96 cargo test --locked

lint: lint-generator lint-collector-rust lint-flow-ui  ## Lint all services

test-flow-ui:        ## flow-ui unit tests (pytest)
	$(DK_RUN) -w /w/services/flow-ui -e HOME=/tmp \
		python:3.12-slim bash -c "python -m venv /tmp/v && /tmp/v/bin/pip -q install -e . pytest && /tmp/v/bin/python -m pytest tests -q"

lint-flow-ui:        ## flow-ui lint (ruff)
	$(DK_RUN) -w /w/services/flow-ui ghcr.io/astral-sh/ruff:latest check src tests scripts

lint-generator:      ## Python lint (ruff)
	$(DK_RUN) -w /w/services/generator-python ghcr.io/astral-sh/ruff:latest check src

lint-collector-rust: ## Rust fmt check + clippy
	$(DK_RUN) -w /w/services/collector-rust -e CARGO_HOME=/tmp/cargo -e HOME=/tmp \
		rust:1.96 bash -c "cargo fmt --check && cargo clippy --locked"
