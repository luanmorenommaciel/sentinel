package grpcserver

import "github.com/prometheus/client_golang/prometheus"

var signalLifecycle = prometheus.NewCounterVec(prometheus.CounterOpts{
	Namespace: "sentinel",
	Name:      "signals_total",
	Help:      "OTLP signals by lifecycle state at the receive boundary.",
}, []string{"signal", "state"})

func init() {
	prometheus.MustRegister(signalLifecycle)
}

func addSignals(signal, state string, count int) {
	if count > 0 {
		signalLifecycle.WithLabelValues(signal, state).Add(float64(count))
	}
}
