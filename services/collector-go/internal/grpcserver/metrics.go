package grpcserver

import (
	"context"
	"log/slog"

	collectormetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"

	"sentinel/collector/internal/transform"
)

type metricsReceiver struct {
	collectormetrics.UnimplementedMetricsServiceServer
	sender          Sender
	expectedVersion string
}

func (r *metricsReceiver) Export(
	ctx context.Context,
	req *collectormetrics.ExportMetricsServiceRequest,
) (*collectormetrics.ExportMetricsServiceResponse, error) {
	metrics := transform.MetricsRequest(req)
	for _, m := range metrics {
		if r.expectedVersion != "" && m.ContractVersion != r.expectedVersion {
			slog.Default().Warn("contract_version mismatch",
				"expected", r.expectedVersion,
				"received", m.ContractVersion,
				"service", m.ServiceName,
			)
		}
		slog.Default().Debug("metric received",
			"service", m.ServiceName,
			"name", m.MetricName,
			"type", m.MetricType,
			"value", m.Value,
		)
		r.sender.SendMetric(m)
	}
	slog.Default().Info("metrics export accepted", "count", len(metrics))
	return &collectormetrics.ExportMetricsServiceResponse{}, nil
}
