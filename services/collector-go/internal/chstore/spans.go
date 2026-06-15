package chstore

import (
	"context"
	"fmt"

	"sentinel/collector/internal/model"
)

func (s *Store) insertSpans(ctx context.Context, spans []model.Span) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO otel_spans (
		trace_id, span_id, parent_span_id, service_name, name,
		start_unix_nano, end_unix_nano, status_code,
		attributes, resource_attributes, contract_version, ingested_at
	)`)
	if err != nil {
		return fmt.Errorf("insertSpans prepare: %w", err)
	}
	for _, sp := range spans {
		if err := batch.Append(
			sp.TraceID,
			sp.SpanID,
			sp.ParentSpanID,
			sp.ServiceName,
			sp.Name,
			sp.StartUnixNano,
			sp.EndUnixNano,
			sp.StatusCode,
			sp.Attributes,
			sp.ResourceAttributes,
			sp.ContractVersion,
			sp.IngestedAt,
		); err != nil {
			return fmt.Errorf("insertSpans append: %w", err)
		}
	}
	return batch.Send()
}
