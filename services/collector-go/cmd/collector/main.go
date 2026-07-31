package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"sentinel/collector/internal/chstore"
	"sentinel/collector/internal/config"
	"sentinel/collector/internal/grpcserver"
	"sentinel/collector/internal/httpserver"
)

func main() {
	cfg := config.Load()
	if err := cfg.Validate(); err != nil {
		slog.Error("invalid configuration", "error", err)
		os.Exit(2)
	}

	var handler slog.Handler
	if cfg.LogFormat == "text" {
		handler = slog.NewTextHandler(os.Stdout, nil)
	} else {
		handler = slog.NewJSONHandler(os.Stdout, nil)
	}
	logger := slog.New(handler)
	slog.SetDefault(logger)

	store, err := chstore.New(cfg.ClickHouseDSN, cfg.Target, cfg.BatchSize, cfg.FlushInterval, logger)
	if err != nil {
		logger.Error("failed to connect to ClickHouse", "error", err)
		os.Exit(1)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	store.Start(ctx)

	grpcOpts := []grpc.ServerOption{
		grpc.UnaryInterceptor(grpcserver.RateLimitInterceptor(cfg.RateLimitRPS)),
	}
	if tlsOpt, err := grpcserver.TLSOption(cfg.GRPCTLSCertFile, cfg.GRPCTLSKeyFile); err != nil {
		logger.Error("failed to load TLS credentials", "error", err)
		os.Exit(1)
	} else if tlsOpt != nil {
		grpcOpts = append(grpcOpts, tlsOpt)
		logger.Info("gRPC TLS enabled", "cert", cfg.GRPCTLSCertFile)
	}
	grpcSrv := grpcserver.New(store, cfg.ExpectedContractVersion, grpcserver.ParseValidation(cfg.GRPCValidation), grpcOpts...)
	httpSrv := httpserver.New(cfg.HTTPPort, store)

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		logger.Info("gRPC server starting", "port", cfg.GRPCPort)
		if err := grpcSrv.ListenAndServe(cfg.GRPCPort); err != nil {
			logger.Error("gRPC server stopped", "error", err)
		}
	}()
	go func() {
		logger.Info("HTTP server starting", "port", cfg.HTTPPort)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("HTTP server stopped", "error", err)
		}
	}()

	<-quit
	logger.Info("shutting down")

	// Stop accepting new gRPC calls; wait for in-flight to complete.
	grpcSrv.GracefulStop()

	// Signal flush goroutines to drain and exit.
	cancel()
	store.Close() //nolint:errcheck

	shutCtx, shutCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutCancel()
	httpSrv.Shutdown(shutCtx) //nolint:errcheck

	logger.Info("shutdown complete")
}
