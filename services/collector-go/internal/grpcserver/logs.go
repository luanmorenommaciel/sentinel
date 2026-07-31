package grpcserver

import (
	"context"
	"log/slog"

	collectorlogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"sentinel/collector/internal/model"
	"sentinel/collector/internal/transform"
)

type logsReceiver struct {
	collectorlogs.UnimplementedLogsServiceServer
	sender          Sender
	expectedVersion string
	validation      Validation
}

func (r *logsReceiver) Export(
	ctx context.Context,
	req *collectorlogs.ExportLogsServiceRequest,
) (*collectorlogs.ExportLogsServiceResponse, error) {
	logs := transform.LogsRequest(req)
	addSignals("logs", "received", len(logs))
	accepted := make([]model.Log, 0, len(logs))
	var rejected int64
	for _, l := range logs {
		if r.validation != ValidationOff {
			if err := checkContract(l.ServiceName, l.SentinelScenario, l.SentinelRunId,
				l.CloudProvider, l.ContractVersion, r.expectedVersion); err != nil {
				if r.validation == ValidationStrict {
					rejected++
					slog.Default().Warn("contract validation failed — dropping log",
						"error", err, "service", l.ServiceName, "mode", "strict")
					continue
				}
				slog.Default().Warn("contract validation failed — exporting anyway",
					"error", err, "service", l.ServiceName, "mode", "warn")
			}
		}
		slog.Default().Debug("log received",
			"service", l.ServiceName,
			"severity", l.SeverityText,
			"body", l.Body,
		)
		accepted = append(accepted, l)
	}
	if err := r.sender.SendLogs(accepted); err != nil {
		addSignals("logs", "backpressure_rejected", len(accepted))
		slog.Default().Error("logs export rejected — buffer full", "error", err, "count", len(accepted))
		return nil, status.Error(codes.ResourceExhausted, "collector buffer full")
	}
	addSignals("logs", "accepted", len(accepted))
	addSignals("logs", "contract_rejected", int(rejected))
	slog.Default().Debug("logs export accepted", "received", len(logs), "accepted", len(accepted), "rejected", rejected)
	resp := &collectorlogs.ExportLogsServiceResponse{}
	if rejected > 0 {
		resp.PartialSuccess = &collectorlogs.ExportLogsPartialSuccess{
			RejectedLogRecords: rejected,
			ErrorMessage:       "signals rejected by strict contract validation",
		}
	}
	return resp, nil
}
