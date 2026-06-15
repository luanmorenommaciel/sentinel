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
		v = "clickhouse://otelgen:otelgen_secret@localhost:9000/sentinel"
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

	store.SendSpan(model.Span{
		TraceID:            "0badc0decafebabe0123456789abcdef",
		SpanID:             "deadbeefcafe0001",
		ServiceName:        "integration-test",
		Name:               "test.span",
		StartUnixNano:      time.Now().UnixNano(),
		EndUnixNano:        time.Now().UnixNano() + 1_000_000,
		StatusCode:         "OK",
		Attributes:         map[string]string{"test": "true"},
		ResourceAttributes: map[string]string{"service.name": "integration-test"},
		ContractVersion:    "1.0.0",
		IngestedAt:         time.Now().UTC(),
	})

	// let the flush interval fire
	time.Sleep(400 * time.Millisecond)

	conn := store.Conn()
	var count uint64
	if err := conn.QueryRow(context.Background(),
		"SELECT count() FROM sentinel.otel_spans WHERE trace_id = '0badc0decafebabe0123456789abcdef'",
	).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count == 0 {
		t.Error("expected span to be in ClickHouse, got 0 rows")
	}
}

func TestIntegration_InsertLog(t *testing.T) {
	store := newTestStore(t)

	store.SendLog(model.Log{
		TimeUnixNano:       time.Now().UnixNano(),
		ServiceName:        "integration-test",
		SeverityText:       "INFO",
		SeverityNumber:     9,
		Body:               "integration test log",
		ContractVersion:    "1.0.0",
		Attributes:         map[string]string{},
		ResourceAttributes: map[string]string{"service.name": "integration-test"},
		IngestedAt:         time.Now().UTC(),
	})

	time.Sleep(400 * time.Millisecond)

	conn := store.Conn()
	var count uint64
	if err := conn.QueryRow(context.Background(),
		"SELECT count() FROM sentinel.otel_logs WHERE body = 'integration test log'",
	).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count == 0 {
		t.Error("expected log to be in ClickHouse, got 0 rows")
	}
}

func TestIntegration_InsertMetric(t *testing.T) {
	store := newTestStore(t)

	store.SendMetric(model.Metric{
		TimeUnixNano:       time.Now().UnixNano(),
		ServiceName:        "integration-test",
		Name:               "integration.test_gauge",
		Type:               "gauge",
		Value:              99.9,
		ContractVersion:    "1.0.0",
		Attributes:         map[string]string{},
		ResourceAttributes: map[string]string{"service.name": "integration-test"},
		IngestedAt:         time.Now().UTC(),
	})

	time.Sleep(400 * time.Millisecond)

	conn := store.Conn()
	var count uint64
	if err := conn.QueryRow(context.Background(),
		"SELECT count() FROM sentinel.otel_metrics WHERE name = 'integration.test_gauge'",
	).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count == 0 {
		t.Error("expected metric to be in ClickHouse, got 0 rows")
	}
}
