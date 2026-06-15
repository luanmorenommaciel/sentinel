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

.PHONY: help guard up init generate e2e down reset logs ps

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

init: guard          ## Apply the SELECTED collector's own ClickHouse DDL
ifeq ($(COLLECTOR),rust)
	cat services/collector-rust/infra/clickhouse/ddl/*.sql | docker compose exec -T clickhouse clickhouse-client -mn
else
	cat services/collector-go/migrations/*.sql            | docker compose exec -T clickhouse clickhouse-client -mn
endif

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
