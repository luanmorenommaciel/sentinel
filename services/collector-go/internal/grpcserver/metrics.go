package grpcserver

import (
	"context"
	"log/slog"

	collectormetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"sentinel/collector/internal/model"
	"sentinel/collector/internal/transform"
)

type metricsReceiver struct {
	collectormetrics.UnimplementedMetricsServiceServer
	sender          Sender
	expectedVersion string
	validation      Validation
}

func (r *metricsReceiver) Export(
	ctx context.Context,
	req *collectormetrics.ExportMetricsServiceRequest,
) (*collectormetrics.ExportMetricsServiceResponse, error) {
	metrics := transform.MetricsRequest(req)
	addSignals("metrics", "received", len(metrics))
	accepted := make([]model.Metric, 0, len(metrics))
	var rejected int64
	for _, m := range metrics {
		if r.validation != ValidationOff {
			if err := checkContract(m.ServiceName, m.SentinelScenario, m.SentinelRunId,
				m.CloudProvider, m.ContractVersion, r.expectedVersion); err != nil {
				if r.validation == ValidationStrict {
					rejected++
					slog.Default().Warn("contract validation failed — dropping metric",
						"error", err, "service", m.ServiceName, "mode", "strict")
					continue
				}
				slog.Default().Warn("contract validation failed — exporting anyway",
					"error", err, "service", m.ServiceName, "mode", "warn")
			}
		}
		slog.Default().Debug("metric received",
			"service", m.ServiceName,
			"name", m.MetricName,
			"type", m.MetricType,
			"value", m.Value,
		)
		accepted = append(accepted, m)
	}
	if err := r.sender.SendMetrics(accepted); err != nil {
		addSignals("metrics", "backpressure_rejected", len(accepted))
		slog.Default().Error("metrics export rejected — buffer full", "error", err, "count", len(accepted))
		return nil, status.Error(codes.ResourceExhausted, "collector buffer full")
	}
	addSignals("metrics", "accepted", len(accepted))
	addSignals("metrics", "contract_rejected", int(rejected))
	slog.Default().Debug("metrics export accepted", "received", len(metrics), "accepted", len(accepted), "rejected", rejected)
	resp := &collectormetrics.ExportMetricsServiceResponse{}
	if rejected > 0 {
		resp.PartialSuccess = &collectormetrics.ExportMetricsPartialSuccess{
			RejectedDataPoints: rejected,
			ErrorMessage:       "signals rejected by strict contract validation",
		}
	}
	return resp, nil
}
