# Sentinel monorepo — configurable end-to-end pipeline.
#
# Choose which collector runs with COLLECTOR (rust | go); default rust.
#   make e2e                  # full pipeline with the Rust collector
#   make e2e COLLECTOR=go     # full pipeline with the Go collector
#   make up / init / generate / down / reset / logs
#
# The selected collector owns OTLP :4317 and its OWN ClickHouse schema
# (schemas are intentionally NOT reconciled — see docs/clickhouse-schema-divergence.md).

COLLECTOR ?= rust
SCENARIO  ?= baseline
SEED      ?= 42
WINDOW    ?= 5m
export COMPOSE_PROFILES = $(COLLECTOR)

VALID_COLLECTORS := rust go

.PHONY: help guard up init generate e2e down reset logs ps \
        build test test-generator test-collector-rust test-collector-go \
        lint lint-generator lint-collector-rust lint-collector-go

# Docker runner for per-service build/test/lint — no host toolchains required.
DK_RUN := docker run --rm --user $(shell id -u):$(shell id -g) -v "$(CURDIR)":/w

help:                ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  COLLECTOR=$(COLLECTOR)  SCENARIO=$(SCENARIO)  SEED=$(SEED)  WINDOW=$(WINDOW)"

guard:               ## Validate COLLECTOR is one of: rust | go
	@echo "$(VALID_COLLECTORS)" | tr ' ' '\n' | grep -qx "$(COLLECTOR)" || \
		{ echo "ERROR: COLLECTOR='$(COLLECTOR)' invalid. Use one of: $(VALID_COLLECTORS)"; exit 1; }

up: guard            ## Start ClickHouse + the selected collector
	docker compose up -d --build clickhouse collector-$(COLLECTOR)

init: guard          ## No-op: the canonical bronze schema auto-applies on ClickHouse boot (both collectors)
	@echo "$(COLLECTOR) → canonical bronze schema (bronze.*) auto-applies on ClickHouse boot via infra/clickhouse/init.d/; nothing to apply"

generate: guard      ## Run the generator → OTLP :4317 (SCENARIO / SEED / WINDOW configurable)
	docker compose run --rm generator \
		--scenario $(SCENARIO) --seed $(SEED) --window $(WINDOW) \
		--delivery otlp --otlp-endpoint http://collector:4317

e2e: up init generate ## Full configurable pipeline (up + init + generate)
	@echo "E2E complete with COLLECTOR=$(COLLECTOR). Inspect at http://localhost:8123/play"

ps: guard            ## Show running services
	docker compose ps

logs: guard          ## Tail the selected collector's logs
	docker compose logs -f collector-$(COLLECTOR)

down:                ## Stop all services (both profiles)
	COMPOSE_PROFILES=rust,go docker compose down

reset:               ## Stop all services and drop volumes (fresh ClickHouse)
	COMPOSE_PROFILES=rust,go docker compose down -v

# ── build / test / lint (all run in Docker; no host cargo/go/python needed) ──

build:               ## Build all service images (generator + both collectors)
	COMPOSE_PROFILES=rust,go docker compose build

test: test-generator test-collector-rust test-collector-go  ## Run all unit test suites

test-generator:      ## Generator unit tests (pytest)
	$(DK_RUN) -w /w/services/generator-python -e HOME=/tmp -e CONTRACTS_DIR=/w/contracts/generator/v1 \
		python:3.12-slim bash -c "python -m venv /tmp/v && /tmp/v/bin/pip -q install -e . pytest jsonschema && /tmp/v/bin/python -m pytest tests/unit -q"

test-collector-rust: ## Rust collector tests (cargo test; live-ClickHouse tests are #[ignore]d)
	$(DK_RUN) -w /w/services/collector-rust -e CARGO_HOME=/tmp/cargo -e HOME=/tmp \
		rust:1.96 cargo test --locked

test-collector-go:   ## Go collector unit tests (go test)
	$(DK_RUN) -w /w/services/collector-go -e GOMODCACHE=/tmp/gomod -e GOCACHE=/tmp/gocache -e HOME=/tmp \
		golang:1.21 go test ./...

lint: lint-generator lint-collector-rust lint-collector-go  ## Lint all services

lint-generator:      ## Python lint (ruff)
	$(DK_RUN) -w /w/services/generator-python ghcr.io/astral-sh/ruff:latest check src

lint-collector-rust: ## Rust fmt check + clippy
	$(DK_RUN) -w /w/services/collector-rust -e CARGO_HOME=/tmp/cargo -e HOME=/tmp \
		rust:1.96 bash -c "cargo fmt --check && cargo clippy --locked"

lint-collector-go:   ## Go vet
	$(DK_RUN) -w /w/services/collector-go -e GOMODCACHE=/tmp/gomod -e GOCACHE=/tmp/gocache -e HOME=/tmp \
		golang:1.21 go vet ./...
