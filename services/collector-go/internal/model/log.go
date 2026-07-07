package model

import "time"

type Log struct {
	Timestamp          time.Time
	ServiceName        string
	SentinelScenario   string
	SentinelRunId      string
	CloudProvider      string
	SentinelSynthetic  uint8 // 1=true, 0=false
	SeverityText       string
	SeverityNumber     int32
	Body               string
	TraceId            string // empty string if not in trace context
	SpanId             string // empty string if not in span context
	ContractVersion    string
	LogAttributes      map[string]string
	ResourceAttributes map[string]string // non-hoisted remainder
}
