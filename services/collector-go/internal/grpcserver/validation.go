package grpcserver

import "fmt"

// Validation is the receive-boundary contract-enforcement policy (EP3.3). It
// mirrors the Rust collector's contract.grpc_validation (src/grpc.rs,
// apply_validation): Off performs no checks; Warn logs each violation but exports
// the signal anyway; Strict drops the offending signal.
type Validation int

const (
	ValidationOff Validation = iota
	ValidationWarn
	ValidationStrict
)

// ParseValidation maps the config string to a policy, defaulting to Warn for any
// unrecognized value (matches the Rust default and the foreign-OTLP rationale:
// non-Sentinel telemetry legitimately lacks the sentinel.* keys, so Strict would
// drop it — hence Warn is the safe default).
func ParseValidation(s string) Validation {
	switch s {
	case "off":
		return ValidationOff
	case "strict":
		return ValidationStrict
	default:
		return ValidationWarn
	}
}

// checkContract validates the required Sentinel keys hoisted into typed columns.
// Parity with the Rust validate_service_name + validate_required_resource_keys:
// service.name non-empty and sentinel.scenario / sentinel.run_id / cloud.provider
// present, plus the contract_version match when an expected version is configured.
// sentinel.synthetic maps to a uint8 that is always 0/1, so it needs no check.
func checkContract(serviceName, scenario, runID, cloudProvider, contractVersion, expectedVersion string) error {
	switch {
	case serviceName == "":
		return fmt.Errorf("service.name must be non-empty")
	case scenario == "":
		return fmt.Errorf("missing required resource attribute: sentinel.scenario")
	case runID == "":
		return fmt.Errorf("missing required resource attribute: sentinel.run_id")
	case cloudProvider == "":
		return fmt.Errorf("missing required resource attribute: cloud.provider")
	case expectedVersion != "" && contractVersion != expectedVersion:
		return fmt.Errorf("contract_version mismatch: expected %s, got %s", expectedVersion, contractVersion)
	}
	return nil
}
