package chstore

import (
	"context"
	"fmt"

	"sentinel/collector/internal/model"
)

func (s *Store) insertSpans(ctx context.Context, spans []model.Span) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO otel_traces (
		Timestamp, TraceId, SpanId, ParentSpanId, SpanName,
		ServiceName, SentinelScenario, SentinelRunId, CloudProvider, SentinelSynthetic,
		Duration, StatusCode, ContractVersion,
		SpanAttributes, ResourceAttributes
	)`)
	if err != nil {
		return fmt.Errorf("insertSpans prepare: %w", err)
	}
	for _, sp := range spans {
		if err := batch.Append(
			sp.Timestamp,
			sp.TraceId,
			sp.SpanId,
			sp.ParentSpanId,
			sp.SpanName,
			sp.ServiceName,
			sp.SentinelScenario,
			sp.SentinelRunId,
			sp.CloudProvider,
			sp.SentinelSynthetic,
			sp.Duration,
			sp.StatusCode,
			sp.ContractVersion,
			sp.SpanAttributes,
			sp.ResourceAttributes,
		); err != nil {
			return fmt.Errorf("insertSpans append: %w", err)
		}
	}
	return batch.Send()
}
