package model

import "time"

type Span struct {
	TraceID            string
	SpanID             string
	ParentSpanID       *string
	ServiceName        string
	Name               string
	StartUnixNano      int64
	EndUnixNano        int64
	StatusCode         string
	Attributes         map[string]string
	ResourceAttributes map[string]string
	ContractVersion    string
	IngestedAt         time.Time
}
