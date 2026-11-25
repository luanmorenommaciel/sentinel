# Sentinel dashboard context

This language describes the read-only end-user dashboard's view of telemetry.

## Language

**Error span**:
A span whose recorded status is `Error`.
_Avoid_: Alert

**Alert**:
An authoritative verdict produced by an alerting rule or system. An error span alone is not an alert.
