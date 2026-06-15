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
		ResourceSpans: []*tracev1.ResourceSpans{
			{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{
						kv("service.name", "pubsub-ingestion-topic"),
						kv("cloud.provider", "gcp"),
						kv("sentinel.scenario", "baseline"),
					},
				},
				ScopeSpans: []*tracev1.ScopeSpans{
					{
						Spans: []*tracev1.Span{
							{
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
							},
						},
					},
				},
			},
		},
	}

	spans := transform.TraceRequest(req)

	if len(spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(spans))
	}
	s := spans[0]

	if s.TraceID != "0822e8f36c031199972a846916419f82" {
		t.Errorf("trace_id: got %q", s.TraceID)
	}
	if s.SpanID != "17fc695a07a0ca6e" {
		t.Errorf("span_id: got %q", s.SpanID)
	}
	if s.ParentSpanID != nil {
		t.Errorf("parent_span_id: expected nil, got %q", *s.ParentSpanID)
	}
	if s.ServiceName != "pubsub-ingestion-topic" {
		t.Errorf("service_name: got %q", s.ServiceName)
	}
	if s.Name != "messaging.operation" {
		t.Errorf("name: got %q", s.Name)
	}
	if s.StatusCode != "OK" {
		t.Errorf("status_code: got %q", s.StatusCode)
	}
	if s.Attributes["component.name"] != "messaging.ingestion_topic" {
		t.Errorf("attributes: got %v", s.Attributes)
	}
	if s.ResourceAttributes["cloud.provider"] != "gcp" {
		t.Errorf("resource_attributes: got %v", s.ResourceAttributes)
	}
}

func TestTraceRequest_ErrorStatus(t *testing.T) {
	req := &collectortrace.ExportTraceServiceRequest{
		ResourceSpans: []*tracev1.ResourceSpans{
			{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
				},
				ScopeSpans: []*tracev1.ScopeSpans{
					{
						Spans: []*tracev1.Span{
							{
								TraceId: make([]byte, 16),
								SpanId:  make([]byte, 8),
								Status:  &tracev1.Status{Code: tracev1.Status_STATUS_CODE_ERROR},
							},
						},
					},
				},
			},
		},
	}

	spans := transform.TraceRequest(req)
	if len(spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(spans))
	}
	if spans[0].StatusCode != "ERROR" {
		t.Errorf("expected ERROR, got %q", spans[0].StatusCode)
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
