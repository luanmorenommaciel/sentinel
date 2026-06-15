package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	GRPCPort               string
	HTTPPort               string
	ClickHouseDSN          string
	BatchSize              int
	FlushInterval          time.Duration
	LogFormat              string
	ExpectedContractVersion string
	GRPCTLSCertFile        string
	GRPCTLSKeyFile         string
	RateLimitRPS           int
}

func Load() Config {
	return Config{
		GRPCPort:                getEnv("GRPC_PORT", "4317"),
		HTTPPort:                getEnv("HTTP_PORT", "8080"),
		ClickHouseDSN:           getEnv("CLICKHOUSE_DSN", "clickhouse://otelgen:otelgen_secret@localhost:9000/sentinel"),
		BatchSize:               getEnvInt("BATCH_SIZE", 100),
		FlushInterval:           time.Duration(getEnvInt("FLUSH_INTERVAL_MS", 500)) * time.Millisecond,
		LogFormat:               getEnv("LOG_FORMAT", "json"),
		ExpectedContractVersion: getEnv("CONTRACT_VERSION", "1.0.0"),
		GRPCTLSCertFile:         getEnv("GRPC_TLS_CERT_FILE", ""),
		GRPCTLSKeyFile:          getEnv("GRPC_TLS_KEY_FILE", ""),
		RateLimitRPS:            getEnvInt("RATE_LIMIT_RPS", 0), // 0 = disabled
	}
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
