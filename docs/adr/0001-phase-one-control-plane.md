# ADR 0001: Phase 1 in-memory control-plane seams

- Status: accepted (Python runtime supersedes the frozen C++ implementation)
- Date: 2026-09-01

## Context

The server needs a useful Phase 1 foundation before a durable transport or
persistence layer exists. The control plane must validate its boundaries,
expose typed domain state, and make command processing observable and testable.
The active runtime is Python; C++ foundation code is retained only as frozen
reference material. The server must remain independent of vendor protocols and
real-device connections, which belong to Linkers.

## Decision

- `ServerSettings` is a versioned, validated environment boundary with a
  local-only default and an explicit token requirement for non-local binds.
- The Python runtime emits JSON lines with timestamp, level, component, event,
  and fields; credentials and vendor-specific data are not logged.
- Pydantic value/domain models validate Light identity, capability ranges,
  state, command payloads, envelopes, correlation IDs, and idempotency keys.
- `InMemoryLightRepository` is the process-local canonical Light registry.
  `LightService` is the application service coordinating Linker messages,
  command forwarding, request-reply results, idempotency, and event observers.
- FastAPI/Starlette HTTP and WebSocket adapters use those same typed models.
  `PATCH` is an ergonomic adapter; complete v1 command envelopes remain
  available through `POST`.
- Subscriber delivery is bounded and transient. There is no durable message
  store, retry queue, or dead-letter channel until a concrete reliability
  requirement makes one necessary.

## Consequences

The current repository path is process-local and easy to test while exposing
real HTTP/WebSocket boundaries. Normative wire contracts remain under
`contracts/v1/`; runtime models are an implementation boundary, not a second
SDK. The server accepts only abstract Linker registration/state/result data.
Adding durable or remote transport requires explicit size, timeout,
authentication, reconnect, and delivery policies.
