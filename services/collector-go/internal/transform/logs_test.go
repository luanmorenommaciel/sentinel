package transform_test

import (
	"testing"

	"sentinel/collector/internal/transform"

	collectorlogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	logsv1 "go.opentelemetry.io/proto/otlp/logs/v1"
	resourcev1 "go.opentelemetry.io/proto/otlp/resource/v1"
)

func TestLogsRequest_HappyPath(t *testing.T) {
	traceIDBytes, _ := hexToBytes("0822e8f36c031199972a846916419f82")
	spanIDBytes, _ := hexToBytes("17fc695a07a0ca6e")

	req := &collectorlogs.ExportLogsServiceRequest{
		ResourceLogs: []*logsv1.ResourceLogs{
			{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{
						kv("service.name", "pubsub-ingestion-topic"),
						kv("cloud.provider", "gcp"),
					},
				},
				ScopeLogs: []*logsv1.ScopeLogs{
					{
						LogRecords: []*logsv1.LogRecord{
							{
								TimeUnixNano:   1700000000000000000,
								SeverityText:   "INFO",
								SeverityNumber: logsv1.SeverityNumber_SEVERITY_NUMBER_INFO,
								Body: &commonv1.AnyValue{
									Value: &commonv1.AnyValue_StringValue{StringValue: "Request completed successfully."},
								},
								TraceId: traceIDBytes,
								SpanId:  spanIDBytes,
								Attributes: []*commonv1.KeyValue{
									kv("component.name", "messaging.ingestion_topic"),
								},
							},
						},
					},
				},
			},
		},
	}

	logs := transform.LogsRequest(req)

	if len(logs) != 1 {
		t.Fatalf("expected 1 log, got %d", len(logs))
	}
	l := logs[0]

	if l.TimeUnixNano != 1700000000000000000 {
		t.Errorf("time_unix_nano: got %d", l.TimeUnixNano)
	}
	if l.SeverityText != "INFO" {
		t.Errorf("severity_text: got %q", l.SeverityText)
	}
	if l.SeverityNumber != 9 {
		t.Errorf("severity_number: got %d", l.SeverityNumber)
	}
	if l.Body != "Request completed successfully." {
		t.Errorf("body: got %q", l.Body)
	}
	if l.TraceID == nil || *l.TraceID != "0822e8f36c031199972a846916419f82" {
		t.Errorf("trace_id: got %v", l.TraceID)
	}
	if l.SpanID == nil || *l.SpanID != "17fc695a07a0ca6e" {
		t.Errorf("span_id: got %v", l.SpanID)
	}
}

func TestLogsRequest_NilBody(t *testing.T) {
	req := &collectorlogs.ExportLogsServiceRequest{
		ResourceLogs: []*logsv1.ResourceLogs{
			{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
				},
				ScopeLogs: []*logsv1.ScopeLogs{
					{
						LogRecords: []*logsv1.LogRecord{
							{TimeUnixNano: 1, Body: nil},
						},
					},
				},
			},
		},
	}

	logs := transform.LogsRequest(req)
	if len(logs) != 1 {
		t.Fatalf("expected 1 log, got %d", len(logs))
	}
	if logs[0].Body != "" {
		t.Errorf("expected empty body, got %q", logs[0].Body)
	}
}
