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
		ResourceLogs: []*logsv1.ResourceLogs{{
			Resource: &resourcev1.Resource{
				Attributes: []*commonv1.KeyValue{
					kv("service.name", "pubsub-ingestion-topic"),
					kv("cloud.provider", "gcp"),
					kv("sentinel.scenario", "baseline"),
					kv("sentinel.run_id", "golden-fixed-run"),
					kv("sentinel.synthetic", "true"),
					kv("cloud.region", "us-central1"),
				},
			},
			ScopeLogs: []*logsv1.ScopeLogs{{
				LogRecords: []*logsv1.LogRecord{{
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
				}},
			}},
		}},
	}

	logs := transform.LogsRequest(req)

	if len(logs) != 1 {
		t.Fatalf("expected 1 log, got %d", len(logs))
	}
	l := logs[0]

	wantNano := int64(1700000000000000000)
	if l.Timestamp.UnixNano() != wantNano {
		t.Errorf("Timestamp: got %d, want %d", l.Timestamp.UnixNano(), wantNano)
	}
	if l.SeverityText != "INFO" {
		t.Errorf("SeverityText: got %q", l.SeverityText)
	}
	if l.SeverityNumber != 9 {
		t.Errorf("SeverityNumber: got %d", l.SeverityNumber)
	}
	if l.Body != "Request completed successfully." {
		t.Errorf("Body: got %q", l.Body)
	}
	if l.TraceId != "0822e8f36c031199972a846916419f82" {
		t.Errorf("TraceId: got %q", l.TraceId)
	}
	if l.SpanId != "17fc695a07a0ca6e" {
		t.Errorf("SpanId: got %q", l.SpanId)
	}
	// hoisted fields
	if l.SentinelScenario != "baseline" {
		t.Errorf("SentinelScenario: got %q", l.SentinelScenario)
	}
	if l.SentinelRunId != "golden-fixed-run" {
		t.Errorf("SentinelRunId: got %q", l.SentinelRunId)
	}
	if l.CloudProvider != "gcp" {
		t.Errorf("CloudProvider: got %q", l.CloudProvider)
	}
	if l.SentinelSynthetic != 1 {
		t.Errorf("SentinelSynthetic: got %d, want 1", l.SentinelSynthetic)
	}
	// hoisted keys must NOT be in remainder map
	if _, ok := l.ResourceAttributes["sentinel.scenario"]; ok {
		t.Errorf("ResourceAttributes should not contain hoisted key sentinel.scenario")
	}
	// non-hoisted key must remain
	if l.ResourceAttributes["cloud.region"] != "us-central1" {
		t.Errorf("ResourceAttributes[cloud.region]: got %q", l.ResourceAttributes["cloud.region"])
	}
}

func TestLogsRequest_NilBody(t *testing.T) {
	req := &collectorlogs.ExportLogsServiceRequest{
		ResourceLogs: []*logsv1.ResourceLogs{{
			Resource: &resourcev1.Resource{
				Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
			},
			ScopeLogs: []*logsv1.ScopeLogs{{
				LogRecords: []*logsv1.LogRecord{
					{TimeUnixNano: 1, Body: nil},
				},
			}},
		}},
	}

	logs := transform.LogsRequest(req)
	if len(logs) != 1 {
		t.Fatalf("expected 1 log, got %d", len(logs))
	}
	if logs[0].Body != "" {
		t.Errorf("expected empty body, got %q", logs[0].Body)
	}
}
