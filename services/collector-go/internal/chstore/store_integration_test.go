//go:build integration

// Integration tests for chstore — require a real ClickHouse instance.
//
// Run with:
//
//	CLICKHOUSE_DSN="clickhouse://otelgen:otelgen_secret@localhost:9000/sentinel" \
//	  CGO_ENABLED=0 go test ./internal/chstore/... -tags integration -v
//
// The ClickHouse instance must have the sentinel schema applied
// (see migrations/001_init_schema.sql).
package chstore_test

import (
	"context"
	"log/slog"
	"os"
	"testing"
	"time"

	"sentinel/collector/internal/chstore"
	"sentinel/collector/internal/model"
)

func dsn(t *testing.T) string {
	t.Helper()
	v := os.Getenv("CLICKHOUSE_DSN")
	if v == "" {
		v = "clickhouse://otelgen:otelgen_secret@localhost:9000/default"
	}
	return v
}

func newTestStore(t *testing.T) *chstore.Store {
	t.Helper()
	store, err := chstore.New(dsn(t), 10, 200*time.Millisecond, slog.Default())
	if err != nil {
		t.Skipf("ClickHouse unavailable (%v) — skipping integration test", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	store.Start(ctx)
	t.Cleanup(func() {
		cancel()
		store.Close() //nolint:errcheck
	})
	return store
}

func TestIntegration_InsertSpan(t *testing.T) {
	store := newTestStore(t)

	now := time.Now().UTC()
	startNano := now.UnixNano()
	endNano := startNano + 1_000_000

	store.SendSpan(model.Span{
		Timestamp:          time.Unix(0, startNano).UTC(),
		TraceId:            "0badc0decafebabe0123456789abcdef",
		SpanId:             "deadbeefcafe0001",
		ParentSpanId:       "",
		SpanName:           "test.span",
		ServiceName:        "integration-test",
		SentinelScenario:   "baseline",
		SentinelRunId:      "test-run",
		CloudProvider:      "gcp",
		SentinelSynthetic:  1,
		Duration:           endNano - startNano,
		StatusCode:         "OK",
		ContractVersion:    "1.0.0",
		SpanAttributes:     map[string]string{"test": "true"},
		ResourceAttributes: map[string]string{},
	})

	time.Sleep(400 * time.Millisecond)

	conn := store.Conn()
	var count uint64
	if err := conn.QueryRow(context.Background(),
		"SELECT count() FROM otel_traces WHERE TraceId = '0badc0decafebabe0123456789abcdef'",
	).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count == 0 {
		t.Error("expected span to be in ClickHouse, got 0 rows")
	}
}

func TestIntegration_InsertLog(t *testing.T) {
	store := newTestStore(t)

	now := time.Now().UTC()

	store.SendLog(model.Log{
		Timestamp:          now,
		ServiceName:        "integration-test",
		SentinelScenario:   "baseline",
		SentinelRunId:      "test-run",
		CloudProvider:      "gcp",
		SentinelSynthetic:  1,
		SeverityText:       "INFO",
		SeverityNumber:     9,
		Body:               "integration test log",
		TraceId:            "",
		SpanId:             "",
		ContractVersion:    "1.0.0",
		LogAttributes:      map[string]string{},
		ResourceAttributes: map[string]string{},
	})

	time.Sleep(400 * time.Millisecond)

	conn := store.Conn()
	var count uint64
	if err := conn.QueryRow(context.Background(),
		"SELECT count() FROM otel_logs WHERE Body = 'integration test log'",
	).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count == 0 {
		t.Error("expected log to be in ClickHouse, got 0 rows")
	}
}

func TestIntegration_InsertMetric(t *testing.T) {
	store := newTestStore(t)

	now := time.Now().UTC()

	store.SendMetric(model.Metric{
		Timestamp:          now,
		MetricName:         "integration.test_gauge",
		MetricType:         "gauge",
		Value:              99.9,
		ServiceName:        "integration-test",
		SentinelScenario:   "baseline",
		SentinelRunId:      "test-run",
		CloudProvider:      "gcp",
		SentinelSynthetic:  1,
		ContractVersion:    "1.0.0",
		Attributes:         map[string]string{},
		ResourceAttributes: map[string]string{},
	})

	time.Sleep(400 * time.Millisecond)

	conn := store.Conn()
	var count uint64
	if err := conn.QueryRow(context.Background(),
		"SELECT count() FROM otel_metrics WHERE MetricName = 'integration.test_gauge'",
	).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count == 0 {
		t.Error("expected metric to be in ClickHouse, got 0 rows")
	}
}
