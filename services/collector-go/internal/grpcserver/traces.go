package grpcserver

import (
	"context"
	"log/slog"

	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"

	"sentinel/collector/internal/transform"
)

type traceReceiver struct {
	collectortrace.UnimplementedTraceServiceServer
	sender          Sender
	expectedVersion string
}

func (r *traceReceiver) Export(
	ctx context.Context,
	req *collectortrace.ExportTraceServiceRequest,
) (*collectortrace.ExportTraceServiceResponse, error) {
	spans := transform.TraceRequest(req)
	for _, s := range spans {
		if r.expectedVersion != "" && s.ContractVersion != r.expectedVersion {
			slog.Default().Warn("contract_version mismatch",
				"expected", r.expectedVersion,
				"received", s.ContractVersion,
				"service", s.ServiceName,
			)
		}
		slog.Default().Debug("span received",
			"trace_id", s.TraceId,
			"span_id", s.SpanId,
			"service", s.ServiceName,
			"name", s.SpanName,
		)
		r.sender.SendSpan(s)
	}
	slog.Default().Info("trace export accepted", "count", len(spans))
	return &collectortrace.ExportTraceServiceResponse{}, nil
}
