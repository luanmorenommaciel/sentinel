# Por que a bronze separa métricas por tipo (resumo para reunião)

> **Não é uma decisão nova.** Distila a decisão já registrada em
> [ADR-0007](../adr/0007-bronze-canonical-contract.md) para apresentação.
> Status: ADR-0007 **Proposed** — Rust já alinhado, **Go pendente** (a mudança em pauta).
> Data: 2026-07-20.

## TL;DR

- **A decisão já existe:** bronze = schema do **otel-collector-contrib v0.105.0**
  (`sentinel.*`), com métricas **separadas por tipo** (`otel_metrics_gauge`,
  `_sum`, `_histogram`, `_exponential_histogram`, `_summary`). Fonte: ADR-0007.
- **O Rust já escreve assim** — evidência na ADR-0007: generator → collector →
  `sentinel.*` landa ~40.200 logs / 40.200 traces / 152.700 métricas
  (gauge 83.400 + sum 69.300), lossless.
- **A mudança em pauta = alinhar o Go** à bronze. A própria ADR-0007 deixou isso
  como *"separate task"* (Next steps, item 4). Não é proposta nova; é execução.

## O que muda no Go

| | Go hoje (`default.*`) | Bronze (alvo, = Rust) |
|---|---|---|
| Database | `default` (fallback do ClickHouse) | `sentinel` |
| Métricas | **1 tabela** `otel_metrics` (`MetricType` + `Value`) | **tabela por tipo** (`otel_metrics_gauge`, `_sum`, …) |
| Exporter | caminho normalizado (`chstore/*.go`) | exporter bronze **que já existe no Go** (`clickhouse_exporter.go`, hoje dormente) |

## Por que separar por tipo (o núcleo da justificativa)

Os 5 tipos de métrica do OTel têm **formatos diferentes**:

| Tipo | Formato |
|---|---|
| gauge / sum | um número → cabe em `Value Float64` |
| histogram | contagem por bucket + limites (arrays) |
| exponential histogram | escala + arrays de buckets |
| summary | arrays de quantis |

**Exemplo concreto** — 3 métricas chegando:

*Tabela única (jeito do Go hoje):*

| MetricName | MetricType | Value |
|---|---|---|
| cpu.utilization | gauge | `0.73` |
| requests.total | sum | `1500` |
| request.duration | histogram | `???` ❌ |

O histogram **não é um número** — são buckets `[10,40,30,20]` + limites
`[50,100,200]`. Não cabe numa coluna `Value`. Tabela única só funciona com
gauge/sum (limitação que trava o dia que aparecer histogram).

*Tabelas por tipo (bronze):* cada tipo ganha as colunas que precisa —
`otel_metrics_histogram` tem `Count`, `Sum`, `BucketCounts`, `ExplicitBounds`;
`otel_metrics_gauge` não carrega colunas vazias.

## "Isso não dá mais processamento?" — Não

O **OTLP** (o que chega no `:4317`) já entrega a métrica **tipada** — no protobuf
cada métrica é um `oneof`: Gauge / Sum / Histogram / … O tipo **já vem pronto no dado**.

- **Bronze (por tipo):** um `match` no tipo que já veio → roteia pra tabela certa. Praticamente de graça.
- **Tabela única:** precisa **achatar** a estrutura tipada num formato genérico e
  **descartar** o que não cabe. Isso é trabalho *extra* — e com perda de informação.

Ou seja: por-tipo é o formato **mais fiel ao que chega**. Quem transforma (e perde
dado) é a tabela única.

## Trade-off honesto (direto da ADR-0007)

- **Contra:** os 5 campos Sentinel (`sentinel.scenario`, `run_id`, `cloud.provider`, …)
  saem de colunas tipadas e vão pra dentro de `Map(...)` → filtrar por eles vira um
  *Map probe* em vez de hit de índice primário. Recuperável como *materialized columns*
  na **silver**, se a latência dos Watchers exigir. `ServiceName` mantém coluna tipada.
- **A favor:** um schema **canônico, padrão da comunidade, versionado, com dono claro
  (Pod 3)**; exporter mais simples; e um futuro move pra ClickStack vira adoção, não migração.

## Enquadramento medallion

- **Bronze** = landing cru, fiel ao OTel (tabelas por tipo). ← esta decisão.
- **Silver** = schema normalizado/enriquecido (colunas hoistadas, `otel_metrics_1m`).
  O rollup `otel_metrics_1m` que o normalizado tinha vira artefato de silver (ADR-0007).

## Referências

- [ADR-0007](../adr/0007-bronze-canonical-contract.md) — a decisão canônica (supersede ADR-0005)
- [pod3-bronze-gap.md](pod3-bronze-gap.md) — análise de gap + evidência do round-trip
- [`infra/clickhouse/init.d/01-bronze-otel.sql`](../../infra/clickhouse/init.d/01-bronze-otel.sql) — DDL da bronze (contrib v0.105.0)
- [`services/collector-rust/src/clickhouse_exporter.rs`](../../services/collector-rust/src/clickhouse_exporter.rs) — exporter Rust já alinhado
