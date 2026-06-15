package transform

import (
	"time"

	"sentinel/collector/internal/model"

	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	tracev1 "go.opentelemetry.io/proto/otlp/trace/v1"
)

func TraceRequest(req *collectortrace.ExportTraceServiceRequest) []model.Span {
	now := time.Now().UTC()
	var spans []model.Span

	for _, rs := range req.GetResourceSpans() {
		resAttrs := resourceToMap(rs.GetResource())
		svcName := serviceNameFromResource(resAttrs)
		contractVer := contractVersionFromResource(resAttrs)

		for _, ss := range rs.GetScopeSpans() {
			for _, s := range ss.GetSpans() {
				spans = append(spans, model.Span{
					TraceID:            hexBytes(s.GetTraceId()),
					SpanID:             hexBytes(s.GetSpanId()),
					ParentSpanID:       nullableHex(s.GetParentSpanId()),
					ServiceName:        svcName,
					Name:               s.GetName(),
					StartUnixNano:      int64(s.GetStartTimeUnixNano()),
					EndUnixNano:        int64(s.GetEndTimeUnixNano()),
					StatusCode:         spanStatus(s.GetStatus()),
					Attributes:         kvToMap(s.GetAttributes()),
					ResourceAttributes: resAttrs,
					ContractVersion:    contractVer,
					IngestedAt:         now,
				})
			}
		}
	}
	return spans
}

func spanStatus(status *tracev1.Status) string {
	if status == nil {
		return "OK"
	}
	if status.Code == tracev1.Status_STATUS_CODE_ERROR {
		return "ERROR"
	}
	return "OK"
}
