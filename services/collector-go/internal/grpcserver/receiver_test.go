package grpcserver_test

import (
	"context"
	"net"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	collectorlogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	collectormetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	logsv1 "go.opentelemetry.io/proto/otlp/logs/v1"
	metricsv1 "go.opentelemetry.io/proto/otlp/metrics/v1"
	resourcev1 "go.opentelemetry.io/proto/otlp/resource/v1"
	tracev1 "go.opentelemetry.io/proto/otlp/trace/v1"

	"sentinel/collector/internal/grpcserver"
	"sentinel/collector/internal/model"
)

// captureSender collects everything the gRPC handlers send.
type captureSender struct {
	spans   []model.Span
	logs    []model.Log
	metrics []model.Metric
}

func (c *captureSender) SendSpans(spans []model.Span) error {
	c.spans = append(c.spans, spans...)
	return nil
}
func (c *captureSender) SendLogs(logs []model.Log) error {
	c.logs = append(c.logs, logs...)
	return nil
}
func (c *captureSender) SendMetrics(metrics []model.Metric) error {
	c.metrics = append(c.metrics, metrics...)
	return nil
}

func startTestServer(t *testing.T, sender grpcserver.Sender) string {
	return startTestServerWithValidation(t, sender, grpcserver.ValidationOff)
}

func startTestServerWithValidation(t *testing.T, sender grpcserver.Sender, validation grpcserver.Validation) string {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	srv := grpcserver.New(sender, "1.0.0", validation)
	go srv.Serve(lis) //nolint:errcheck
	t.Cleanup(srv.GracefulStop)
	return lis.Addr().String()
}

func TestStrictValidationReportsPartialSuccess(t *testing.T) {
	capture := &captureSender{}
	addr := startTestServerWithValidation(t, capture, grpcserver.ValidationStrict)
	conn := dialTestServer(t, addr)

	resp, err := collectorlogs.NewLogsServiceClient(conn).Export(context.Background(),
		&collectorlogs.ExportLogsServiceRequest{ResourceLogs: []*logsv1.ResourceLogs{{
			Resource:  &resourcev1.Resource{Attributes: []*commonv1.KeyValue{kv("service.name", "invalid")}},
			ScopeLogs: []*logsv1.ScopeLogs{{LogRecords: []*logsv1.LogRecord{{Body: &commonv1.AnyValue{Value: &commonv1.AnyValue_StringValue{StringValue: "missing contract attrs"}}}}}},
		}}})
	if err != nil {
		t.Fatalf("Export: %v", err)
	}
	if resp.PartialSuccess == nil || resp.PartialSuccess.RejectedLogRecords != 1 {
		t.Fatalf("partial success=%v, want one rejected log", resp.PartialSuccess)
	}
	if len(capture.logs) != 0 {
		t.Fatalf("strict validation exported %d invalid logs", len(capture.logs))
	}
}

func dialTestServer(t *testing.T, addr string) *grpc.ClientConn {
	t.Helper()
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("dial %s: %v", addr, err)
	}
	t.Cleanup(func() { conn.Close() }) //nolint:errcheck
	return conn
}

func kv(key, val string) *commonv1.KeyValue {
	return &commonv1.KeyValue{
		Key:   key,
		Value: &commonv1.AnyValue{Value: &commonv1.AnyValue_StringValue{StringValue: val}},
	}
}

// TestTraceReceiver_NonZeroIDs is the core regression test for the "zeroed data" issue.
// It sends a span with explicitly non-zero trace/span/parent IDs over real gRPC
// and asserts that the hex strings received by the store are correct.
func TestTraceReceiver_NonZeroIDs(t *testing.T) {
	capture := &captureSender{}
	conn := dialTestServer(t, startTestServer(t, capture))

	traceID := []byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
		0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10}
	spanID := []byte{0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18}
	parentID := []byte{0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28}

	_, err := collectortrace.NewTraceServiceClient(conn).Export(
		context.Background(),
		&collectortrace.ExportTraceServiceRequest{
			ResourceSpans: []*tracev1.ResourceSpans{{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "test-svc")},
				},
				ScopeSpans: []*tracev1.ScopeSpans{{
					Spans: []*tracev1.Span{{
						TraceId:      traceID,
						SpanId:       spanID,
						ParentSpanId: parentID,
						Name:         "test.op",
						Status:       &tracev1.Status{Code: tracev1.Status_STATUS_CODE_OK},
					}},
				}},
			}},
		},
	)
	if err != nil {
		t.Fatalf("Export: %v", err)
	}

	if len(capture.spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(capture.spans))
	}
	s := capture.spans[0]

	if got, want := s.TraceId, "0102030405060708090a0b0c0d0e0f10"; got != want {
		t.Errorf("TraceId: got %q, want %q", got, want)
	}
	if got, want := s.SpanId, "1112131415161718"; got != want {
		t.Errorf("SpanId: got %q, want %q", got, want)
	}
	if got, want := s.ParentSpanId, "2122232425262728"; got != want {
		t.Errorf("ParentSpanId: got %q, want %q", got, want)
	}
	if s.ServiceName != "test-svc" {
		t.Errorf("ServiceName: got %q, want test-svc", s.ServiceName)
	}
}

func TestTraceReceiver_RootSpan_EmptyParent(t *testing.T) {
	capture := &captureSender{}
	conn := dialTestServer(t, startTestServer(t, capture))

	_, err := collectortrace.NewTraceServiceClient(conn).Export(
		context.Background(),
		&collectortrace.ExportTraceServiceRequest{
			ResourceSpans: []*tracev1.ResourceSpans{{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
				},
				ScopeSpans: []*tracev1.ScopeSpans{{
					Spans: []*tracev1.Span{{
						TraceId:      []byte{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
						SpanId:       []byte{1, 2, 3, 4, 5, 6, 7, 8},
						ParentSpanId: nil,
						Name:         "root.op",
					}},
				}},
			}},
		},
	)
	if err != nil {
		t.Fatalf("Export: %v", err)
	}

	if len(capture.spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(capture.spans))
	}
	if capture.spans[0].ParentSpanId != "" {
		t.Errorf("root span ParentSpanId should be empty, got %q", capture.spans[0].ParentSpanId)
	}
}

func TestTraceReceiver_AllZeroParent_TreatedAsRoot(t *testing.T) {
	capture := &captureSender{}
	conn := dialTestServer(t, startTestServer(t, capture))

	_, err := collectortrace.NewTraceServiceClient(conn).Export(
		context.Background(),
		&collectortrace.ExportTraceServiceRequest{
			ResourceSpans: []*tracev1.ResourceSpans{{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
				},
				ScopeSpans: []*tracev1.ScopeSpans{{
					Spans: []*tracev1.Span{{
						TraceId:      []byte{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
						SpanId:       []byte{1, 2, 3, 4, 5, 6, 7, 8},
						ParentSpanId: make([]byte, 8), // 8 zero bytes = no parent
						Name:         "root.op",
					}},
				}},
			}},
		},
	)
	if err != nil {
		t.Fatalf("Export: %v", err)
	}

	if len(capture.spans) != 1 {
		t.Fatalf("expected 1 span, got %d", len(capture.spans))
	}
	if capture.spans[0].ParentSpanId != "" {
		t.Errorf("all-zero ParentSpanId should be empty in store, got %q", capture.spans[0].ParentSpanId)
	}
}

func TestLogsReceiver_TraceAndSpanIDs(t *testing.T) {
	capture := &captureSender{}
	conn := dialTestServer(t, startTestServer(t, capture))

	traceID := []byte{0xde, 0xad, 0xbe, 0xef, 0xca, 0xfe, 0xba, 0xbe,
		0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef}
	spanID := []byte{0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88}

	_, err := collectorlogs.NewLogsServiceClient(conn).Export(
		context.Background(),
		&collectorlogs.ExportLogsServiceRequest{
			ResourceLogs: []*logsv1.ResourceLogs{{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "log-svc")},
				},
				ScopeLogs: []*logsv1.ScopeLogs{{
					LogRecords: []*logsv1.LogRecord{{
						SeverityText:   "INFO",
						SeverityNumber: logsv1.SeverityNumber_SEVERITY_NUMBER_INFO,
						Body: &commonv1.AnyValue{
							Value: &commonv1.AnyValue_StringValue{StringValue: "test log message"},
						},
						TraceId: traceID,
						SpanId:  spanID,
					}},
				}},
			}},
		},
	)
	if err != nil {
		t.Fatalf("Export: %v", err)
	}

	if len(capture.logs) != 1 {
		t.Fatalf("expected 1 log, got %d", len(capture.logs))
	}
	l := capture.logs[0]

	if got, want := l.TraceId, "deadbeefcafebabe0123456789abcdef"; got != want {
		t.Errorf("TraceId: got %q, want %q", got, want)
	}
	if got, want := l.SpanId, "1122334455667788"; got != want {
		t.Errorf("SpanId: got %q, want %q", got, want)
	}
	if l.Body != "test log message" {
		t.Errorf("Body: got %q, want test log message", l.Body)
	}
}

func TestMetricsReceiver_GaugeValue(t *testing.T) {
	capture := &captureSender{}
	conn := dialTestServer(t, startTestServer(t, capture))

	now := uint64(1700000000000000000)

	_, err := collectormetrics.NewMetricsServiceClient(conn).Export(
		context.Background(),
		&collectormetrics.ExportMetricsServiceRequest{
			ResourceMetrics: []*metricsv1.ResourceMetrics{{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "metric-svc")},
				},
				ScopeMetrics: []*metricsv1.ScopeMetrics{{
					Metrics: []*metricsv1.Metric{{
						Name: "latency.ms",
						Data: &metricsv1.Metric_Gauge{
							Gauge: &metricsv1.Gauge{
								DataPoints: []*metricsv1.NumberDataPoint{{
									TimeUnixNano: now,
									Value:        &metricsv1.NumberDataPoint_AsDouble{AsDouble: 99.9},
								}},
							},
						},
					}},
				}},
			}},
		},
	)
	if err != nil {
		t.Fatalf("Export: %v", err)
	}

	if len(capture.metrics) != 1 {
		t.Fatalf("expected 1 metric, got %d", len(capture.metrics))
	}
	m := capture.metrics[0]

	if m.MetricName != "latency.ms" {
		t.Errorf("MetricName: got %q, want latency.ms", m.MetricName)
	}
	if m.Value != 99.9 {
		t.Errorf("Value: got %f, want 99.9", m.Value)
	}
	if m.MetricType != "gauge" {
		t.Errorf("MetricType: got %q, want gauge", m.MetricType)
	}
	if m.ServiceName != "metric-svc" {
		t.Errorf("ServiceName: got %q, want metric-svc", m.ServiceName)
	}
}
