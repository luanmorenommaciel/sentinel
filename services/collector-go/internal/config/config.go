package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	GRPCPort                string
	HTTPPort                string
	ClickHouseDSN           string
	Target                  string
	BatchSize               int
	FlushInterval           time.Duration
	LogFormat               string
	ExpectedContractVersion string
	GRPCTLSCertFile         string
	GRPCTLSKeyFile          string
	RateLimitRPS            int
	GRPCValidation          string
}

// Target destinations for the collector's hot path (ADR-0009).
const (
	// TargetBronze writes the live path into sentinel.* (the equalized default).
	TargetBronze = "bronze"
	// TargetNormalized writes the opt-in default.* schema + otel_metrics_1m MV.
	TargetNormalized = "normalized"
)

func Load() Config {
	return Config{
		GRPCPort:                getEnv("GRPC_PORT", "4317"),
		HTTPPort:                getEnv("HTTP_PORT", "8080"),
		ClickHouseDSN:           getEnv("CLICKHOUSE_DSN", "clickhouse://otelgen:otelgen_secret@localhost:9000/sentinel"),
		Target:                  getEnv("CLICKHOUSE_TARGET", TargetBronze),
		BatchSize:               getEnvInt("BATCH_SIZE", 100),
		FlushInterval:           time.Duration(getEnvInt("FLUSH_INTERVAL_MS", 500)) * time.Millisecond,
		LogFormat:               getEnv("LOG_FORMAT", "json"),
		ExpectedContractVersion: getEnv("CONTRACT_VERSION", "1.0.0"),
		GRPCTLSCertFile:         getEnv("GRPC_TLS_CERT_FILE", ""),
		GRPCTLSKeyFile:          getEnv("GRPC_TLS_KEY_FILE", ""),
		RateLimitRPS:            getEnvInt("RATE_LIMIT_RPS", 0),    // 0 = disabled
		GRPCValidation:          getEnv("GRPC_VALIDATION", "warn"), // off | warn | strict (EP3.3, parity w/ Rust)
	}
}

func (c Config) Validate() error {
	if c.BatchSize <= 0 {
		return fmt.Errorf("BATCH_SIZE must be > 0, got %d", c.BatchSize)
	}
	if c.FlushInterval <= 0 {
		return fmt.Errorf("FLUSH_INTERVAL_MS must be > 0, got %s", c.FlushInterval)
	}
	if c.Target != TargetBronze && c.Target != TargetNormalized {
		return fmt.Errorf("CLICKHOUSE_TARGET must be %q or %q, got %q", TargetBronze, TargetNormalized, c.Target)
	}
	if c.GRPCValidation != "off" && c.GRPCValidation != "warn" && c.GRPCValidation != "strict" {
		return fmt.Errorf("GRPC_VALIDATION must be off, warn, or strict, got %q", c.GRPCValidation)
	}
	if c.LogFormat != "json" && c.LogFormat != "text" {
		return fmt.Errorf("LOG_FORMAT must be json or text, got %q", c.LogFormat)
	}
	if c.RateLimitRPS < 0 {
		return fmt.Errorf("RATE_LIMIT_RPS must be >= 0, got %d", c.RateLimitRPS)
	}
	return nil
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}
