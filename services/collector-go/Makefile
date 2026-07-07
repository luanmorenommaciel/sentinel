GO     := CGO_ENABLED=0 GOTOOLCHAIN=local /usr/local/go/bin/go
DOCKER := docker compose

.PHONY: build test vet sender sender-hyperdx up down reset logs logs-hyperdx

build:
	$(GO) build ./...

test:
	$(GO) test ./... -v -timeout 30s

vet:
	$(GO) vet ./...

# Envia span/log/metric para o collector → sentinel ClickHouse
sender:
	$(GO) run ./cmd/sender

# Envia span/log/metric direto para o HyperDX :4316 → aparece no UI em :8000
sender-hyperdx:
	$(GO) run ./cmd/sender localhost:4316

up:
	$(DOCKER) up --build

down:
	$(DOCKER) down

reset:
	$(DOCKER) down -v

logs:
	$(DOCKER) logs -f collector

logs-hyperdx:
	$(DOCKER) logs -f hyperdx
