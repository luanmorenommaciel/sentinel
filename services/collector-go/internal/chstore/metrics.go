package chstore

import (
	"context"
	"fmt"

	"sentinel/collector/internal/model"
)

func (s *Store) insertMetrics(ctx context.Context, metrics []model.Metric) error {
	batch, err := s.conn.PrepareBatch(ctx, `INSERT INTO otel_metrics (
		time_unix_nano, service_name, name, type, value,
		attributes, resource_attributes, contract_version, ingested_at
	)`)
	if err != nil {
		return fmt.Errorf("insertMetrics prepare: %w", err)
	}
	for _, m := range metrics {
		if err := batch.Append(
			m.TimeUnixNano,
			m.ServiceName,
			m.Name,
			m.Type,
			m.Value,
			m.Attributes,
			m.ResourceAttributes,
			m.ContractVersion,
			m.IngestedAt,
		); err != nil {
			return fmt.Errorf("insertMetrics append: %w", err)
		}
	}
	return batch.Send()
}
