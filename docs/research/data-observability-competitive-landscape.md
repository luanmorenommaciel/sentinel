# Data observability — competitive landscape and V2 input

> What the category ships, what users actually use, and where Sentinel already stands on
> ground nobody else occupies.
> *2026-09-01 · Pod 2 · input for the V2 roadmap, not a decision*

**Method.** ~200 web searches and ~40 primary-source fetches across vendor docs, changelogs,
specs, GitHub schemas and analyst summaries. **Coverage is uneven and marked as such** — see
[§7](#7-coverage-ledger). Monte Carlo, Datadog, Grafana, OpenLineage, Elementary and the
OpenTelemetry semconv gap are deep and primary-sourced. Bigeye, Anomalo, Sifflet and Databand
are thin to absent; the search budget ran out. Nothing in those gaps changes the
recommendations, which rest on the high-confidence lanes.

---

## 1. The one paragraph that matters

Gartner's 2026 Market Guide states the category's technical direction as a **shift away from
full-table scans toward "continuous telemetry using metadata, logs, and pipeline signals."**

That is a description of Sentinel's architecture. Every incumbent in this space polls a
warehouse on a schedule; the shift Gartner names is the one they have to make and Sentinel
starts from.

Elementary's own OSS-vs-Cloud table concedes the same thing from the other side:

| | Their OSS | Their Cloud |
|---|---|---|
| Time to detection | **only when dbt runs** | as soon as it happens |
| Cost | **warehouse compute** | metadata only |
| Configuration | **manual, many parameters** | automatic |

They monetise fixing exactly what a stream-fed collector gets for free.

**And the incident data says the boundary is the right place to stand.** From Monte Carlo's
telemetry over 11M+ monitored tables:

| Root cause | Share |
|---|---|
| Pipeline execution faults | **26.2 %** |
| Real-world variation (not an error) | 20.0 % |
| Ingestion disruptions | **16.6 %** |
| Platform instability | 15.2 % |
| Intentional changes / backfills | 14.2 % |
| Schema drift | 7.8 % |

**~43 % of incidents are execution or ingestion faults** — what an ingestion-boundary
collector sees first and a warehouse poller sees last. Monitors are placed at the landing
layer only **34 %** of the time. That mismatch is Sentinel's thesis in one table.

---

## 2. Feature categories, ranked by how universally they ship

| Category | Ships in | Verdict |
|---|---|---|
| Freshness · volume · schema-change · alerting with ownership | 12/12 | **Table stakes** |
| Distribution / column health (null %, uniqueness, min/max) | 11/12 | Table stakes |
| Table-level lineage · custom SQL rules | 10/12 | Table stakes |
| Incident grouping and triage · ML/statistical thresholds | 9/12 | Table stakes at enterprise tier |
| Health / quality scorecards | 8/12 | Rising to table stakes |
| Column-level lineage · monitoring-as-code | 6/12 | Differentiator |
| Job/run execution monitoring · automated RCA | 5/12 | Differentiator |
| Cost/FinOps · SLA + error budgets | 4/12 | Differentiator |
| **Streaming pathway topology + lag** | **2/12** | ⭐ Wide open — Datadog DSM only |
| **Data contracts with runtime enforcement** | **2/12** | ⭐ Wide open |
| **Usage-driven telemetry cost reduction** | **1/12** | ⭐ Wide open — Grafana only |
| **Receive-boundary / shift-left validation** | **~1/12** | ⭐⭐ Empty |

The last four rows are Sentinel's territory. The first five are the entry fee.

---

## 3. The four structural openings

### 3.1 ⭐⭐ Contracts are defined everywhere and enforced almost nowhere

**ODCS v3.1.0** (Linux Foundation, Dec 2025) settled the *definition* format. Enforcement is
another story:

| Tool | Enforcement |
|---|---|
| DataHub OSS | stores contract objects, **no execution engine** |
| datacontract-cli | **translation layer**, CI gate only |
| Confluent Schema Registry | client-side on community licence; broker-side needs Enterprise |
| Redpanda | broker-side WASM transforms — the one real OSS runtime enforcer |
| OpenMetadata 1.9+ | first OSS catalogue to *execute* contracts |

> *"The contract sits in a catalog as documentation. The catalog has no opinion about the
> data flowing past it."*

**Sentinel is already a runtime receive boundary that validates against a versioned contract
and counts violations per signal type and reason.** That is not a roadmap item — it is a
shipped differentiator that is currently invisible because nothing renders it.

### 3.2 ⭐⭐ OpenTelemetry has no data-pipeline semantic conventions

Verified firsthand against the semconv registry: it covers HTTP, Database, Messaging, FaaS,
CI/CD, Object Stores… and **nothing for data pipelines, ETL, data quality, datasets or
lineage.**

Two proposals exist. Both open, `needs-triage`, **zero maintainer response**:

- [semconv#3762](https://github.com/open-telemetry/semantic-conventions/issues/3762) — `pipeline.*`:
  `pipeline.run` span, `pipeline.rows_read/written`, `pipeline.quality.rules_passed/failed`,
  `pipeline.quality.freshness_lag_seconds`
- [semconv#3909](https://github.com/open-telemetry/semantic-conventions/issues/3909) —
  `data.staleness.age / .lag / .records.behind / .sla.*`. Its motivation: *"systems can have
  zero errors and low latency while serving outdated data"* and *"every data-observability
  vendor computes it in a proprietary, siloed way."*

An earlier attempt to make lineage a top-level OTel signal was **closed** in 2024. The nearest
precedent, CI/CD semconv, is at Release Candidate and is a near-mechanical adaptation.

**Aligning Sentinel's attribute names with these costs nothing and buys standards-track
positioning in an empty domain.** Filing on those issues *with a working implementation* is
real open-source leverage.

### 3.3 ⭐ Streaming-time observability is closed-source and OTel-hostile

Datadog's own compatibility matrix: Data Streams Monitoring is **not supported with OTel
SDKs** — *"N/A (OTel does not offer DSM functionality)"*. It requires their tracer and a
proprietary `dd-pathway-ctx` header. **There is no open cross-vendor pathway-context
standard.** Grafana has no equivalent: Tempo's `service_graphs` derives edges from
parent-child spans, which **breaks across an async queue boundary**.

The detection-floor argument is well documented: a warehouse check running every 15 minutes
has a 15-minute detection floor; a streaming check has seconds.

### 3.4 ⭐ OpenLineage has the right payloads, computes nothing, and has no OTLP transport

OpenLineage (LF AI & Data, **Graduated**) already standardises what a detection layer needs:

- **`DataQualityMetricsInputDatasetFacet`** — `rowCount`, `bytes`, `lastUpdated`, plus
  per-column `nullCount`, `distinctCount`, `sum`, `min`, `max`, `quantiles{}`. A ready-made,
  standards-backed input schema for rolling-stats baselines.
- **`DataQualityAssertionsDatasetFacet`** — `{assertion, success, column, severity, expected,
  actual}` where *"a test can fail without blocking the pipeline when severity is 'warn'"* —
  **the same warn/strict split Sentinel already implements at the gRPC boundary.**

But there is **no OTLP transport** (Java transports: Http, Kafka, Console, File, GCS, S3,
Datadog…), and Marquez, the reference UI, has had **no tagged release since 2024-10-24** while
the spec ships biweekly.

Meanwhile the producers already emit OTLP: **dbt Fusion natively** (`--export-to-otlp`,
`trace_id ≡ invocation_id`), Airflow native OTel tracing, Databricks OTLP in beta.

**The bridge is missing exactly where Sentinel stands.**

---

## 3.5 ⭐⭐ El territorio pipeline-céntrico está vacante

*Añadido 2026-09-01 tras cerrar la línea Databand/Soda.*

**Databand era el producto pipeline-céntrico líder, y su marca fue retirada.**
`ibm.com/products/databand` hace **301 → watsonx.data integration**, y esa página de destino
contiene **cero ocurrencias** de la cadena "Databand" (166 KB de HTML, verificado). El dominio
`databand.ai` resuelve al redirector de IBM; el blog entero desapareció. El SDK `dbnd` seguía
publicando en PyPI hasta **2026-03-05**, pero los commits públicos pararon en **marzo 2025** —
el repo de GitHub es un espejo de un GitLab privado que se congeló un año antes que los
paquetes.

> **Matiz que no hay que perder:** *no se encontró carta de retiro formal de soporte*. Las
> páginas de ciclo de vida de IBM siguen sin publicar fecha de EOS (última actualización
> 2026-02-16), y las SKUs siguen existiendo a efectos de soporte. Lo observable es **retiro de
> marca y absorción del producto**, no una discontinuación anunciada. No representar lo
> segundo como confirmado.

**Soda, la independiente más sana, dejó de ser open source.** `soda-core` v3 era Apache-2.0;
**v4 es Elastic License 2.0** — *"no podés ofrecer el software a terceros como servicio
gestionado… no podés eludir la funcionalidad de clave de licencia"* — y PyPI declara
`license: Proprietary`. Además v4 reemplazó SodaCL por una sintaxis de contratos, un cambio
rompiente. **Quien elija Soda Core "porque es OSS" está trabajando con información vieja.**

Y Soda es **dataset-céntrica**: no tiene modelo de run/task, ni DAG, ni operaciones. Su testing
de pipelines es un punto de integración, no un sujeto de primera clase.

**Conclusión:** el sujeto *run → task → operación sobre dataset* está vacante. El líder fue
absorbido y la independiente sana mira tablas en reposo.

### La señal estrella: "la operación que faltó"

Databand podía alertar sobre **una escritura que nunca ocurrió**. Una herramienta que mira
tablas en reposo **no puede**: ve una tabla desactualizada, no ve que el write no pasó. La
diferencia sale directamente de tener un modelo pipeline-céntrico y de ninguna otra cosa.

En su UI era un estado de primera clase y graficable — círculo rojo en el gráfico de
operaciones, × roja en el de tendencia. **La ausencia como señal.** Es la idea más fuerte de
todo el relevamiento y cae naturalmente del lado de Sentinel.

### Databand construyó el modelo correcto sobre el sustrato equivocado

Su modelo de datos era sólido: `run` → `task_run` (con identidad de intento y **firmas de
contenido** que permiten decir *"esta tarea se reusó, no se recorrió"*) → operación sobre
dataset (`read`/`write`/`delete`), más estadísticas por columna y una taxonomía que separa
métricas **declaradas por el usuario** de las **derivadas por el sistema**.

El sustrato fue el error: un canal RPC propietario con verbos fijos, y para Airflow un
**monkey-patch de la cluster policy** que envuelve `Operator.execute` y secuestra el logger —
con un fetcher que exige *"la versión de Airflow debe ser igual a la de Databand"*. Cero
OpenLineage en todo el repo.

**Cada uno de esos verbos mapea sobre OTLP**: un task run es un span, una operación sobre
dataset es un span event o un span hijo, las estadísticas de columna son métricas o atributos,
el estado es status más atributo. Ser OTel-nativo no es una apuesta — **es la corrección al
fallo específico que mató al antecedente más cercano.**

### Detalles baratos que vale copiar

| De | Qué | Por qué |
|---|---|---|
| Databand | **Auto-resolución de alerta al reintentar** — si el run se reinicia, la alerta se cierra sola y sólo vuelve si falla de nuevo | Los reintentos no paginan dos veces |
| Databand | **Alertas a nivel de fuente**, no de pipeline — conectás un Airflow y todos sus DAGs, presentes y futuros, quedan cubiertos | Cobertura sin configuración desde el día uno |
| Databand | Un gráfico en el editor de alertas que muestra **el umbral contra el histórico antes de guardar** | Previene la mayoría de las malas configuraciones |
| Soda | **`auto_exclude_anomalies: True`** en el entrenamiento — los puntos ya marcados no envenenan el ajuste siguiente | Ataca de raíz el *"un problema largo tapa sus huellas"* |
| Soda | **Backfilling del baseline** — mirar un año atrás para arrancar con modelo en vez de esperar semanas | Time-to-value |
| Soda | Tres tableros, **cada uno una pregunta**: Ejecutivo *"¿está mejorando?"* · Manager *"¿funciona el programa?"* · Steward *"¿qué arreglo hoy?"* | Arquitectura de información honesta |

### Sobre la detección de anomalías de Soda

La v3 usaba **Facebook Prophet** — confirmado por el pin de dependencias, no por marketing. La
actual es un modelo propietario **no divulgado** que dice ser *"70 % más preciso que Prophet"*,
con benchmark interno no reproducible. Venden explicabilidad y no publican el modelo.

Su propia franqueza sobre los límites vale citarla:

> *"Una anomalía sugiere un problema pero no lo confirma. Puede generar falsas alertas. No
> previene nada: marca cosas después de que pasaron."*

---

## 3.6 ⭐⭐ Nadie hace cumplir un contrato en el borde — y el único que monetiza la negociación cobra por ella

*Añadido 2026-09-01 al cerrar Acceldata · Bigeye · Metaplane · Soda · Great Expectations.*

| Proveedor | Artefacto de contrato | ¿Versionado? | ¿Acuerdo productor↔consumidor? | ¿Bloquea? |
|---|---|---|---|---|
| **Soda** | YAML con esquema + calidad + owner en un solo documento | **Sí** — historial ilimitado, **`checksum` por versión**, diff y split-view | **Sí** — roles, estados Open→Done/Won't Do, diff con color, notificaciones, autoridad "Manage Contract" | CI: warn en dev, bloqueo/cuarentena en prod |
| **Great Expectations** | Expectation Suite | **No** — verificado en el código: no hay campo `version`; `meta` sólo guarda la versión de la librería | No — no modela contraparte | Checkpoint + `fail_task_on_validation_failure` en Airflow |
| **Bigeye** | Bigconfig YAML (monitores) | Sólo por git | No | **`circuit_breaker_mode` en Airflow — apagado por defecto** |
| **Metaplane** | Ninguno | No | No | Comentarios en PR, sólo dbt |
| **Acceldata** | Ninguno — su Schema Drift Policy es diff entre crawls y **ni siquiera se puede correr a mano** | No | Los SLA de Data Products son sociales | No |

**Soda es el único que convierte la negociación en producto — y es exactamente lo que cobra.** Su tier gratuito incluye escaneo, observabilidad, alertas y usuarios ilimitados. El de **US$750/mes** agrega *"contratos de datos colaborativos"* y la interfaz no-code.

> **El motor de checks es commodity. El producto es el acuerdo negociado entre equipos.**

Sumado a que **Soda Core pasó a Elastic License 2.0** (§3.5), shippear firma de contratos productor↔consumidor en OSS genuino pega justo en su línea de monetización, y para compradores con mandato de procurement Apache/MIT ellos ya quedaron descalificados.

**Y nadie implementa semántica de *compatibilidad* de esquema.** El modelo maduro —
BACKWARD / FORWARD / FULL / TRANSITIVE del Schema Registry de Confluent, más ODCS v3.1.0 —
vive **fuera de este conjunto de proveedores**. Es prior art probado, barato de adoptar, y
encaja directo en el registro de contratos que ya existe.

### Tres cosas que validan decisiones ya tomadas

**El default `warn` está bien precedido, no es una concesión.** Los tres que documentan el tema convergieron por separado en enforcement de tres estados: Soda con `warn`/`fail` escalonado por entorno, Bigeye con `circuit_breaker_mode` **apagado por defecto**, GX con niveles de severidad en `notify_on`.

**La identidad estable de cada check es una lección aprendida a los golpes.** Soda shippea `identity:` (v3) y `qualifier` (v4) precisamente para que editar un check no huérfane su historial. Hay que hornearlo desde el día uno, no agregarlo después.

**El arranque en frío se resuelve releyendo historia del almacenamiento.** El backfill por Row Creation Time de Bigeye y el snapshot de metadata de Metaplane convierten una ventana de entrenamiento de 21 días en instantánea. Sentinel tiene `bronze.*` con TTL de 30 días: el baseline se puede bootstrapear el primer día.

### Metodologías de detección, lado a lado

| | Método | Ventana | Estacionalidad |
|---|---|---|---|
| **Soda v3** | **Prophet** (pin verificado en el código) | ≥4 medidas, `window_length` 1000 | la de Prophet |
| **Soda v4** | "Propietario"; la UI es z-score con **z=3 por defecto** | no documentada | no documentada |
| **Bigeye** | **Selección de modelo sobre una cartera de forecasters** + intervalo de predicción modelado aparte | **21 días**, reentrena cada 24 h | *"tres o más ciclos"* — **sólo semanal por defecto** |
| **Metaplane** | **Propio, explícitamente no-Prophet, consciente de la forma** (escalera, monótona, escalón); **reentrena tras cada observación** | 3–7 días horarios | día/DoD/WoW/MoM/YoY |
| **GX Core** | **Ninguno — sólo reglas.** Su detector de outliers es IQR **dentro del lote** | — | — |
| **GX Cloud** | **10 % de desvío sobre la media móvil de 5 corridas** | 5 corridas | ninguna |
| **Acceldata** | **No divulgado.** "Un slider." | ? | ? |

**Publicar el algoritmo es una cuña creíble.** Acceldata no divulga nada; Bigeye no nombra
familias de modelos y su whitepaper está detrás de un formulario; Metaplane publica el
razonamiento pero no el estimador. Un proyecto abierto que publique **algoritmo, ventana y
semántica del umbral** se diferencia sólo con transparencia — y la honestidad de Bigeye al
admitir su límite de *"tres o más ciclos"* compra más credibilidad que un "ML-powered" sin
calificar.

El argumento más filoso de la categoría es de Metaplane y **es cierto**:

> *"Estos modelos de estantería (Prophet, por ejemplo) están hechos para pronosticar, no para
> detectar anomalías. Optimizan el objetivo equivocado: minimizar error de pronóstico en vez
> de identificar correctamente las anomalías."*

### Cuatro ideas de visualización, priorizadas

1. **La banda dibujada y el umbral de alerta tienen que ser el mismo objeto.** Metaplane shippeó una versión donde diferían y llamó públicamente "simplificación" al arreglarlo: *"si ves un valor fuera del área verde, Metaplane mandó una alerta."* No repetir su v1.
2. **El estado gris del Scorecard de Bigeye** — verde = monitoreado y sano · rojo = monitoreado y fallando · **gris = sin monitor ese día**. Distingue *sano* de *no observado*; casi todos los widgets de salud confunden las dos cosas.
3. **Marcadores de cambio de configuración sobre la serie temporal** (Soda) — permite distinguir *"cambió el dato"* de *"cambiamos el detector"*.
4. **Tres estados de resultado, no dos** (Bigeye): Passing · **Alerting** (discrepancia) · **Failing** (error de infraestructura). Soda codifica lo mismo con `has_failures()` vs `has_errors()`. La mayoría confunde *"el check no coincidió"* con *"el check no pudo correr"*.

### La posición desocupada

Metaplane y Bigeye llegaron por separado a los mismos cuatro pilares — métricas, metadata,
lineaje, logs — y **ambos descartaron *trazas* y agregaron *lineaje***.

Para una herramienta OTel-nativa ese es el hueco interesante: **una traza *es* un registro de
lineaje con tiempos.** Sostener que lineaje y trazas son el mismo objeto a distinta
granularidad es una posición que nadie ocupa.

Dato de contexto: **Datadog —el entrante mejor financiado, ya con Metaplane adentro— eligió
OpenLineage JSON sobre HTTP propietario para lineaje**, mientras su Data Streams Monitoring ya
funciona con APM instrumentado con OTel. Tratan los dos estándares como adyacentes, no
competidores. **Un solo formato OTLP que transporte facetas tipo `dataQualityMetrics` /
`dataQualityAssertions`, con un contexto de traza que abarque app → pipeline → tabla, es una
arquitectura que nadie de este conjunto construyó.**

### Una advertencia operativa

**Shippear el migrador antes que el cambio rompiente.** GX borró la CLI, el formato de
configuración, el Validator y los profilers **en una sola release, sin camino automático** — y
el foro muestra el costo. Soda está cometiendo el mismo error ahora con v3→v4. Aplica directo
al versionado del registro de contratos de Sentinel.

---

## 4. What the evidence says users actually value

**Anomaly detection wins because it needs the least maintenance.** Monte Carlo measured human
touches per monitor across 11M+ tables:

| Monitor type | Avg touches |
|---|---|
| Custom SQL | 2.35 |
| Data validation tests | 2.03 |
| Comparison monitors | 1.63 |
| **Anomaly detection** | **1.33 — 40 % less** |

This is the strongest quantitative evidence in the corpus, and it directly validates the
Tier-1-statistical-first plan.

**Alert noise is the category's #1 documented failure mode.**

- A 150-column dataset generates **900–1,200 automated rules**; one 500-asset team faced
  **3,000+ alerts/week**, cut to **<30 clusters** by lineage-based grouping
- Engagement **drops ~15 % above 50 alerts/week and a further 20 % above 100**
- **20 % of users escalate 80 % of alerts**
- **~34 % of detected "incidents" are not errors** — business variation (20 %) or planned
  backfills (14.2 %)
- Grafana's 1,363-respondent survey: alert fatigue is an obstacle for **30 %**

**Detection before the business notices is the purchase driver.** 74 % of data professionals
say stakeholders find issues first most or all of the time; 68 % report time-to-detection ≥ 4
hours; time-to-resolution averages 15 hours.

---

## 5. Visualizations worth stealing

| Visualization | What it does | Why |
|---|---|---|
| ⭐ **Anomaly chart with expected-range band** | observed line + baseline band + flagged points | Turns *"the test failed"* into *"here is normal, here is where we left it."* Without it a statistical alert is not arguable. Universal across the category |
| ⭐ **Freshness update timeline** | ticks per update, **▽ marks "now"**, dotted line at the expected gap; hover a gap → both timestamps and the interval | Reads far better than a value chart for arrival/latency. Maps 1:1 onto the Arrival watcher |
| ⭐ **State timeline** (Grafana panel) | state changes as coloured regions, length = time in state | Highest-leverage pipeline panel: validation-mode changes, per-run status, backfill windows. Answers *when* it broke and *for how long* |
| **Lineage painted with health** | the DAG, each node carrying one fused status | Lineage without health is documentation; with health it is an incident tool |
| **Node graph frames** (Grafana) | `mainstat`/`secondarystat`/`arc__*`/`detail__*` | The open answer to Datadog's topology map — any source can emit it |
| **`Simulate Configuration`** | preview a sensitivity change **against history before saving** | The correct answer to alert fatigue. Almost nobody ships it |
| **Schema diff with `ordinal_position`** | detects add/drop/retype **and reorder** | OpenLineage models ordinal position for exactly this |

---

## 6. Recommended V2 shortlist

Ordered by (differentiation × evidence) ÷ effort. Every item leans on something that exists.

### Tier 1 — build first

**V2.1 · Contract Health — make the receive boundary visible.**
The counters already exist (`signals_rejected_total{signal,reason}`, `contract.grpc_validation`
in `off`/`warn`/`strict`). Nothing renders them. Ship: violation rate per producer × signal ×
reason over time; a **state timeline of validation mode**; top violating `sentinel.*` keys;
contract-version adoption per producer; and a **"would-be-rejected under strict"
counterfactual** so a team can promote `warn → strict` with evidence rather than nerve.
*Why first:* §3.1 — no competitor has it, and the data is already being collected.

**V2.2 · Arrival + Volume watchers as z-score over bronze, with the band as the primary artifact.**
Match the documented commercial baseline before beating it: Elementary ships plain z-score,
threshold 3.0, 1-day bucket, 14-day training, 2-day detection (**nested, not additive**), with
seasonality as a `PARTITION BY`. Beat it cheaply with a genuinely **sliding** window (theirs is
cumulative, so *"a long problem covers its own tracks"*), **robust statistics** (MAD/median),
and **dual warn/error severity**.
*Why:* §4 — 40 % fewer human touches than any rule-based alternative.

**V2.3 · The flow DAG becomes health-bearing.**
`services/flow-ui` already renders origin → collector → `bronze.*` with a contract-backed node
inspector. Add per-node fused health state, edge thickness = throughput, edge colour =
violation rate, and a state-timeline strip. Emit it as Grafana **node-graph frames** so it
renders there too with no plugin.

### Tier 2

**V2.4 · Freshness/arrival lag as a first-class signal**, named `data.staleness.*` and
`pipeline.*` per the two open proposals — free standards positioning (§3.2).

**V2.5 · An alert-noise budget, designed in from day one.** Dedup, lineage-based clustering,
suppression during declared backfills, per-channel rate ceilings defaulted at the documented
**50/week and 100/week engagement cliffs**, severity from downstream blast radius. *Not
retrofittable.*

**V2.6 · Schema watcher with ordinal-position awareness** and a diff view. Attribute violations
per schema version — Datadog does this for Avro/Protobuf only, **not JSON Schema**, which is
precisely Sentinel's contract format.

### Tier 3 — strategic bets

**V2.7 · Emit OpenLineage facets over OTLP.** Map per-signal stats onto
`DataQualityMetricsInputDatasetFacet` and validation results onto
`DataQualityAssertionsDatasetFacet` (whose `severity: error|warn` already mirrors our policy).
Publishing the OTLP transport OpenLineage lacks is the highest-leverage open-source
contribution available here — real gap, real implementation, interoperability with ~16 lineage
consumers.

**V2.8 · Adopt OpenLineage's facet governance for `contracts/`** — namespaced prefixes,
per-object immutable `_schemaURL`, a documented custom→standard promotion path. Gives per-facet
version evolution instead of a monolithic `v1/`→`v2/` bump. **Worth an ADR before the registry
grows.**

**V2.9 · Usage-driven signal reduction.** Observe which bronze columns and label combinations
detectors actually read; recommend aggregations at ingestion. Grafana proves the pattern
(**35 % average cost reduction across 1,500+ orgs**) and it is Cloud-only — an OSS
implementation is a genuine differentiator.

### Team-decided, not survey-derived

**V2.10 · Language selector — PT-BR · ES · EN.** A dropdown in the header, alongside the
palette switch. Not a finding from this survey; a Crew decision, recorded here so the roadmap
is one list. Three things make it larger than string extraction, and they should be settled
before any code:

1. **The prose IS the product.** Every board publishes its own method — *"median ± 3σ, σ from
   MAD × 1.4826 · stddev only where MAD collapses"*, *"grey is not observed, never fine"* —
   and §3.5 argues that publishing algorithm, window and threshold semantics is the
   differentiation. Translating that is not localisation of labels, it is translating
   explanation where precision is the whole value. Symbols and identifiers (`σ`, `MAD`,
   `sentinel.run_id`, table names) stay untranslated.
2. **The sentences are composed server-side.** `health_note`, `volume_state.why` and the
   contract notes are assembled in `pipeline.py` and shipped as finished English strings.
   Either the backend emits a **structured reason** (`{code, params}`) and the client renders
   it, or the server localises and needs to know the viewer's locale. The first is the right
   shape and is the actual work in this item; the dropdown is an afternoon.
3. **Number formatting is per-locale.** pt-BR uses a comma decimal separator; `fmt()` in
   `app.js` and `fmt()` in `main.py` both hard-code the English convention, and the figures
   are rendered server-side before any script runs — so the locale has to be known at
   render time, not only after hydration.

Prerequisite either way: the reason-code refactor. Doing the dropdown first would freeze the
English strings in place across four boards.

### Explicitly deprioritized

- **Column-level lineage** — highest effort, and there is no column-level transformation graph
  to derive it from yet. Do stream/table level first.
- **Cost/FinOps** — needs warehouse billing integration; orthogonal to the OTel thesis.
- **LLM tiers** — keep at Tier 3 as already planned. 92 % of Grafana respondents see value in
  AI for anomaly detection, but **26 % cite excessive manual context input as the top barrier**,
  and Gartner's advice is to *"validate AI claims during the pilot phase."* Tier-1 statistics
  has better evidence and lower maintenance burden.

---

## 7. Coverage ledger

| Topic | Depth | Confidence |
|---|---|---|
| Monte Carlo · Datadog · Grafana | Deep, primary-sourced | High |
| OpenLineage spec + facets · OTel semconv gap | Deep, verified firsthand | High |
| Elementary (z-score method, OSS/Cloud split) | Good | Medium-High |
| Great Expectations · Marquez · ODCS · Dagster | Adequate | Medium |
| **Databand · Soda** | **Deep, primary-sourced** (línea tardía, 2026-09-01) | **High** |
| **Acceldata · Bigeye · Metaplane · Great Expectations** | **Deep, primary-sourced** (línea tardía) | **High** |
| **Anomalo · Sifflet** | **Thin to none** | **—** |

**Three questions worth a fresh search budget:** Anomalo's actual ML method (the
gradient-boosted-classifier reading is *plausible inference, not confirmed*); Sifflet's
monitoring-as-code YAML schema (the best available reference for git-managed monitors); and
whether IBM has published a formal support-withdrawal letter for Databand (§3.5 settles the
brand withdrawal; the announcement letter remains unfound and `ibm.com/docs` is WAF-blocked to
automated clients).

---

## 8. Two structural warnings to design around

1. **Tree vs DAG.** OTel spans have one parent; data lineage is a DAG with many. Both
   OpenLineage's founder and an independent dbt-OTel proof of concept hit this. Decide
   deliberately — span **links** for extra parents, or lineage as a separate relation joined on
   `run_id`. Datadog chose links.
2. **Lossy OTel→Prometheus mapping**, and hard limits if Grafana is ever a render target: max
   15 promoted Loki labels, 128 structured-metadata attributes / 64 KB, 5 MB per trace.
