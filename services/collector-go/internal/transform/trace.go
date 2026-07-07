package transform

import (
	"time"

	"sentinel/collector/internal/model"

	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	tracev1 "go.opentelemetry.io/proto/otlp/trace/v1"
)

func TraceRequest(req *collectortrace.ExportTraceServiceRequest) []model.Span {
	var spans []model.Span

	for _, rs := range req.GetResourceSpans() {
		resAttrs := resourceToMap(rs.GetResource())
		svcName := serviceNameFromResource(resAttrs)
		contractVer := contractVersionFromResource(resAttrs)

		for _, ss := range rs.GetScopeSpans() {
			for _, s := range ss.GetSpans() {
				startNano := int64(s.GetStartTimeUnixNano())
				endNano := int64(s.GetEndTimeUnixNano())
				spans = append(spans, model.Span{
					Timestamp:          time.Unix(0, startNano).UTC(),
					TraceId:            hexBytes(s.GetTraceId()),
					SpanId:             hexBytes(s.GetSpanId()),
					ParentSpanId:       emptyHex(s.GetParentSpanId()),
					SpanName:           s.GetName(),
					ServiceName:        svcName,
					SentinelScenario:   sentinelScenario(resAttrs),
					SentinelRunId:      sentinelRunId(resAttrs),
					CloudProvider:      cloudProvider(resAttrs),
					SentinelSynthetic:  sentinelSynthetic(resAttrs),
					Duration:           endNano - startNano,
					StatusCode:         spanStatus(s.GetStatus()),
					ContractVersion:    contractVer,
					SpanAttributes:     kvToMap(s.GetAttributes()),
					ResourceAttributes: remainingResourceAttrs(resAttrs),
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
