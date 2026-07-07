package chstore

import (
	"context"
	"fmt"

	"sentinel/collector/internal/model"
)

func (s *Store) insertLogs(ctx context.Context, logs []model.Log) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO otel_logs (
		Timestamp,
		ServiceName, SentinelScenario, SentinelRunId, CloudProvider, SentinelSynthetic,
		SeverityText, SeverityNumber, Body,
		TraceId, SpanId, ContractVersion,
		LogAttributes, ResourceAttributes
	)`)
	if err != nil {
		return fmt.Errorf("insertLogs prepare: %w", err)
	}
	for _, l := range logs {
		if err := batch.Append(
			l.Timestamp,
			l.ServiceName,
			l.SentinelScenario,
			l.SentinelRunId,
			l.CloudProvider,
			l.SentinelSynthetic,
			l.SeverityText,
			l.SeverityNumber,
			l.Body,
			l.TraceId,
			l.SpanId,
			l.ContractVersion,
			l.LogAttributes,
			l.ResourceAttributes,
		); err != nil {
			return fmt.Errorf("insertLogs append: %w", err)
		}
	}
	return batch.Send()
}
