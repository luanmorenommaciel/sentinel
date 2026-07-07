package transform

import (
	"encoding/hex"
	"fmt"
	"strconv"

	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	resourcev1 "go.opentelemetry.io/proto/otlp/resource/v1"
)

// hoistedKeys are the resource-attribute keys promoted to first-class columns.
// They are extracted individually and removed from the ResourceAttributes map,
// mirroring the Rust collector's schema design.
var hoistedKeys = map[string]bool{
	"service.name":        true,
	"sentinel.scenario":   true,
	"sentinel.run_id":     true,
	"cloud.provider":      true,
	"sentinel.synthetic":  true,
}

func kvToMap(kvs []*commonv1.KeyValue) map[string]string {
	m := make(map[string]string, len(kvs))
	for _, kv := range kvs {
		if kv == nil {
			continue
		}
		switch v := kv.Value.GetValue().(type) {
		case *commonv1.AnyValue_StringValue:
			m[kv.Key] = v.StringValue
		case *commonv1.AnyValue_BoolValue:
			if v.BoolValue {
				m[kv.Key] = "true"
			} else {
				m[kv.Key] = "false"
			}
		case *commonv1.AnyValue_IntValue:
			m[kv.Key] = strconv.FormatInt(v.IntValue, 10)
		case *commonv1.AnyValue_DoubleValue:
			m[kv.Key] = strconv.FormatFloat(v.DoubleValue, 'f', -1, 64)
		default:
			m[kv.Key] = fmt.Sprint(kv.Value.GetValue())
		}
	}
	return m
}

func resourceToMap(r *resourcev1.Resource) map[string]string {
	if r == nil {
		return map[string]string{}
	}
	return kvToMap(r.Attributes)
}

// remainingResourceAttrs returns resource attributes with hoisted keys removed.
func remainingResourceAttrs(res map[string]string) map[string]string {
	m := make(map[string]string, len(res))
	for k, v := range res {
		if !hoistedKeys[k] {
			m[k] = v
		}
	}
	return m
}

func hexBytes(b []byte) string {
	if len(b) == 0 {
		return ""
	}
	return hex.EncodeToString(b)
}

// emptyHex returns "" for empty or all-zero bytes (root span / absent correlation IDs).
func emptyHex(b []byte) string {
	s := hexBytes(b)
	if s == "" {
		return ""
	}
	for _, c := range b {
		if c != 0 {
			return s
		}
	}
	return ""
}

func serviceNameFromResource(res map[string]string) string {
	if v, ok := res["service.name"]; ok && v != "" {
		return v
	}
	return "unknown"
}

func sentinelScenario(res map[string]string) string  { return res["sentinel.scenario"] }
func sentinelRunId(res map[string]string) string     { return res["sentinel.run_id"] }
func cloudProvider(res map[string]string) string     { return res["cloud.provider"] }

func sentinelSynthetic(res map[string]string) uint8 {
	if res["sentinel.synthetic"] == "true" {
		return 1
	}
	return 0
}

func contractVersionFromResource(res map[string]string) string {
	if v, ok := res["contract_version"]; ok && v != "" {
		return v
	}
	return "1.0.0"
}
