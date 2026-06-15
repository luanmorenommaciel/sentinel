package chstore

import "github.com/prometheus/client_golang/prometheus"

var (
	flushTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Namespace: "sentinel",
		Name:      "batch_flush_total",
		Help:      "Total number of batch flushes, labeled by signal and status.",
	}, []string{"signal", "status"})

	flushSize = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "sentinel",
		Name:      "batch_flush_size",
		Help:      "Number of records per batch flush.",
		Buckets:   []float64{1, 5, 10, 25, 50, 100},
	}, []string{"signal"})

	insertErrors = prometheus.NewCounterVec(prometheus.CounterOpts{
		Namespace: "sentinel",
		Name:      "ch_insert_errors_total",
		Help:      "Total ClickHouse insert errors after all retry attempts.",
	}, []string{"signal"})
)

func init() {
	prometheus.MustRegister(flushTotal, flushSize, insertErrors)
}
