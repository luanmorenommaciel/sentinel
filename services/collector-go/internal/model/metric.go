package model

import "time"

type Metric struct {
	TimeUnixNano       int64
	ServiceName        string
	Name               string
	Type               string
	Value              float64
	Attributes         map[string]string
	ResourceAttributes map[string]string
	ContractVersion    string
	IngestedAt         time.Time
}
