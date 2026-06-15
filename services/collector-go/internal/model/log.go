package model

import "time"

type Log struct {
	TimeUnixNano       int64
	ServiceName        string
	SeverityText       string
	SeverityNumber     int32
	Body               string
	TraceID            *string
	SpanID             *string
	Attributes         map[string]string
	ResourceAttributes map[string]string
	ContractVersion    string
	IngestedAt         time.Time
}
