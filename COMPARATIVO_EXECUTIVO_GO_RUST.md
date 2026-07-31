# Comparativo executivo — Go × Rust

## Objetivo

Comparar os coletores Go e Rust após a equalização do pipeline de ingestão OTLP → ClickHouse, usando o mesmo cenário, volume, schema, batch e critérios de validação.

## Resumo da decisão

**Recomendação: Rust para o coletor de carga sustentada.**

Após os ajustes, Go e Rust atingiram empate técnico de performance na carga de 5 minutos. Rust apresentou pequena vantagem de throughput, menor consumo de memória, menos parts no ClickHouse e melhor compressão.

Go continua sendo uma boa escolha quando simplicidade de desenvolvimento, onboarding e menor latência em bursts curtos são as prioridades.

## Ambiente do teste

- Cenário: `baseline`, seed `42`.
- Volume de 1m: 46.620 sinais.
- Volume de 5m: 233.100 sinais.
- Repetições: 3 por coletor e janela.
- Total: 12 execuções.
- Batch: 1.000 linhas por destino.
- Flush: 500 ms.
- Destino: schema bronze `sentinel.*`.
- ClickHouse: container limitado a 4 GiB.
- Medição: tempo até todas as linhas estarem consultáveis.
- Merges congelados durante a ingestão.

## Ajustes realizados

### Correção e confiabilidade

- Enqueue atômico: o RPC inteiro é aceito ou rejeitado.
- `partial_success` para sinais rejeitados pela validação `strict`.
- Validação fail-fast de batch, flush, target e configurações inválidas.
- Métricas separadas para received, accepted, rejected, persisted e dropped.
- Retry Go com jitter, cancelamento e drain seguro no shutdown.

### Equalização de performance

- Mesmo destino, schema, batch e intervalo de flush.
- Rust passou a acumular batch por tabela de destino.
- Inserts Rust independentes passaram a executar concorrentemente.
- Removido `async_insert + wait_for_async_insert`, principal gargalo do Rust.
- Logs por RPC movidos de `INFO` para `DEBUG`.
- Buckets Prometheus ajustados para batches de 1.000 ou mais.

### Segurança e operação

- Go passou a executar como usuário nonroot.
- Rust permanece em imagem estática distroless/nonroot.
- O benchmark passou a registrar CPU, memória, OOM, parts, compressão e resultados individuais.

## Resultado antes dos ajustes

Carga de 5 minutos — 233.100 sinais:

| Coletor | Tempo | Throughput | Resultado |
|---|---:|---:|---|
| Go | 5,187 s | 44.939 sinais/s | Referência inicial |
| Rust | 54,169 s | 4.304 sinais/s | 10,44× mais lento |

O resultado anterior era dominado por diferenças de exporter: batches mistos menores, inserts HTTP sequenciais e espera do `async_insert` no Rust.

## Resultado após os ajustes

### Carga curta — 1 minuto

| Métrica | Go | Rust | Melhor |
|---|---:|---:|---|
| Tempo E2E | 1,459 s | 1,756 s | Go |
| Throughput | 31.953/s | 26.549/s | Go |
| Memória do coletor | 37,21 MiB | 6,98 MiB | Rust |
| Parts | 90 | 85 | Rust |
| Compressão | 7,78× | 19,19× | Rust |

Go foi 20,4% mais rápido no burst curto.

### Carga sustentada — 5 minutos

| Métrica | Go | Rust | Melhor |
|---|---:|---:|---|
| Tempo E2E | 4,905 s | 4,683 s | Rust |
| Throughput | 47.523/s | 49.776/s | Rust |
| Memória do coletor | 44,05 MiB | 13,61 MiB | Rust |
| Pico de CPU do coletor | 32,44% | 28,10% | Rust |
| Parts | 447 | 415 | Rust |
| Compressão | 7,78× | 19,17× | Rust |
| Linhas persistidas | 100% | 100% | Empate |
| OOM | 0 | 0 | Empate |

Na carga sustentada, Rust apresentou:

- 4,7% mais throughput;
- 4,5% menos tempo E2E;
- 69,1% menos memória no coletor;
- 13,4% menos pico de CPU amostrado;
- 7,2% menos parts;
- 2,46× mais compressão.

## Comparação técnica

| Critério | Go | Rust |
|---|---|---|
| Performance sustentada | Muito boa | Muito boa, pequena vantagem |
| Burst curto | Melhor | Bom |
| Memória | Maior | Muito menor |
| Segurança de memória | Runtime/GC | Garantias em compilação, sem GC |
| Concorrência | Goroutines e channels simples | Tokio e tipos mais rigorosos |
| Build | Mais rápido e simples | Mais lento e complexo |
| Imagem | Alpine nonroot | Distroless estática nonroot |
| Manutenção | Curva menor | Curva maior |
| Storage | Mais parts e menor compressão | Menos parts e maior compressão |
| Ecossistema | Amplo e acessível | Forte em segurança e eficiência |

## Benefícios de Go

- Desenvolvimento e onboarding mais simples.
- Builds rápidos.
- Ecossistema maduro para OTel e ClickHouse.
- Melhor resultado em bursts curtos.
- Modelo de concorrência fácil de operar e modificar.

## Benefícios de Rust

- Melhor eficiência em carga sustentada.
- Consumo de memória significativamente menor.
- Sem garbage collector.
- Segurança de memória e concorrência em compilação.
- Menor superfície de ataque com distroless/nonroot.
- Menos parts e melhor compressão no ClickHouse.

## Recomendação

### Escolha principal: Rust

Usar Rust para o coletor principal quando os objetivos forem:

- ingestão contínua e sustentada;
- eficiência de memória;
- segurança e previsibilidade operacional;
- menor custo de storage;
- execução em ambientes com recursos limitados.

### Quando escolher Go

Go continua recomendado quando os objetivos forem:

- entrega e evolução rápidas;
- equipe com maior experiência em Go;
- menor complexidade de manutenção;
- workloads predominantemente curtos ou intermitentes.

## Conclusão

Os ajustes eliminaram o gargalo do Rust e transformaram uma diferença de 10,44× contra Rust em empate técnico, com vantagem do Rust na carga sustentada e na eficiência operacional.

Para o perfil do Sentinel — coletor de telemetria contínuo, crítico e de longa duração — **Rust oferece o melhor equilíbrio entre performance, memória, segurança e eficiência de armazenamento**.

## Observação sobre entrega

Nos dois coletores, o ack OTLP confirma aceitação no pipeline em memória. Persistência durável por RPC exigiria WAL ou fila persistente. Persistências e drops são expostos por métricas operacionais.

## Evidências

- `bakeoff.json`: medianas consolidadas.
- `bakeoff-runs.jsonl`: resultados das 12 execuções.
- `ANALISE_PERFORMANCE_GO_RUST.md`: análise técnica completa.
