package transform

import (
	"time"

	"sentinel/collector/internal/model"

	collectorlogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
)

func LogsRequest(req *collectorlogs.ExportLogsServiceRequest) []model.Log {
	var logs []model.Log

	for _, rl := range req.GetResourceLogs() {
		resAttrs := resourceToMap(rl.GetResource())
		svcName := serviceNameFromResource(resAttrs)
		contractVer := contractVersionFromResource(resAttrs)

		for _, sl := range rl.GetScopeLogs() {
			for _, lr := range sl.GetLogRecords() {
				logs = append(logs, model.Log{
					Timestamp:          time.Unix(0, int64(lr.GetTimeUnixNano())).UTC(),
					ServiceName:        svcName,
					SentinelScenario:   sentinelScenario(resAttrs),
					SentinelRunId:      sentinelRunId(resAttrs),
					CloudProvider:      cloudProvider(resAttrs),
					SentinelSynthetic:  sentinelSynthetic(resAttrs),
					SeverityText:       lr.GetSeverityText(),
					SeverityNumber:     int32(lr.GetSeverityNumber()),
					Body:               anyValueToString(lr.GetBody()),
					TraceId:            emptyHex(lr.GetTraceId()),
					SpanId:             emptyHex(lr.GetSpanId()),
					ContractVersion:    contractVer,
					LogAttributes:      kvToMap(lr.GetAttributes()),
					ResourceAttributes: remainingResourceAttrs(resAttrs),
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
