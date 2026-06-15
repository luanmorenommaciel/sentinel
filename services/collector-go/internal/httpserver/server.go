package httpserver

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"sentinel/collector/internal/chstore"
)

type Server struct {
	store  *chstore.Store
	server *http.Server
}

func New(port string, store *chstore.Store) *Server {
	mux := http.NewServeMux()
	s := &Server{store: store}

	mux.HandleFunc("/health", s.health)
	mux.HandleFunc("/ready", s.ready)
	mux.Handle("/metrics", promhttp.Handler())

	s.server = &http.Server{
		Addr:         ":" + port,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}
	return s
}

func (s *Server) ListenAndServe() error { return s.server.ListenAndServe() }

func (s *Server) Shutdown(ctx context.Context) error { return s.server.Shutdown(ctx) }

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	if err := s.store.Ready(ctx); err != nil {
		component := "clickhouse"
		reason := err.Error()
		if ctx.Err() != nil {
			reason = "ping timed out after 2s"
		}
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"status":    "not_ready",
			"component": component,
			"reason":    reason,
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(body) //nolint:errcheck
}
