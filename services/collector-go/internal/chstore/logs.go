package chstore

import (
	"context"
	"fmt"

	"sentinel/collector/internal/model"
)

func (s *Store) insertLogs(ctx context.Context, logs []model.Log) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO otel_logs (
		time_unix_nano, service_name, severity_text, severity_number, body,
		trace_id, span_id,
		attributes, resource_attributes, contract_version, ingested_at
	)`)
	if err != nil {
		return fmt.Errorf("insertLogs prepare: %w", err)
	}
	for _, l := range logs {
		if err := batch.Append(
			l.TimeUnixNano,
			l.ServiceName,
			l.SeverityText,
			l.SeverityNumber,
			l.Body,
			l.TraceID,
			l.SpanID,
			l.Attributes,
			l.ResourceAttributes,
			l.ContractVersion,
			l.IngestedAt,
		); err != nil {
			return fmt.Errorf("insertLogs append: %w", err)
		}
	}
	return batch.Send()
}
