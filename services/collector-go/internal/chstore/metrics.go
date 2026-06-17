package chstore

import (
	"context"
	"fmt"

	"sentinel/collector/internal/model"
)

func (s *Store) insertMetrics(ctx context.Context, metrics []model.Metric) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO otel_metrics (
		Timestamp, MetricName, MetricType, Value,
		ServiceName, SentinelScenario, SentinelRunId, CloudProvider, SentinelSynthetic,
		ContractVersion, Attributes, ResourceAttributes
	)`)
	if err != nil {
		return fmt.Errorf("insertMetrics prepare: %w", err)
	}
	for _, m := range metrics {
		if err := batch.Append(
			m.Timestamp,
			m.MetricName,
			m.MetricType,
			m.Value,
			m.ServiceName,
			m.SentinelScenario,
			m.SentinelRunId,
			m.CloudProvider,
			m.SentinelSynthetic,
			m.ContractVersion,
			m.Attributes,
			m.ResourceAttributes,
		); err != nil {
			return fmt.Errorf("insertMetrics append: %w", err)
		}
	}
	return batch.Send()
}
