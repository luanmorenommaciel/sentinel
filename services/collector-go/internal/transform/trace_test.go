package transform_test

import (
	"testing"

	"sentinel/collector/internal/transform"

	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	resourcev1 "go.opentelemetry.io/proto/otlp/resource/v1"
	tracev1 "go.opentelemetry.io/proto/otlp/trace/v1"
)

func TestTraceRequest_HappyPath(t *testing.T) {
	traceIDBytes, _ := hexToBytes("0822e8f36c031199972a846916419f82")
	spanIDBytes, _ := hexToBytes("17fc695a07a0ca6e")

	req := &collectortrace.ExportTraceServiceRequest{
		ResourceSpans: []*tracev1.ResourceSpans{{
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
			ScopeSpans: []*tracev1.ScopeSpans{{
				Spans: []*tracev1.Span{{
					TraceId:           traceIDBytes,
					SpanId:            spanIDBytes,
					ParentSpanId:      nil,
					Name:              "messaging.operation",
					StartTimeUnixNano: 1700000000000000000,
					EndTimeUnixNano:   1700000000030032131,
					Status:            &tracev1.Status{Code: tracev1.Status_STATUS_CODE_OK},
					Attributes: []*commonv1.KeyValue{
						kv("component.name", "messaging.ingestion_topic"),
					},
				}},
			}},
		}},
	}

	spans := transform.TraceRequest(req)

	if len(spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(spans))
	}
	s := spans[0]

	if s.TraceId != "0822e8f36c031199972a846916419f82" {
		t.Errorf("TraceId: got %q", s.TraceId)
	}
	if s.SpanId != "17fc695a07a0ca6e" {
		t.Errorf("SpanId: got %q", s.SpanId)
	}
	if s.ParentSpanId != "" {
		t.Errorf("ParentSpanId: expected empty, got %q", s.ParentSpanId)
	}
	if s.ServiceName != "pubsub-ingestion-topic" {
		t.Errorf("ServiceName: got %q", s.ServiceName)
	}
	if s.SpanName != "messaging.operation" {
		t.Errorf("SpanName: got %q", s.SpanName)
	}
	if s.Duration != 30032131 {
		t.Errorf("Duration: got %d, want 30032131", s.Duration)
	}
	if s.StatusCode != "OK" {
		t.Errorf("StatusCode: got %q", s.StatusCode)
	}
	// hoisted resource-attribute fields
	if s.SentinelScenario != "baseline" {
		t.Errorf("SentinelScenario: got %q", s.SentinelScenario)
	}
	if s.SentinelRunId != "golden-fixed-run" {
		t.Errorf("SentinelRunId: got %q", s.SentinelRunId)
	}
	if s.CloudProvider != "gcp" {
		t.Errorf("CloudProvider: got %q", s.CloudProvider)
	}
	if s.SentinelSynthetic != 1 {
		t.Errorf("SentinelSynthetic: got %d, want 1", s.SentinelSynthetic)
	}
	// hoisted keys must NOT appear in the remainder map
	if _, ok := s.ResourceAttributes["sentinel.scenario"]; ok {
		t.Errorf("ResourceAttributes should not contain hoisted key sentinel.scenario")
	}
	if _, ok := s.ResourceAttributes["service.name"]; ok {
		t.Errorf("ResourceAttributes should not contain hoisted key service.name")
	}
	// non-hoisted key must remain
	if s.ResourceAttributes["cloud.region"] != "us-central1" {
		t.Errorf("ResourceAttributes[cloud.region]: got %q", s.ResourceAttributes["cloud.region"])
	}
	if s.SpanAttributes["component.name"] != "messaging.ingestion_topic" {
		t.Errorf("SpanAttributes: got %v", s.SpanAttributes)
	}
}

func TestTraceRequest_ErrorStatus(t *testing.T) {
	req := &collectortrace.ExportTraceServiceRequest{
		ResourceSpans: []*tracev1.ResourceSpans{{
			Resource: &resourcev1.Resource{
				Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
			},
			ScopeSpans: []*tracev1.ScopeSpans{{
				Spans: []*tracev1.Span{{
					TraceId: make([]byte, 16),
					SpanId:  make([]byte, 8),
					Status:  &tracev1.Status{Code: tracev1.Status_STATUS_CODE_ERROR},
				}},
			}},
		}},
	}

	spans := transform.TraceRequest(req)
	if len(spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(spans))
	}
	if spans[0].StatusCode != "ERROR" {
		t.Errorf("expected ERROR, got %q", spans[0].StatusCode)
	}
}

func TestTraceRequest_SentinelSynthetic_False(t *testing.T) {
	req := &collectortrace.ExportTraceServiceRequest{
		ResourceSpans: []*tracev1.ResourceSpans{{
			Resource: &resourcev1.Resource{
				Attributes: []*commonv1.KeyValue{
					kv("service.name", "svc"),
					kv("sentinel.synthetic", "false"),
				},
			},
			ScopeSpans: []*tracev1.ScopeSpans{{
				Spans: []*tracev1.Span{{
					TraceId: make([]byte, 16),
					SpanId:  make([]byte, 8),
				}},
			}},
		}},
	}

	spans := transform.TraceRequest(req)
	if len(spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(spans))
	}
	if spans[0].SentinelSynthetic != 0 {
		t.Errorf("SentinelSynthetic: expected 0 for 'false', got %d", spans[0].SentinelSynthetic)
	}
}

func TestTraceRequest_EmptyRequest(t *testing.T) {
	spans := transform.TraceRequest(&collectortrace.ExportTraceServiceRequest{})
	if len(spans) != 0 {
		t.Errorf("expected 0 spans, got %d", len(spans))
	}
}

func TestTraceRequest_NilRequest(t *testing.T) {
	spans := transform.TraceRequest(nil)
	if len(spans) != 0 {
		t.Errorf("expected 0 spans for nil request, got %d", len(spans))
	}
}

// helpers

func kv(key, value string) *commonv1.KeyValue {
	return &commonv1.KeyValue{
		Key:   key,
		Value: &commonv1.AnyValue{Value: &commonv1.AnyValue_StringValue{StringValue: value}},
	}
}

func hexToBytes(s string) ([]byte, error) {
	b := make([]byte, len(s)/2)
	for i := range b {
		hi := hexNibble(s[2*i])
		lo := hexNibble(s[2*i+1])
		b[i] = (hi << 4) | lo
	}
	return b, nil
}

func hexNibble(c byte) byte {
	switch {
	case c >= '0' && c <= '9':
		return c - '0'
	case c >= 'a' && c <= 'f':
		return c - 'a' + 10
	default:
		return 0
	}
}
