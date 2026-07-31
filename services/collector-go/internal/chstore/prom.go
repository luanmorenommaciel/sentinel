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
		Buckets:   []float64{1, 10, 50, 100, 250, 500, 750, 1000, 2000, 5000},
	}, []string{"signal"})

	insertErrors = prometheus.NewCounterVec(prometheus.CounterOpts{
		Namespace: "sentinel",
		Name:      "ch_insert_errors_total",
		Help:      "Total ClickHouse insert errors after all retry attempts.",
	}, []string{"signal"})

	storedSignals = prometheus.NewCounterVec(prometheus.CounterOpts{
		Namespace: "sentinel",
		Name:      "storage_signals_total",
		Help:      "Signals completed by the storage stage, labeled by outcome.",
	}, []string{"signal", "outcome"})
)

func init() {
	prometheus.MustRegister(flushTotal, flushSize, insertErrors, storedSignals)
}
