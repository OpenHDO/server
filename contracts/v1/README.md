# OpenHDO protocol contracts v1

This directory contains the language-neutral contracts shared by the server,
OpenHDO Linker processes, agents, plugins, and clients.

The JSON Schema files define the logical message shape, not a transport. A
transport may be local or remote, but remote traffic must provide encryption,
authentication, bounded message sizes, timeouts, and reconnect handling.

## Compatibility rules

- `v` is the protocol major version. A receiver must reject unsupported major
  versions before processing a payload.
- `type` is a stable domain message name such as `link.register`,
  `light.command.power`, or `light.state.changed`.
- Unknown optional fields may be ignored; required field changes require a new
  major contract.
- Every message has a unique `id`, an ISO-8601 UTC timestamp, a `source`, and
  an object `payload`.
- Commands and results use `correlation_id` to connect a response or event to
  a request. A command's `command_id` identifies the logical command, while
  `idempotency_key` is reused for retries of that same command.
- Discovery uses the same request/reply rule: `discovery.start` sets
  `correlation_id` equal to its own envelope `id`; candidate and completion
  messages repeat that id.

## Light v1

The first device capability contract is the RGB Light slice:

Light v1 is vendor-neutral and real-device oriented. It describes the Light
capability and its observable state, not a home-automation runtime, gateway,
simulator, or driver API. Driver/vendor provenance, when useful for operators,
belongs in non-normative integration documentation and must not add
vendor-specific fields to these messages.

- [`light-command.schema.json`](light-command.schema.json) defines
  `light.command.power`, `light.command.brightness`, and
  `light.command.rgb_color` envelope messages. Each command requires
  `correlation_id` in the envelope and `light_id`, `command_id`, and
  `idempotency_key` in its payload.
- [`light-state.schema.json`](light-state.schema.json) defines unsolicited
  `light.state.reported` snapshots and command-correlated
  `light.state.changed` events.
- [`light.schema.json`](light.schema.json) defines the shared value shapes:
  brightness is an integer intensity from 0 to 255, and `rgb_color` is an
  object with `r`, `g`, and `b` integer channels from 0 to 255. This is
  OpenHDO's own vendor-neutral contract semantics; it does not import a
  runtime or gateway model.

Linker discovery may attach devices to the existing `link.register` payload.
Each device has an abstract capability list; the Light descriptor is defined
by [`light-capability.schema.json`](light-capability.schema.json) and contains
only `power`, a brightness range of 0 to 255, optional `RGB`/`RGBW`/`CCT`
color modes, and an RGB channel range of 0 to 255. Device pairing, protocol,
DP mapping, vendor/model details, local keys, and real-device connections are
Linker concerns and are not part of the server contract.

`correlation_id` refers to the envelope `id` of the request being correlated.
For a command retry, the envelope `id` may change, but `command_id` and
`idempotency_key` remain unchanged. Receivers must not execute the same
logical command more than once for a repeated idempotency key within their
configured retention window. `light.state.changed` repeats the command
metadata so downstream consumers can reconcile state with the command.

All Light messages are ordinary v1 envelopes. Existing Linker registration
remains backward-compatible; its optional `devices` field carries the
vendor-neutral descriptors above. The schemas define logical messages, not a
runtime or HTTP/WebSocket transport, and are intentionally independent of the
server implementation language. New message types should be added with an
example and a compatibility test.

## Server-initiated Linker connection

The server can connect to a real Linker configured by an admin. The endpoint
registration body is `{ "host": "<IP>", "port": <port>, "minisecret": "<secret>" }`.
The server opens `ws://<host>:<port>/api/v1/linker` and sends the
`X-OpenHDO-Minisecret` header. The Linker verifies that header and sends a
`link.register` envelope first. Its `source` and manifest `id` must match.

After registration, both sides use the existing v1 envelopes: the Linker
sends state, command-result, and discovery-reply messages; the server sends
light commands and discovery starts. A lost connection is retried after five
seconds. The Linker endpoint is a real runtime boundary; the server does not
manufacture device or Linker data.

## Discovery v1

[`discovery.schema.json`](discovery.schema.json) defines the server-owned
discovery vertical slice:

- `discovery.start` carries a UUID `session_id` and integer `timeout_s` from 1
  through 60. Its envelope `correlation_id` must equal its envelope `id`.
- `discovery.candidate` carries only an abstract `candidate_id`, display name,
  `transport: "wifi"`, Light capabilities, and `requires_pairing`.
- `discovery.completed` carries the session UUID, `completed` or `failed`
  status, and a nullable error.

The server exposes authenticated POST/GET session endpoints and forwards the
start message over the existing Linker WebSocket. Sessions are process-local;
the server times out bounded scans and never manufactures candidates. Linker
pairing, vendor/model data, IPs, local keys, and DP fields are outside this
contract.
