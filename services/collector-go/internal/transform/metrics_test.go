package transform_test

import (
	"testing"

	"sentinel/collector/internal/transform"

	collectormetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	metricsv1 "go.opentelemetry.io/proto/otlp/metrics/v1"
	resourcev1 "go.opentelemetry.io/proto/otlp/resource/v1"
)

func TestMetricsRequest_Gauge(t *testing.T) {
	req := &collectormetrics.ExportMetricsServiceRequest{
		ResourceMetrics: []*metricsv1.ResourceMetrics{
			{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{
						kv("service.name", "pubsub-ingestion-topic"),
					},
				},
				ScopeMetrics: []*metricsv1.ScopeMetrics{
					{
						Metrics: []*metricsv1.Metric{
							{
								Name: "operation.latency_ms",
								Data: &metricsv1.Metric_Gauge{
									Gauge: &metricsv1.Gauge{
										DataPoints: []*metricsv1.NumberDataPoint{
											{
												TimeUnixNano: 1700000000000000000,
												Value:        &metricsv1.NumberDataPoint_AsDouble{AsDouble: 30.032},
												Attributes: []*commonv1.KeyValue{
													kv("component.name", "messaging.ingestion_topic"),
												},
											},
										},
									},
								},
							},
						},
					},
				},
			},
		},
	}

	metrics := transform.MetricsRequest(req)

	if len(metrics) != 1 {
		t.Fatalf("expected 1 metric, got %d", len(metrics))
	}
	m := metrics[0]

	if m.Name != "operation.latency_ms" {
		t.Errorf("name: got %q", m.Name)
	}
	if m.Type != "gauge" {
		t.Errorf("type: got %q", m.Type)
	}
	if m.Value != 30.032 {
		t.Errorf("value: got %f", m.Value)
	}
	if m.ServiceName != "pubsub-ingestion-topic" {
		t.Errorf("service_name: got %q", m.ServiceName)
	}
}

func TestMetricsRequest_Sum(t *testing.T) {
	req := &collectormetrics.ExportMetricsServiceRequest{
		ResourceMetrics: []*metricsv1.ResourceMetrics{
			{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
				},
				ScopeMetrics: []*metricsv1.ScopeMetrics{
					{
						Metrics: []*metricsv1.Metric{
							{
								Name: "operation.request_count",
								Data: &metricsv1.Metric_Sum{
									Sum: &metricsv1.Sum{
										DataPoints: []*metricsv1.NumberDataPoint{
											{
												TimeUnixNano: 1700000000000000000,
												Value:        &metricsv1.NumberDataPoint_AsDouble{AsDouble: 1.0},
											},
										},
									},
								},
							},
						},
					},
				},
			},
		},
	}

	metrics := transform.MetricsRequest(req)
	if len(metrics) != 1 {
		t.Fatalf("expected 1 metric, got %d", len(metrics))
	}
	if metrics[0].Type != "sum" {
		t.Errorf("type: expected sum, got %q", metrics[0].Type)
	}
}

func TestMetricsRequest_Histogram(t *testing.T) {
	req := &collectormetrics.ExportMetricsServiceRequest{
		ResourceMetrics: []*metricsv1.ResourceMetrics{
			{
				Resource: &resourcev1.Resource{
					Attributes: []*commonv1.KeyValue{kv("service.name", "svc")},
				},
				ScopeMetrics: []*metricsv1.ScopeMetrics{
					{
						Metrics: []*metricsv1.Metric{
							{
								Name: "request.duration",
								Data: &metricsv1.Metric_Histogram{
									Histogram: &metricsv1.Histogram{
										DataPoints: []*metricsv1.HistogramDataPoint{
											{
												TimeUnixNano:   1700000000000000000,
												ExplicitBounds: []float64{10, 50, 100},
												BucketCounts:   []uint64{2, 5, 8, 12},
											},
										},
									},
								},
							},
						},
					},
				},
			},
		},
	}

	metrics := transform.MetricsRequest(req)

	// 3 bounds + 1 +Inf = 4 rows
	if len(metrics) != 4 {
		t.Fatalf("expected 4 histogram rows, got %d", len(metrics))
	}
	for _, m := range metrics {
		if m.Type != "histogram" {
			t.Errorf("type: expected histogram, got %q", m.Type)
		}
		if m.Name != "request.duration" {
			t.Errorf("name: expected request.duration, got %q", m.Name)
		}
		if _, ok := m.Attributes["bucket_le"]; !ok {
			t.Errorf("bucket_le attribute missing")
		}
	}
	if m := metrics[3]; m.Attributes["bucket_le"] != "+Inf" {
		t.Errorf("last row bucket_le: expected +Inf, got %q", m.Attributes["bucket_le"])
	}
}

func TestMetricsRequest_EmptyRequest(t *testing.T) {
	metrics := transform.MetricsRequest(&collectormetrics.ExportMetricsServiceRequest{})
	if len(metrics) != 0 {
		t.Errorf("expected 0 metrics, got %d", len(metrics))
	}
}
