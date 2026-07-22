// sender is a manual integration test client.
// Run with: go run ./cmd/sender [host:port]
// Sends one span, one log, and one metric with known non-zero IDs,
// then prints the SQL queries to verify in ClickHouse.
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

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
)

// Known non-zero IDs — easy to grep in ClickHouse.
//
//	trace_id : 0badc0decafebabe0123456789abcdef
//	span_id  : deadbeefcafe0001
var (
	traceID = []byte{0x0b, 0xad, 0xc0, 0xde, 0xca, 0xfe, 0xba, 0xbe,
		0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef}
	spanID = []byte{0xde, 0xad, 0xbe, 0xef, 0xca, 0xfe, 0x00, 0x01}
)

func main() {
	target := "localhost:4317"
	if len(os.Args) > 1 {
		target = os.Args[1]
	}

	conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("dial %s: %v", target, err)
	}
	defer conn.Close() //nolint:errcheck

	ctx := context.Background()
	now := uint64(time.Now().UnixNano())

	resource := &resourcev1.Resource{
		Attributes: []*commonv1.KeyValue{
			attr("service.name", "sender-test"),
			attr("contract_version", "1.0.0"),
			attr("cloud.provider", "gcp"),
		},
	}

	sendSpan(ctx, conn, resource, now)
	sendLog(ctx, conn, resource, now)
	sendMetric(ctx, conn, resource, now)

	fmt.Println()
	fmt.Println("Verifique no ClickHouse (http://localhost:8123/play):")
	fmt.Println()
	fmt.Println("  SELECT TraceId, SpanId, SpanName, ServiceName")
	fmt.Println("  FROM bronze.otel_traces")
	fmt.Println("  WHERE ServiceName = 'sender-test';")
	fmt.Println()
	fmt.Println("  SELECT TraceId, SpanId, Body, SeverityText")
	fmt.Println("  FROM bronze.otel_logs")
	fmt.Println("  WHERE ServiceName = 'sender-test';")
	fmt.Println()
	fmt.Println("  SELECT MetricName, Value")
	fmt.Println("  FROM bronze.otel_metrics_gauge")
	fmt.Println("  WHERE ServiceName = 'sender-test';")
	fmt.Println()
	fmt.Println("Expected trace_id : 0badc0decafebabe0123456789abcdef")
	fmt.Println("Expected span_id  : deadbeefcafe0001")
}

func sendSpan(ctx context.Context, conn *grpc.ClientConn, res *resourcev1.Resource, now uint64) {
	_, err := collectortrace.NewTraceServiceClient(conn).Export(ctx,
		&collectortrace.ExportTraceServiceRequest{
			ResourceSpans: []*tracev1.ResourceSpans{{
				Resource: res,
				ScopeSpans: []*tracev1.ScopeSpans{{
					Spans: []*tracev1.Span{{
						TraceId:           traceID,
						SpanId:            spanID,
						Name:              "sender.test_span",
						StartTimeUnixNano: now,
						EndTimeUnixNano:   now + 30_000_000,
						Status:            &tracev1.Status{Code: tracev1.Status_STATUS_CODE_OK},
						Attributes: []*commonv1.KeyValue{
							attr("http.method", "GET"),
							attr("http.status_code", "200"),
						},
					}},
				}},
			}},
		},
	)
	if err != nil {
		log.Fatalf("export traces: %v", err)
	}
	fmt.Printf("[span]   trace_id=0badc0decafebabe0123456789abcdef  span_id=deadbeefcafe0001  name=sender.test_span\n")
}

func sendLog(ctx context.Context, conn *grpc.ClientConn, res *resourcev1.Resource, now uint64) {
	_, err := collectorlogs.NewLogsServiceClient(conn).Export(ctx,
		&collectorlogs.ExportLogsServiceRequest{
			ResourceLogs: []*logsv1.ResourceLogs{{
				Resource: res,
				ScopeLogs: []*logsv1.ScopeLogs{{
					LogRecords: []*logsv1.LogRecord{{
						TimeUnixNano:   now,
						SeverityText:   "INFO",
						SeverityNumber: logsv1.SeverityNumber_SEVERITY_NUMBER_INFO,
						Body:           anyStr("sender integration test — IDs nao sao zero"),
						TraceId:        traceID,
						SpanId:         spanID,
					}},
				}},
			}},
		},
	)
	if err != nil {
		log.Fatalf("export logs: %v", err)
	}
	fmt.Printf("[log]    body=\"sender integration test — IDs nao sao zero\"\n")
}

func sendMetric(ctx context.Context, conn *grpc.ClientConn, res *resourcev1.Resource, now uint64) {
	_, err := collectormetrics.NewMetricsServiceClient(conn).Export(ctx,
		&collectormetrics.ExportMetricsServiceRequest{
			ResourceMetrics: []*metricsv1.ResourceMetrics{{
				Resource: res,
				ScopeMetrics: []*metricsv1.ScopeMetrics{{
					Metrics: []*metricsv1.Metric{{
						Name: "sender.test_gauge",
						Data: &metricsv1.Metric_Gauge{
							Gauge: &metricsv1.Gauge{
								DataPoints: []*metricsv1.NumberDataPoint{{
									TimeUnixNano: now,
									Value:        &metricsv1.NumberDataPoint_AsDouble{AsDouble: 42.0},
									Attributes:   []*commonv1.KeyValue{attr("env", "integration-test")},
								}},
							},
						},
					}},
				}},
			}},
		},
	)
	if err != nil {
		log.Fatalf("export metrics: %v", err)
	}
	fmt.Printf("[metric] name=sender.test_gauge  type=gauge  value=42.0\n")
}

func attr(key, val string) *commonv1.KeyValue {
	return &commonv1.KeyValue{
		Key:   key,
		Value: &commonv1.AnyValue{Value: &commonv1.AnyValue_StringValue{StringValue: val}},
	}
}

func anyStr(s string) *commonv1.AnyValue {
	return &commonv1.AnyValue{Value: &commonv1.AnyValue_StringValue{StringValue: s}}
}
