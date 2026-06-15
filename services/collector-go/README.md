# Sentinel

**Self-Healing Data Pipelines. Autonomous detection, AI-native reasoning, OTel-native by design.**

---

## O que é este projeto

O Sentinel é uma plataforma de pipelines de dados auto-curativos baseada em OpenTelemetry. Este repositório contém o **Pod 2 — OTel Collector Go**: um serviço de alta performance que recebe sinais OTLP/gRPC do Pod 1 (OTelGen Python) e persiste diretamente no ClickHouse.

```
Pod 1 (OTelGen Python)
        │
        │  OTLP/gRPC :4317
        ▼
Pod 2 (Collector Go)   ←── este repositório
        │
        │  Native TCP :9000
        ▼
ClickHouse :9000
  sentinel.otel_spans
  sentinel.otel_logs
  sentinel.otel_metrics
```

---

## Pré-requisitos

| Ferramenta | Versão mínima | Verificar |
|------------|---------------|-----------|
| Go | 1.21.x | `go version` |
| Docker | 24+ | `docker --version` |
| Docker Compose | v2 | `docker compose version` |
| make | qualquer | `make --version` |

> **macOS 15 (Sonoma / Sequoia) + Go 1.21.5**: existe um bug de compatibilidade com `dyld` que impede binários Go com CGO de executarem localmente. **Todos os comandos `go` devem usar `CGO_ENABLED=0`**. O `Makefile` já faz isso automaticamente — use `make` para tudo.

---

## Estrutura do projeto

```
sentinel/
├── cmd/
│   ├── collector/       # Binário principal
│   └── sender/          # Cliente de teste manual
├── internal/
│   ├── config/          # Configuração via env vars
│   ├── model/           # Structs de domínio (Span, Log, Metric)
│   ├── transform/       # OTLP proto → model (puro, sem deps externas)
│   ├── chstore/         # Batch flusher + inserters ClickHouse
│   ├── grpcserver/      # Receivers OTLP gRPC
│   └── httpserver/      # /health e /ready
├── migrations/
│   └── 001_init_schema.sql
├── contract/
│   ├── schema/          # Schema de input (Pod 1)
│   ├── golden/          # Baseline de referência (278 registros)
│   └── output_contract/ # Contrato para o time ClickStack
├── Makefile
├── Dockerfile
└── docker-compose.yml
```

---

## Configuração

Copie o `.env.example` para `.env` (opcional — o docker-compose já tem os defaults):

```bash
cp .env.example .env
```

| Variável | Default | Descrição |
|----------|---------|-----------|
| `GRPC_PORT` | `4317` | Porta OTLP/gRPC |
| `HTTP_PORT` | `8080` | Porta HTTP (health/ready) |
| `CLICKHOUSE_DSN` | `clickhouse://otelgen:otelgen_secret@localhost:9000/sentinel` | DSN nativo TCP |
| `BATCH_SIZE` | `100` | Registros por batch antes do flush |
| `FLUSH_INTERVAL_MS` | `500` | Intervalo máximo de flush em ms |
| `LOG_FORMAT` | `json` | `json` (produção) ou `text` (dev) |

---

## Passo a passo — Subir o ambiente

### 1. Clonar e entrar no diretório

```bash
git clone <repo>
cd sentinel
```

### 2. Compilar e testar localmente

```bash
make build    # compila todos os pacotes
make vet      # análise estática
make test     # roda os 14 testes (unitários + integração gRPC)
```

### 3. Subir o stack completo

```bash
make up
```

O que acontece internamente:
1. Docker constrói a imagem do collector (multi-stage, binário estático)
2. ClickHouse sobe e executa `migrations/001_init_schema.sql` → cria `sentinel.otel_spans`, `sentinel.otel_logs`, `sentinel.otel_metrics`
3. O collector aguarda o ClickHouse passar o healthcheck antes de iniciar
4. gRPC escuta em `:4317`, HTTP em `:8080`

> **Primeira vez:** o init do ClickHouse leva ~15s. Aguarde o log `gRPC server starting` antes de enviar dados.

### 4. Verificar saúde

```bash
curl http://localhost:8080/health   # {"status":"ok"}
curl http://localhost:8080/ready    # {"status":"ready"} — confirma conexão com CH
```

### 5. Enviar dados de teste

```bash
make sender
```

Output esperado:
```
[span]   trace_id=0badc0decafebabe0123456789abcdef  span_id=deadbeefcafe0001  name=sender.test_span
[log]    body="sender integration test — IDs nao sao zero"
[metric] name=sender.test_gauge  type=gauge  value=42.0
```

### 6. Verificar dados no ClickHouse

Abra **http://localhost:8123/play** (user: `otelgen`, senha: `otelgen_secret`):

```sql
-- Spans
SELECT trace_id, span_id, name, service_name, status_code
FROM sentinel.otel_spans
WHERE service_name = 'sender-test';

-- Logs
SELECT trace_id, body, severity_text
FROM sentinel.otel_logs
WHERE service_name = 'sender-test';

-- Métricas
SELECT name, type, value, service_name
FROM sentinel.otel_metrics
WHERE service_name = 'sender-test';
```

### 7. Ver logs em tempo real

```bash
make logs
```

### 8. Parar o stack

```bash
make down     # para, preserva dados no volume
make reset    # para E apaga volumes (reset completo)
```

> Use `make reset` sempre que alterar `migrations/001_init_schema.sql` — o ClickHouse só executa o init script com volume vazio.

---

## Comandos disponíveis

| Comando | Descrição |
|---------|-----------|
| `make build` | Compila todos os pacotes |
| `make test` | 14 testes (unitários + gRPC in-process) |
| `make vet` | Análise estática Go |
| `make sender` | Envia span/log/metric de teste para o collector |
| `make up` | `docker compose up --build` |
| `make down` | Para o stack (preserva dados) |
| `make reset` | Para + apaga volumes |
| `make logs` | Tail dos logs do collector |

---

## Decisões de design e seus motivos

### Por que Go direto ao ClickHouse (sem OTel Collector padrão)?

O OTel Collector padrão (otelcol) adiciona latência de serialização/deserialização e requer configuração YAML extensa. Um receiver Go nativo com `PrepareBatch` do `clickhouse-go/v2` faz um único round-trip TCP por batch, sem overhead de re-serialização.

### Por que canais com buffer + goroutines dedicadas?

O handler gRPC precisa retornar imediatamente para não bloquear o produtor (Pod 1). Os canais (`spanCh`, `logCh`, `metricCh`) desacoplam o recebimento da escrita. O buffer de `batchSize × 4` absorve picos sem back-pressure imediata.

### Por que `flushLoop[T any]` como função genérica?

Go não permite parâmetros de tipo em métodos (`func (s *Store[T]) ...` é inválido). A função livre genérica `flushLoop[T any]` serve para Span, Log e Metric com um único código, sem duplicação.

### Por que `nullableHex` para `ParentSpanID`?

No OTLP, um span raiz tem `parent_span_id` como 8 bytes zero ou ausente. Armazenar `"0000000000000000"` no ClickHouse como string não indica "sem pai" — seria ambíguo em queries. `Nullable(String)` com `nil` é semântico: `IS NULL` = span raiz.

### Por que `go 1.21` no go.mod se o design dizia 1.23?

O sistema tem Go 1.21.5 instalado. A diretiva `go 1.23` no `go.mod` dispara download automático de toolchain (`GOTOOLCHAIN=auto`), que falha em ambiente sem acesso à internet ou sem versão disponível. Fixamos `go 1.21` com `GOTOOLCHAIN=local` para builds reproduzíveis localmente.

### Por que `CGO_ENABLED=0` obrigatório no macOS 15?

macOS 15 (Sonoma/Sequoia) + Go 1.21.5 tem incompatibilidade com o linker: binários com CGO falham com `dyld: missing LC_UUID load command`. Compilar sem CGO (`CGO_ENABLED=0`) produz um binário estático puro Go, sem dependência do runtime C do macOS. O `Makefile` encapsula isso.

### Por que `CREATE DATABASE IF NOT EXISTS sentinel` na migration?

O `docker-entrypoint-initdb.d` do ClickHouse executa o SQL sem contexto de banco padrão. `CREATE TABLE IF NOT EXISTS otel_spans` cria em `default`, não em `sentinel`. Nomes totalmente qualificados (`sentinel.otel_spans`) junto com `CREATE DATABASE IF NOT EXISTS sentinel` garantem que as tabelas fiquem no banco correto independente do contexto de execução.

### Por que interface `Sender` no grpcserver?

O handler gRPC usava `*chstore.Store` diretamente, impossibilitando testes sem ClickHouse real. A interface `Sender` (3 métodos) permite testes in-process com um `captureSender` simples, sem mocks complexos. `*chstore.Store` satisfaz a interface automaticamente — zero impacto no código de produção.

---

## Cobertura de testes

| Pacote | Testes | O que valida |
|--------|--------|--------------|
| `internal/transform` | 9 | OTLP proto → hex string; nil body; status ERROR/OK; nil request |
| `internal/grpcserver` | 5 | IDs não-zero end-to-end via gRPC real; root span nil parent; bytes zero tratados como root; log trace_id; métrica gauge |