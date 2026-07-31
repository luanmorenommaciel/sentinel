package grpcserver

import (
	"context"
	"log/slog"

	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"sentinel/collector/internal/model"
	"sentinel/collector/internal/transform"
)

type traceReceiver struct {
	collectortrace.UnimplementedTraceServiceServer
	sender          Sender
	expectedVersion string
	validation      Validation
}

func (r *traceReceiver) Export(
	ctx context.Context,
	req *collectortrace.ExportTraceServiceRequest,
) (*collectortrace.ExportTraceServiceResponse, error) {
	spans := transform.TraceRequest(req)
	addSignals("traces", "received", len(spans))
	accepted := make([]model.Span, 0, len(spans))
	var rejected int64
	for _, s := range spans {
		if r.validation != ValidationOff {
			if err := checkContract(s.ServiceName, s.SentinelScenario, s.SentinelRunId,
				s.CloudProvider, s.ContractVersion, r.expectedVersion); err != nil {
				if r.validation == ValidationStrict {
					rejected++
					slog.Default().Warn("contract validation failed — dropping span",
						"error", err, "service", s.ServiceName, "mode", "strict")
					continue
				}
				slog.Default().Warn("contract validation failed — exporting anyway",
					"error", err, "service", s.ServiceName, "mode", "warn")
			}
		}
		slog.Default().Debug("span received",
			"trace_id", s.TraceId,
			"span_id", s.SpanId,
			"service", s.ServiceName,
			"name", s.SpanName,
		)
		accepted = append(accepted, s)
	}
	if err := r.sender.SendSpans(accepted); err != nil {
		addSignals("traces", "backpressure_rejected", len(accepted))
		slog.Default().Error("trace export rejected — buffer full", "error", err, "count", len(accepted))
		return nil, status.Error(codes.ResourceExhausted, "collector buffer full")
	}
	addSignals("traces", "accepted", len(accepted))
	addSignals("traces", "contract_rejected", int(rejected))
	slog.Default().Debug("trace export accepted", "received", len(spans), "accepted", len(accepted), "rejected", rejected)
	resp := &collectortrace.ExportTraceServiceResponse{}
	if rejected > 0 {
		resp.PartialSuccess = &collectortrace.ExportTracePartialSuccess{
			RejectedSpans: rejected,
			ErrorMessage:  "signals rejected by strict contract validation",
		}
	}
	return resp, nil
}
