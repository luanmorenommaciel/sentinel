package model

import "time"

type Metric struct {
	Timestamp          time.Time
	MetricName         string
	MetricType         string
	Value              float64
	ServiceName        string
	SentinelScenario   string
	SentinelRunId      string
	CloudProvider      string
	SentinelSynthetic  uint8 // 1=true, 0=false
	ContractVersion    string
	Attributes         map[string]string
	ResourceAttributes map[string]string // non-hoisted remainder
}
