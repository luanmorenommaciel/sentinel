package config

import (
	"testing"
	"time"
)

func TestValidate(t *testing.T) {
	valid := Config{BatchSize: 1000, FlushInterval: 500 * time.Millisecond, Target: TargetBronze, GRPCValidation: "warn", LogFormat: "json"}
	if err := valid.Validate(); err != nil {
		t.Fatalf("valid config rejected: %v", err)
	}

	cases := []struct {
		name string
		edit func(*Config)
	}{
		{"batch", func(c *Config) { c.BatchSize = 0 }},
		{"flush", func(c *Config) { c.FlushInterval = 0 }},
		{"target", func(c *Config) { c.Target = "typo" }},
		{"validation", func(c *Config) { c.GRPCValidation = "maybe" }},
		{"format", func(c *Config) { c.LogFormat = "xml" }},
		{"rate", func(c *Config) { c.RateLimitRPS = -1 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cfg := valid
			tc.edit(&cfg)
			if err := cfg.Validate(); err == nil {
				t.Fatal("expected validation error")
			}
		})
	}
}
