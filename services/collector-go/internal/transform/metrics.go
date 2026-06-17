package transform

import (
	"strconv"
	"time"

	"sentinel/collector/internal/model"

	collectormetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	metricsv1 "go.opentelemetry.io/proto/otlp/metrics/v1"
)

func MetricsRequest(req *collectormetrics.ExportMetricsServiceRequest) []model.Metric {
	var metrics []model.Metric

	for _, rm := range req.GetResourceMetrics() {
		resAttrs := resourceToMap(rm.GetResource())
		svcName := serviceNameFromResource(resAttrs)
		contractVer := contractVersionFromResource(resAttrs)

		for _, sm := range rm.GetScopeMetrics() {
			for _, m := range sm.GetMetrics() {
				metrics = append(metrics, extractDataPoints(m, svcName, contractVer, resAttrs)...)
			}
		}
	}
	return metrics
}

func extractDataPoints(
	m *metricsv1.Metric,
	svcName, contractVer string,
	resAttrs map[string]string,
) []model.Metric {
	var out []model.Metric

	remAttrs := remainingResourceAttrs(resAttrs)
	scenario := sentinelScenario(resAttrs)
	runID := sentinelRunId(resAttrs)
	cloud := cloudProvider(resAttrs)
	synthetic := sentinelSynthetic(resAttrs)

	switch d := m.GetData().(type) {
	case *metricsv1.Metric_Gauge:
		for _, dp := range d.Gauge.GetDataPoints() {
			out = append(out, model.Metric{
				Timestamp:          time.Unix(0, int64(dp.GetTimeUnixNano())).UTC(),
				MetricName:         m.GetName(),
				MetricType:         "gauge",
				Value:              dp.GetAsDouble(),
				ServiceName:        svcName,
				SentinelScenario:   scenario,
				SentinelRunId:      runID,
				CloudProvider:      cloud,
				SentinelSynthetic:  synthetic,
				ContractVersion:    contractVer,
				Attributes:         kvToMap(dp.GetAttributes()),
				ResourceAttributes: remAttrs,
			})
		}
	case *metricsv1.Metric_Sum:
		for _, dp := range d.Sum.GetDataPoints() {
			out = append(out, model.Metric{
				Timestamp:          time.Unix(0, int64(dp.GetTimeUnixNano())).UTC(),
				MetricName:         m.GetName(),
				MetricType:         "sum",
				Value:              dp.GetAsDouble(),
				ServiceName:        svcName,
				SentinelScenario:   scenario,
				SentinelRunId:      runID,
				CloudProvider:      cloud,
				SentinelSynthetic:  synthetic,
				ContractVersion:    contractVer,
				Attributes:         kvToMap(dp.GetAttributes()),
				ResourceAttributes: remAttrs,
			})
		}
	case *metricsv1.Metric_Histogram:
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
					Timestamp:          time.Unix(0, int64(dp.GetTimeUnixNano())).UTC(),
					MetricName:         m.GetName(),
					MetricType:         "histogram",
					Value:              count,
					ServiceName:        svcName,
					SentinelScenario:   scenario,
					SentinelRunId:      runID,
					CloudProvider:      cloud,
					SentinelSynthetic:  synthetic,
					ContractVersion:    contractVer,
					Attributes:         attrs,
					ResourceAttributes: remAttrs,
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
				Timestamp:          time.Unix(0, int64(dp.GetTimeUnixNano())).UTC(),
				MetricName:         m.GetName(),
				MetricType:         "histogram",
				Value:              infCount,
				ServiceName:        svcName,
				SentinelScenario:   scenario,
				SentinelRunId:      runID,
				CloudProvider:      cloud,
				SentinelSynthetic:  synthetic,
				ContractVersion:    contractVer,
				Attributes:         infAttrs,
				ResourceAttributes: remAttrs,
			})
		}
	}
	return out
}
