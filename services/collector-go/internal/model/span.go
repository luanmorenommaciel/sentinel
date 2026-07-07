package model

import "time"

type Span struct {
	Timestamp          time.Time
	TraceId            string
	SpanId             string
	ParentSpanId       string // empty string for root spans
	SpanName           string
	ServiceName        string
	SentinelScenario   string
	SentinelRunId      string
	CloudProvider      string
	SentinelSynthetic  uint8 // 1=true, 0=false
	Duration           int64 // end_unix_nano - start_unix_nano in nanoseconds
	StatusCode         string
	ContractVersion    string
	SpanAttributes     map[string]string
	ResourceAttributes map[string]string // non-hoisted remainder
}
