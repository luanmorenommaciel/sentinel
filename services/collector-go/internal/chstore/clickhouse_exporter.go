package chstore

import (
	"context"
	"fmt"

	"sentinel/collector/internal/model"
)

// BronzeCounts reports how many rows ExportBronze wrote to each bronze table.
type BronzeCounts struct {
	Logs    int
	Spans   int
	Metrics int
}

// ExportBronze writes logs, spans, and gauge/sum metrics into the Sentinel bronze layer
// (sentinel.* tables, DDL: infra/clickhouse/init.d/01-bronze-otel.sql) — the OTel-contrib
// v0.105.0 shape that collector-rust's clickhouse_exporter.rs also targets. Bronze has no
// typed Sentinel columns, so the hoisted fields are folded back into ResourceAttributes
// (see fullResourceAttributes).
//
// Histogram metrics are not written here: transform/metrics.go explodes each histogram
// datapoint into one row per bucket boundary, which does not match bronze's per-datapoint
// BucketCounts/ExplicitBounds array shape (sentinel.otel_metrics_histogram).
func (s *Store) ExportBronze(
	ctx context.Context,
	logs []model.Log,
	spans []model.Span,
	metrics []model.Metric,
) (BronzeCounts, error) {
	var counts BronzeCounts

	if len(logs) > 0 {
		if err := s.insertBronzeLogs(ctx, logs); err != nil {
			return counts, fmt.Errorf("bronze logs: %w", err)
		}
		counts.Logs = len(logs)
	}

	if len(spans) > 0 {
		if err := s.insertBronzeTraces(ctx, spans); err != nil {
			return counts, fmt.Errorf("bronze traces: %w", err)
		}
		counts.Spans = len(spans)
	}

	var gauges, sums []model.Metric
	for _, m := range metrics {
		switch m.MetricType {
		case "gauge":
			gauges = append(gauges, m)
		case "sum":
			sums = append(sums, m)
		}
	}
	if len(gauges) > 0 {
		if err := s.insertBronzeMetrics(ctx, "sentinel.otel_metrics_gauge", gauges); err != nil {
			return counts, fmt.Errorf("bronze metrics gauge: %w", err)
		}
	}
	if len(sums) > 0 {
		if err := s.insertBronzeMetrics(ctx, "sentinel.otel_metrics_sum", sums); err != nil {
			return counts, fmt.Errorf("bronze metrics sum: %w", err)
		}
	}
	counts.Metrics = len(gauges) + len(sums)

	return counts, nil
}

// insertBronzeMetricsSplit routes a batch of metrics to the bronze per-type tables,
// matching flushLoop's `func(ctx, []T) error` shape so it can drive the metrics flush
// goroutine directly (ADR-0009). It splits gauge/sum like ExportBronze and — per
// ADR-0010 (v1 = gauge+sum) — skips histogram/summary/exp-histogram, logging the drop
// so the omission is observable rather than silent.
func (s *Store) insertBronzeMetricsSplit(ctx context.Context, metrics []model.Metric) error {
	var gauges, sums []model.Metric
	var dropped int
	for _, m := range metrics {
		switch m.MetricType {
		case "gauge":
			gauges = append(gauges, m)
		case "sum":
			sums = append(sums, m)
		default:
			dropped++
		}
	}
	if dropped > 0 && s.logger != nil {
		s.logger.Warn("bronze: dropping non-gauge/sum metrics (ADR-0010 v1=gauge+sum)",
			"dropped", dropped, "kept", len(gauges)+len(sums))
	}
	if len(gauges) > 0 {
		if err := s.insertBronzeMetrics(ctx, "sentinel.otel_metrics_gauge", gauges); err != nil {
			return fmt.Errorf("bronze metrics gauge: %w", err)
		}
	}
	if len(sums) > 0 {
		if err := s.insertBronzeMetrics(ctx, "sentinel.otel_metrics_sum", sums); err != nil {
			return fmt.Errorf("bronze metrics sum: %w", err)
		}
	}
	return nil
}

func (s *Store) insertBronzeLogs(ctx context.Context, logs []model.Log) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO sentinel.otel_logs (
		Timestamp, ServiceName, SeverityText, SeverityNumber, Body,
		TraceId, SpanId, LogAttributes, ResourceAttributes
	)`)
	if err != nil {
		return fmt.Errorf("prepare: %w", err)
	}
	for _, l := range logs {
		resourceAttrs := fullResourceAttributes(
			l.ServiceName, l.SentinelScenario, l.SentinelRunId, l.CloudProvider,
			l.SentinelSynthetic, l.ContractVersion, l.ResourceAttributes,
		)
		if err := batch.Append(
			l.Timestamp,
			l.ServiceName,
			l.SeverityText,
			severityNumberUint8(l.SeverityNumber),
			l.Body,
			l.TraceId,
			l.SpanId,
			l.LogAttributes,
			resourceAttrs,
		); err != nil {
			return fmt.Errorf("append: %w", err)
		}
	}
	return batch.Send()
}

func (s *Store) insertBronzeTraces(ctx context.Context, spans []model.Span) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO sentinel.otel_traces (
		Timestamp, TraceId, SpanId, ParentSpanId, SpanName,
		ServiceName, Duration, StatusCode, SpanAttributes, ResourceAttributes
	)`)
	if err != nil {
		return fmt.Errorf("prepare: %w", err)
	}
	for _, sp := range spans {
		resourceAttrs := fullResourceAttributes(
			sp.ServiceName, sp.SentinelScenario, sp.SentinelRunId, sp.CloudProvider,
			sp.SentinelSynthetic, sp.ContractVersion, sp.ResourceAttributes,
		)
		if err := batch.Append(
			sp.Timestamp,
			sp.TraceId,
			sp.SpanId,
			sp.ParentSpanId,
			sp.SpanName,
			sp.ServiceName,
			sp.Duration,
			bronzeStatusCode(sp.StatusCode),
			sp.SpanAttributes,
			resourceAttrs,
		); err != nil {
			return fmt.Errorf("append: %w", err)
		}
	}
	return batch.Send()
}

func (s *Store) insertBronzeMetrics(ctx context.Context, table string, metrics []model.Metric) error {
	batch, err := s.conn.PrepareBatch(ctx, fmt.Sprintf(`INSERT INTO %s (
		ServiceName, MetricName, TimeUnix, Value, Attributes, ResourceAttributes
	)`, table))
	if err != nil {
		return fmt.Errorf("prepare: %w", err)
	}
	for _, m := range metrics {
		resourceAttrs := fullResourceAttributes(
			m.ServiceName, m.SentinelScenario, m.SentinelRunId, m.CloudProvider,
			m.SentinelSynthetic, m.ContractVersion, m.ResourceAttributes,
		)
		if err := batch.Append(
			m.ServiceName,
			m.MetricName,
			m.Timestamp,
			m.Value,
			m.Attributes,
			resourceAttrs,
		); err != nil {
			return fmt.Errorf("append: %w", err)
		}
	}
	return batch.Send()
}

// fullResourceAttributes reconstructs the complete resource-attribute map bronze expects.
// The normalized default.* schema hoists service.name/sentinel.*/cloud.provider into typed
// columns and strips them out of ResourceAttributes; bronze has no typed Sentinel columns,
// so this folds them back in alongside contract_version (contrib/bronze convention, matches
// collector-rust's service_name_and_resource).
func fullResourceAttributes(
	serviceName, scenario, runID, cloudProvider string,
	synthetic uint8,
	contractVersion string,
	remaining map[string]string,
) map[string]string {
	m := make(map[string]string, len(remaining)+6)
	for k, v := range remaining {
		m[k] = v
	}
	m["service.name"] = serviceName
	m["sentinel.scenario"] = scenario
	m["sentinel.run_id"] = runID
	m["cloud.provider"] = cloudProvider
	if synthetic == 1 {
		m["sentinel.synthetic"] = "true"
	} else {
		m["sentinel.synthetic"] = "false"
	}
	m["contract_version"] = contractVersion
	return m
}

// severityNumberUint8 clamps to bronze's UInt8 SeverityNumber column. OTLP severity is
// 0..=24, well within range; the model field is int32 only because OTLP's wire type is
// int32, so this guards the theoretical out-of-range case rather than wrapping it.
func severityNumberUint8(n int32) uint8 {
	if n < 0 || n > 255 {
		return 0
	}
	return uint8(n)
}

// bronzeStatusCode maps this collector's OK/ERROR convention to the contrib/bronze
// "Ok"/"Error" StatusCode strings (collector-rust's clickhouse_exporter.rs uses the same
// mapping). OTLP's Unset is already collapsed to OK upstream in transform/trace.go.
func bronzeStatusCode(code string) string {
	if code == "ERROR" {
		return "Error"
	}
	return "Ok"
}
