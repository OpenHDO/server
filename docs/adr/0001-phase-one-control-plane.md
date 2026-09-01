# ADR 0001: Phase 1 in-memory control-plane seams

- Status: accepted
- Date: 2026-09-01

## Context

The server needs a useful Phase 1 foundation before a transport or persistence
layer exists. The control plane must validate its boundaries, expose typed
domain state, and make command processing observable and testable without
coupling core code to HTTP, WebSocket, SQLite, or a third-party framework.

## Decision

- Configuration enters through a small versioned key/value boundary and is
  converted to a typed `Configuration`. Environment variables are one adapter;
  file and CLI adapters can feed the same loader later.
- `Logger` emits JSON lines with a timestamp, level, component, event, and
  fields. Its clock and output are injectable for deterministic tests.
- `Device` and `DeviceId` are validated value/domain objects. `DeviceRegistry`
  is the in-memory repository and returns deterministic ID ordering.
- `CommandMessage` and `EventMessage` are versioned message envelopes with
  typed variants, IDs, and correlation IDs. `ControlPlane` is the small service
  layer/message router: it applies commands to the registry, publishes events
  synchronously to subscribers, and returns a request-reply result.
- Subscriber failures are logged and isolated from other subscribers. There is
  no durable message store, retry queue, or dead-letter channel until a
  persistence/transport requirement makes one necessary.

## Consequences

The current path is local and synchronous, which keeps behavior easy to test
and leaves clear adapters for a future public transport. These C++ message
types are not yet wire contracts; adding a remote transport requires a
versioned schema/codec under `contracts/v1/` and explicit size, timeout,
authentication, and reconnect policies.
