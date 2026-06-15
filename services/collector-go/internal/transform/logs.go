package transform

import (
	"time"

	"sentinel/collector/internal/model"

	collectorlogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
)

func LogsRequest(req *collectorlogs.ExportLogsServiceRequest) []model.Log {
	now := time.Now().UTC()
	var logs []model.Log

	for _, rl := range req.GetResourceLogs() {
		resAttrs := resourceToMap(rl.GetResource())
		svcName := serviceNameFromResource(resAttrs)
		contractVer := contractVersionFromResource(resAttrs)

		for _, sl := range rl.GetScopeLogs() {
			for _, lr := range sl.GetLogRecords() {
				logs = append(logs, model.Log{
					TimeUnixNano:       int64(lr.GetTimeUnixNano()),
					ServiceName:        svcName,
					SeverityText:       lr.GetSeverityText(),
					SeverityNumber:     int32(lr.GetSeverityNumber()),
					Body:               anyValueToString(lr.GetBody()),
					TraceID:            nullableHex(lr.GetTraceId()),
					SpanID:             nullableHex(lr.GetSpanId()),
					Attributes:         kvToMap(lr.GetAttributes()),
					ResourceAttributes: resAttrs,
					ContractVersion:    contractVer,
					IngestedAt:         now,
				})
			}
		}
	}
	return logs
}

func anyValueToString(av *commonv1.AnyValue) string {
	if av == nil {
		return ""
	}
	if sv, ok := av.GetValue().(*commonv1.AnyValue_StringValue); ok {
		return sv.StringValue
	}
	return av.String()
}
