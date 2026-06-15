package grpcserver

import (
	"crypto/tls"
	"fmt"
	"net"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/reflection"

	collectorlogs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	collectormetrics "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"

	"sentinel/collector/internal/model"
)

// Sender accepts telemetry signals for buffered delivery to the store.
type Sender interface {
	SendSpan(model.Span)
	SendLog(model.Log)
	SendMetric(model.Metric)
}

type Server struct {
	grpc *grpc.Server
}

// New creates the gRPC server and registers all three OTLP service handlers.
// expectedContractVersion is logged as a warning when incoming telemetry carries
// a different contract_version resource attribute.
func New(sender Sender, expectedContractVersion string, opts ...grpc.ServerOption) *Server {
	srv := grpc.NewServer(opts...)

	collectortrace.RegisterTraceServiceServer(srv, &traceReceiver{sender: sender, expectedVersion: expectedContractVersion})
	collectorlogs.RegisterLogsServiceServer(srv, &logsReceiver{sender: sender, expectedVersion: expectedContractVersion})
	collectormetrics.RegisterMetricsServiceServer(srv, &metricsReceiver{sender: sender, expectedVersion: expectedContractVersion})

	reflection.Register(srv)

	return &Server{grpc: srv}
}

func (s *Server) ListenAndServe(port string) error {
	lis, err := net.Listen("tcp", ":"+port)
	if err != nil {
		return fmt.Errorf("grpc listen on :%s: %w", port, err)
	}
	return s.grpc.Serve(lis)
}

// Serve starts the gRPC server on an existing listener (used by tests).
func (s *Server) Serve(lis net.Listener) error { return s.grpc.Serve(lis) }

func (s *Server) GracefulStop() { s.grpc.GracefulStop() }

// TLSOption returns a grpc.ServerOption that enables TLS using the given
// cert and key files. Returns nil if either path is empty (insecure mode).
func TLSOption(certFile, keyFile string) (grpc.ServerOption, error) {
	if certFile == "" || keyFile == "" {
		return nil, nil
	}
	cert, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, fmt.Errorf("grpc TLS: load key pair: %w", err)
	}
	return grpc.Creds(credentials.NewTLS(&tls.Config{
		Certificates: []tls.Certificate{cert},
		MinVersion:   tls.VersionTLS12,
	})), nil
}
