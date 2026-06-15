package transform

import (
	"strconv"
	"time"

	"sentinel/collector/internal/model"

	collectormetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	metricsv1 "go.opentelemetry.io/proto/otlp/metrics/v1"
)

func MetricsRequest(req *collectormetrics.ExportMetricsServiceRequest) []model.Metric {
	now := time.Now().UTC()
	var metrics []model.Metric

	for _, rm := range req.GetResourceMetrics() {
		resAttrs := resourceToMap(rm.GetResource())
		svcName := serviceNameFromResource(resAttrs)
		contractVer := contractVersionFromResource(resAttrs)

		for _, sm := range rm.GetScopeMetrics() {
			for _, m := range sm.GetMetrics() {
				metrics = append(metrics, extractDataPoints(m, svcName, contractVer, resAttrs, now)...)
			}
		}
	}
	return metrics
}

func extractDataPoints(
	m *metricsv1.Metric,
	svcName, contractVer string,
	resAttrs map[string]string,
	now time.Time,
) []model.Metric {
	var out []model.Metric

	switch d := m.GetData().(type) {
	case *metricsv1.Metric_Gauge:
		for _, dp := range d.Gauge.GetDataPoints() {
			out = append(out, model.Metric{
				TimeUnixNano:       int64(dp.GetTimeUnixNano()),
				ServiceName:        svcName,
				Name:               m.GetName(),
				Type:               "gauge",
				Value:              dp.GetAsDouble(),
				Attributes:         kvToMap(dp.GetAttributes()),
				ResourceAttributes: resAttrs,
				ContractVersion:    contractVer,
				IngestedAt:         now,
			})
		}
	case *metricsv1.Metric_Sum:
		for _, dp := range d.Sum.GetDataPoints() {
			out = append(out, model.Metric{
				TimeUnixNano:       int64(dp.GetTimeUnixNano()),
				ServiceName:        svcName,
				Name:               m.GetName(),
				Type:               "sum",
				Value:              dp.GetAsDouble(),
				Attributes:         kvToMap(dp.GetAttributes()),
				ResourceAttributes: resAttrs,
				ContractVersion:    contractVer,
				IngestedAt:         now,
			})
		}
	case *metricsv1.Metric_Histogram:
		// Each histogram data point is stored as one row per bucket boundary.
		// bucket_le attribute holds the upper bound; value holds the cumulative count.
		for _, dp := range d.Histogram.GetDataPoints() {
			dpAttrs := kvToMap(dp.GetAttributes())
			bounds := dp.GetExplicitBounds()
			counts := dp.GetBucketCounts()
			for i, bound := range bounds {
				attrs := make(map[string]string, len(dpAttrs)+1)
				for k, v := range dpAttrs {
					attrs[k] = v
				}
				attrs["bucket_le"] = strconv.FormatFloat(bound, 'f', -1, 64)
				var count float64
				if i < len(counts) {
					count = float64(counts[i])
				}
				out = append(out, model.Metric{
					TimeUnixNano:       int64(dp.GetTimeUnixNano()),
					ServiceName:        svcName,
					Name:               m.GetName(),
					Type:               "histogram",
					Value:              count,
					Attributes:         attrs,
					ResourceAttributes: resAttrs,
					ContractVersion:    contractVer,
					IngestedAt:         now,
				})
			}
			// +Inf bucket (total count)
			infAttrs := make(map[string]string, len(dpAttrs)+1)
			for k, v := range dpAttrs {
				infAttrs[k] = v
			}
			infAttrs["bucket_le"] = "+Inf"
			var infCount float64
			if len(counts) > 0 {
				infCount = float64(counts[len(counts)-1])
			}
			out = append(out, model.Metric{
				TimeUnixNano:       int64(dp.GetTimeUnixNano()),
				ServiceName:        svcName,
				Name:               m.GetName(),
				Type:               "histogram",
				Value:              infCount,
				Attributes:         infAttrs,
				ResourceAttributes: resAttrs,
				ContractVersion:    contractVer,
				IngestedAt:         now,
			})
		}
	}
	return out
}
