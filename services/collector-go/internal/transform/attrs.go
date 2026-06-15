package transform

import (
	"encoding/hex"
	"fmt"
	"strconv"

	commonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	resourcev1 "go.opentelemetry.io/proto/otlp/resource/v1"
)

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

func hexBytes(b []byte) string {
	if len(b) == 0 {
		return ""
	}
	return hex.EncodeToString(b)
}

// nullableHex returns nil for empty bytes (root span has no parent).
func nullableHex(b []byte) *string {
	s := hexBytes(b)
	if s == "" {
		return nil
	}
	// all-zero bytes means no parent span
	allZero := true
	for _, c := range b {
		if c != 0 {
			allZero = false
			break
		}
	}
	if allZero {
		return nil
	}
	return &s
}

func serviceNameFromResource(res map[string]string) string {
	if v, ok := res["service.name"]; ok && v != "" {
		return v
	}
	return "unknown"
}

func contractVersionFromResource(res map[string]string) string {
	if v, ok := res["contract_version"]; ok && v != "" {
		return v
	}
	return "1.0.0"
}
