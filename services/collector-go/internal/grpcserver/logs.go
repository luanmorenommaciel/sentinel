package grpcserver

import (
	"context"
	"log/slog"

	collectorlogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"

	"sentinel/collector/internal/transform"
)

type logsReceiver struct {
	collectorlogs.UnimplementedLogsServiceServer
	sender          Sender
	expectedVersion string
}

func (r *logsReceiver) Export(
	ctx context.Context,
	req *collectorlogs.ExportLogsServiceRequest,
) (*collectorlogs.ExportLogsServiceResponse, error) {
	logs := transform.LogsRequest(req)
	for _, l := range logs {
		if r.expectedVersion != "" && l.ContractVersion != r.expectedVersion {
			slog.Default().Warn("contract_version mismatch",
				"expected", r.expectedVersion,
				"received", l.ContractVersion,
				"service", l.ServiceName,
			)
		}
		slog.Default().Debug("log received",
			"service", l.ServiceName,
			"severity", l.SeverityText,
			"body", l.Body,
		)
		r.sender.SendLog(l)
	}
	slog.Default().Info("logs export accepted", "count", len(logs))
	return &collectorlogs.ExportLogsServiceResponse{}, nil
}
