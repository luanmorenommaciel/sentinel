# ClickHouse Schema Divergence — Rust vs Go (estado final)

> **SUPERSEDED (2026-07-21) por [ADR-0007](adr/0007-bronze-canonical-contract.md).**
> Este documento registra a reconciliação do schema *normalizado* `default.*` (2026-06-16),
> quando ambos os collectors passaram a escrever o mesmo DDL no database `default`. Esse
> caminho foi **aposentado**: os dois collectors agora escrevem o schema **bronze** split
> (OTel-contrib) diretamente no database `bronze` (`bronze.otel_logs` / `otel_traces` /
> `otel_metrics_gauge` / `otel_metrics_sum`), com equivalência verificada. As referências a
> `default.*` e ao MV `otel_metrics_1m` abaixo são **históricas**. Mantido para registro.

**Data:** 2026-06-16  
**Branch:** `feat/02-otel-collector-go`  
**Propósito:** Comparação coluna a coluna após a normalização completa do POD 2.
Serve como referência de estado final antes do POD 3 (modelo canônico).

Fontes:
- Rust — `services/collector-rust/infra/clickhouse/ddl/00{1,2,3}_*.sql`
- Go   — `services/collector-go/migrations/001_init_schema.sql`

---

## Resultado: schemas idênticos

Todas as 10 divergências documentadas em
[clickhouse-schema-divergence3.md](clickhouse-schema-divergence3.md) foram
resolvidas. Os dois collectors agora escrevem no mesmo database (`default`) com
o mesmo DDL estrutural.

---

## otel_logs

| # | Coluna | Tipo | Codec | Rust | Go |
|---|--------|------|-------|------|----|
| 1 | `Timestamp` | `DateTime64(9, 'UTC')` | `Delta, ZSTD(1)` | ✓ | ✓ |
| 2 | `ServiceName` | `LowCardinality(String)` | — | ✓ | ✓ |
| 3 | `SentinelScenario` | `LowCardinality(String)` | — | ✓ | ✓ |
| 4 | `SentinelRunId` | `LowCardinality(String)` | — | ✓ | ✓ |
| 5 | `CloudProvider` | `LowCardinality(String)` | — | ✓ | ✓ |
| 6 | `SentinelSynthetic` | `UInt8` | — | ✓ | ✓ |
| 7 | `SeverityText` | `LowCardinality(String)` | — | ✓ | ✓ |
| 8 | `SeverityNumber` | `Int32` | `Delta, ZSTD(1)` | ✓ | ✓ |
| 9 | `Body` | `String` | `ZSTD(1)` | ✓ | ✓ |
| 10 | `TraceId` | `String` | — | ✓ | ✓ |
| 11 | `SpanId` | `String` | — | ✓ | ✓ |
| 12 | `ContractVersion` | `LowCardinality(String)` | — | ✓ | ✓ |
| 13 | `LogAttributes` | `Map(String, String)` | — | ✓ | ✓ |
| 14 | `ResourceAttributes` | `Map(String, String)` | — | ✓ | ✓ |

| Parâmetro | Rust | Go |
|-----------|------|----|
| Engine | `MergeTree` | `MergeTree` |
| PARTITION BY | `toDate(Timestamp)` | `toDate(Timestamp)` |
| ORDER BY | `(ServiceName, Timestamp, TraceId)` | `(ServiceName, Timestamp, TraceId)` |
| TTL | `toDate(Timestamp) + INTERVAL 30 DAY` | `toDate(Timestamp) + INTERVAL 30 DAY` |
| `index_granularity` | `8192` | `8192` |

**Divergências: nenhuma.**

---

## otel_traces

| # | Coluna | Tipo | Codec | Rust | Go |
|---|--------|------|-------|------|----|
| 1 | `Timestamp` | `DateTime64(9, 'UTC')` | `Delta, ZSTD(1)` | ✓ | ✓ |
| 2 | `TraceId` | `String` | — | ✓ | ✓ |
| 3 | `SpanId` | `String` | — | ✓ | ✓ |
| 4 | `ParentSpanId` | `String` | — | ✓ | ✓ |
| 5 | `SpanName` | `LowCardinality(String)` | — | ✓ | ✓ |
| 6 | `ServiceName` | `LowCardinality(String)` | — | ✓ | ✓ |
| 7 | `SentinelScenario` | `LowCardinality(String)` | — | ✓ | ✓ |
| 8 | `SentinelRunId` | `LowCardinality(String)` | — | ✓ | ✓ |
| 9 | `CloudProvider` | `LowCardinality(String)` | — | ✓ | ✓ |
| 10 | `SentinelSynthetic` | `UInt8` | — | ✓ | ✓ |
| 11 | `Duration` | `Int64` | `Delta, ZSTD(1)` | ✓ | ✓ |
| 12 | `StatusCode` | `LowCardinality(String)` | — | ✓ | ✓ |
| 13 | `ContractVersion` | `LowCardinality(String)` | — | ✓ | ✓ |
| 14 | `SpanAttributes` | `Map(String, String)` | — | ✓ | ✓ |
| 15 | `ResourceAttributes` | `Map(String, String)` | — | ✓ | ✓ |

| Parâmetro | Rust | Go |
|-----------|------|----|
| Engine | `MergeTree` | `MergeTree` |
| PARTITION BY | `toDate(Timestamp)` | `toDate(Timestamp)` |
| ORDER BY | `(ServiceName, Timestamp, TraceId)` | `(ServiceName, Timestamp, TraceId)` |
| TTL | `toDate(Timestamp) + INTERVAL 30 DAY` | `toDate(Timestamp) + INTERVAL 30 DAY` |
| `index_granularity` | `8192` | `8192` |

**Divergências: nenhuma.**

---

## otel_metrics

| # | Coluna | Tipo | Codec | Rust | Go |
|---|--------|------|-------|------|----|
| 1 | `Timestamp` | `DateTime64(9, 'UTC')` | `Delta, ZSTD(1)` | ✓ | ✓ |
| 2 | `MetricName` | `LowCardinality(String)` | — | ✓ | ✓ |
| 3 | `MetricType` | `LowCardinality(String)` | — | ✓ | ✓ |
| 4 | `Value` | `Float64` | `ZSTD(1)` | ✓ | ✓ |
| 5 | `ServiceName` | `LowCardinality(String)` | — | ✓ | ✓ |
| 6 | `SentinelScenario` | `LowCardinality(String)` | — | ✓ | ✓ |
| 7 | `SentinelRunId` | `LowCardinality(String)` | — | ✓ | ✓ |
| 8 | `CloudProvider` | `LowCardinality(String)` | — | ✓ | ✓ |
| 9 | `SentinelSynthetic` | `UInt8` | — | ✓ | ✓ |
| 10 | `ContractVersion` | `LowCardinality(String)` | — | ✓ | ✓ |
| 11 | `Attributes` | `Map(String, String)` | — | ✓ | ✓ |
| 12 | `ResourceAttributes` | `Map(String, String)` | — | ✓ | ✓ |

| Parâmetro | Rust | Go |
|-----------|------|----|
| Engine | `MergeTree` | `MergeTree` |
| PARTITION BY | `toDate(Timestamp)` | `toDate(Timestamp)` |
| ORDER BY | `(ServiceName, MetricName, Timestamp)` | `(ServiceName, MetricName, Timestamp)` |
| TTL | `toDate(Timestamp) + INTERVAL 90 DAY` | `toDate(Timestamp) + INTERVAL 90 DAY` |
| `index_granularity` | `8192` | `8192` |

**Divergências: nenhuma.**

---

## otel_metrics_1m + otel_metrics_1m_mv

| # | Coluna | Tipo | Rust | Go |
|---|--------|------|------|----|
| 1 | `window_start` | `DateTime` | ✓ | ✓ |
| 2 | `ServiceName` | `LowCardinality(String)` | ✓ | ✓ |
| 3 | `MetricName` | `LowCardinality(String)` | ✓ | ✓ |
| 4 | `SentinelScenario` | `LowCardinality(String)` | ✓ | ✓ |
| 5 | `count` | `SimpleAggregateFunction(sum, UInt64)` | ✓ | ✓ |
| 6 | `sum_val` | `SimpleAggregateFunction(sum, Float64)` | ✓ | ✓ |
| 7 | `sum_sq` | `SimpleAggregateFunction(sum, Float64)` | ✓ | ✓ |
| 8 | `min_val` | `SimpleAggregateFunction(min, Float64)` | ✓ | ✓ |
| 9 | `max_val` | `SimpleAggregateFunction(max, Float64)` | ✓ | ✓ |

| Parâmetro | Rust | Go |
|-----------|------|----|
| Engine | `AggregatingMergeTree` | `AggregatingMergeTree` |
| PARTITION BY | `toDate(window_start)` | `toDate(window_start)` |
| ORDER BY | `(ServiceName, MetricName, SentinelScenario, window_start)` | `(ServiceName, MetricName, SentinelScenario, window_start)` |
| TTL | `toDate(window_start) + INTERVAL 90 DAY` | `toDate(window_start) + INTERVAL 90 DAY` |
| `index_granularity` | `8192` | `8192` |
| MV `FROM` | `otel_metrics` | `otel_metrics` |
| MV `TO` | `otel_metrics_1m` | `otel_metrics_1m` |
| MV projeção | `toStartOfMinute`, `count()`, `sum`, `min`, `max` | idem |

**Divergências: nenhuma.**

---

## Resumo

| Dimensão | Estado |
|----------|--------|
| Database | `default` — idêntico |
| Tabelas presentes | `otel_logs`, `otel_traces`, `otel_metrics`, `otel_metrics_1m`, MV `otel_metrics_1m_mv` — idêntico |
| Colunas (nome, tipo, codec, ordem) | Idênticas em todas as 4 tabelas |
| ENGINE | `MergeTree` / `AggregatingMergeTree` — idêntico |
| PARTITION BY | `toDate(Timestamp)` / `toDate(window_start)` — idêntico |
| ORDER BY | Idêntico por sinal |
| TTL (âncora + intervalo) | `toDate(Timestamp)` 30d logs/traces, 90d metrics — idêntico |
| `index_granularity` | `8192` — idêntico |
| Skip indexes | Nenhum em ambos |
| `ttl_only_drop_parts` | Não definido em ambos |
| Map key type | `Map(String, String)` em ambos |

**Nenhuma divergência estrutural restante.** Os dois collectors são substituíveis
um pelo outro do ponto de vista do schema ClickHouse. A única diferença é a
linguagem de implementação (Rust vs Go) e seus respectivos detalhes de
deployment.
