---
title: Go — Idioms + Patterns for Sentinel
last_updated: 2026-06-01
confidence: 0.85
---

> **MCP Validated:** 2026-06-01
> Sources: go.dev/doc, pkg.go.dev/go.opentelemetry.io/collector, clickhouse.com/docs/integrations/go, golangci-lint.run

# Go — Idioms + Patterns for Sentinel

Go is the **safe-default Collector language** (ADR-0004). Even if Rust wins the bake-off,
Go expertise is needed to read the upstream `opentelemetry-collector` reference implementation,
which is written entirely in Go.

---

## Project Setup

```text
services/collector-go/
├── go.mod          # module + versioned deps
├── go.sum          # committed (we ship a binary)
├── cmd/collector/
│   └── main.go     # calls otelcol.NewCommand()
├── internal/       # unexported impl (compiler-enforced)
│   ├── receiver/
│   ├── processor/
│   └── exporter/   # ClickHouse write logic
└── Dockerfile
```

Use `internal/` for implementation details; `pkg/` for stable importable code.

```bash
# Static binary suitable for distroless images
CGO_ENABLED=0 GOOS=linux go build -o bin/collector ./cmd/collector/
```

---

## Concurrency

### Goroutines + Channels

```go
// Unbuffered — sender blocks until receiver is ready (synchronisation point)
ch := make(chan *Batch)

// Buffered — sender blocks only when buffer full (backpressure boundary)
ch := make(chan *Batch, 512)
```

**Sentinel rule:** all inter-stage queues use buffered channels.
Buffer size = burst duration × throughput rate.

### select{} + context.Context

Always add a `ctx.Done()` arm in any long-running `select`:

```go
select {
case batch := <-inCh:
    process(batch)
case <-ctx.Done():
    return ctx.Err()
case <-time.After(5 * time.Second):
    flush() // periodic partial-batch flush
}
```

Pass `context.Context` as the **first parameter** of every function that may block.
Never store ctx in a struct.

### Backpressure: Bounded Channel

```go
func (p *Pipeline) Receive(ctx context.Context, rec LogRecord) error {
    select {
    case p.queue <- rec:
        return nil
    case <-ctx.Done():
        return ctx.Err()
    default:
        return ErrBatchFull // queue full; caller signals upstream to slow down
    }
}
```

### errgroup for Parallel Fan-Out

```go
import "golang.org/x/sync/errgroup"

func (e *Exporter) flushAll(ctx context.Context, rows []Row) error {
    g, gCtx := errgroup.WithContext(ctx)
    for _, shard := range e.shards {
        shard := shard // capture loop variable
        g.Go(func() error { return shard.Insert(gCtx, rows) })
    }
    return g.Wait() // returns first error; cancels gCtx for siblings
}
```

---

## Error Handling

Go has no exceptions. Errors are explicit return values.

```go
result, err := doSomething(ctx)
if err != nil {
    return fmt.Errorf("doSomething: %w", err) // %w wraps for unwrapping
}
```

```go
// Sentinel errors — declare at package level
var (
    ErrBatchFull     = errors.New("batch full")
    ErrSchemaInvalid = errors.New("schema validation failed")
)

// Check in the chain (works through %w wraps)
if errors.Is(err, ErrBatchFull) { ... }

// Extract a typed error
var ce *ClickHouseError
if errors.As(err, &ce) { log.Printf("CH code=%d", ce.Code) }
```

Note: `errors.Is` traverses the wrap chain. Never compare errors with `==`.
Reserve `panic` for programmer errors (nil pointer logic faults), not I/O failures.

---

## Reading the Upstream OTel Collector

### Package Layout

```text
opentelemetry-collector/
├── receiver/otlpreceiver/   # OTLP gRPC + HTTP (what we feed into)
├── processor/batchprocessor/
├── exporter/
├── otelcol/                 # orchestration — builds + runs the binary
└── component/               # base interfaces: Component, Config, Factory
```

### Factory Pattern

Every component exposes `NewFactory()` returning a `component.Factory`.
The factory owns config creation and component instantiation:

```go
func NewFactory() exporter.Factory {
    return exporter.NewFactory(
        metadata.Type,
        createDefaultConfig,
        exporter.WithLogs(createLogsExporter, metadata.LogsStability),
    )
}
```

### otelcol.NewCommand (entry point)

```go
func main() {
    factories := otelcol.Factories{
        Receivers: map[component.Type]receiver.Factory{
            otlpreceiver.NewFactory().Type(): otlpreceiver.NewFactory(),
        },
        Exporters: map[component.Type]exporter.Factory{
            chexporter.NewFactory().Type(): chexporter.NewFactory(),
        },
    }
    cmd, _ := otelcol.NewCommand(otelcol.CollectorSettings{
        BuildInfo: component.BuildInfo{Command: "sentinel-collector", Version: "0.1.0"},
        Factories: func() (otelcol.Factories, error) { return factories, nil },
    })
    if err := cmd.Execute(); err != nil { os.Exit(1) }
}
```

Every component implements `Start(ctx, host)` and `Shutdown(ctx)`.
Always honour the context timeout in `Shutdown`.

---

## ClickHouse Client (clickhouse-go v2)

Use the native driver `github.com/ClickHouse/clickhouse-go/v2` — not the `database/sql` shim.
Supports batch inserts, connection pooling, LZ4 compression, and async inserts natively.

```go
conn, _ := clickhouse.Open(&clickhouse.Options{
    Addr:            []string{"clickhouse:9000"},
    Auth:            clickhouse.Auth{Database: "sentinel", Username: "default", Password: os.Getenv("CH_PASSWORD")},
    MaxOpenConns:    10,
    MaxIdleConns:    5,
    ConnMaxLifetime: time.Hour,
    DialTimeout:     5 * time.Second,
    Compression:     &clickhouse.Compression{Method: clickhouse.CompressionLZ4},
})
```

### Batch Insert

```go
func (e *Exporter) insertBatch(ctx context.Context, rows []OTLPLogRow) error {
    batch, err := e.conn.PrepareBatch(ctx, "INSERT INTO otel_logs")
    if err != nil {
        return fmt.Errorf("PrepareBatch: %w", err)
    }
    for _, r := range rows {
        if err := batch.Append(r.Timestamp, r.SeverityText, r.Body, r.Attrs); err != nil {
            return fmt.Errorf("Append: %w", err)
        }
    }
    return fmt.Errorf("Send: %w", batch.Send())
}
```

For very high throughput, `conn.AsyncInsert` is available (fire-and-forget mode).
Monitor insert errors via ClickHouse `system.query_log`.

---

## Testing

### Table-Driven Tests (idiomatic)

```go
func TestSeverityMapping(t *testing.T) {
    t.Parallel()
    cases := []struct {
        input string
        want  int32
    }{
        {"DEBUG", 5}, {"INFO", 9}, {"ERROR", 17}, {"", 0},
    }
    for _, tc := range cases {
        tc := tc
        t.Run(tc.input, func(t *testing.T) {
            t.Parallel()
            if got := mapSeverity(tc.input); got != tc.want {
                t.Errorf("mapSeverity(%q) = %d, want %d", tc.input, got, tc.want)
            }
        })
    }
}
```

`testify/assert` is acceptable for integration tests where diff output matters;
avoid `testify/suite`. Use stdlib `t.Errorf` for pure unit tests.

Always pass a context with timeout in I/O tests:

```go
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
```

---

## Build + CI

```bash
go fmt ./...                    # format (fail CI if diff)
go vet ./...                    # built-in static analysis
go test ./... -race -cover      # race detector + coverage
golangci-lint run ./...         # full lint suite
```

### golangci-lint Linter Set

```yaml
# .golangci.yml (services/collector-go/)
linters:
  enable:
    - govet        # standard checks
    - staticcheck  # SA*, S*, QF* (replaces errcheck, gosimple)
    - gosec        # hardcoded creds, unsafe blocks (G-series)
    - gocritic     # style + performance
    - ineffassign  # unused assignments
    - contextcheck # ensure context passed, not stored
```

### CI Gate Mapping

| Crew B gate | Go command |
|---|---|
| 1. Linter | `golangci-lint run` |
| 2. Type check | `go build ./...` (compiler enforces) |
| 3. Tests >80% | `go test ./... -race -coverprofile=coverage.out` |
| 4. Security | `govulncheck ./...` + gosec via golangci-lint |
| 5. Markdown | `markdownlint` (language-agnostic) |
| 6. AI review | CodeRabbit |
| 7. Build | `CGO_ENABLED=0 go build ./cmd/collector/` + Docker |

---

## Idiom Cheat Sheet

```go
// defer cleanup — always pair Open with deferred Close
f, err := os.Open(path)
if err != nil { return err }
defer f.Close()

// context deadline on I/O
ctx, cancel := context.WithTimeout(parent, 3*time.Second)
defer cancel()

// periodic flush — use NewTicker, not time.Tick (Tick leaks)
ticker := time.NewTicker(500 * time.Millisecond)
defer ticker.Stop()

// nil channel disables a select case (zero-cost toggle)
var flushCh <-chan time.Time // nil — case never fires
if ready { flushCh = time.After(0) }

// sync.Once — safe lazy initialisation
var once sync.Once
once.Do(func() { conn, err = openConn() })

// signal without data — empty struct, zero allocation
done := make(chan struct{})
close(done) // broadcast to all receivers
```

---

## See Also

- `../rust/index.md` — Rust KB sibling (Tokio, tonic, the bake-off counterpart)
- `../../telemetry/otel-collector/index.md` — receiver/processor/exporter pipeline concepts
- `../../storage/clickhouse/index.md` — ClickHouse schema, OTel table layout, connection tuning
- `../../process/crew-b-wow/index.md` — CI gates, PR flow, ADR process
- `../../../CLAUDE.md` — KB routing table, terminology guardrails
- `../../../docs/RUST_PROJECT_STANDARDS.md` — Rust standards (parallel to these Go conventions)
- `docs/adr/0004-collector-implementation-language.md` — Go vs Rust bake-off decision record
- Upstream Collector: <https://github.com/open-telemetry/opentelemetry-collector>
- Go docs: <https://go.dev/doc/>
- clickhouse-go v2: <https://clickhouse.com/docs/integrations/go>
- golangci-lint linters: <https://golangci-lint.run/usage/linters/>
