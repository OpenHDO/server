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

`correlation_id` refers to the envelope `id` of the request being correlated.
For a command retry, the envelope `id` may change, but `command_id` and
`idempotency_key` remain unchanged. Receivers must not execute the same
logical command more than once for a repeated idempotency key within their
configured retention window. `light.state.changed` repeats the command
metadata so downstream consumers can reconcile state with the command.

All Light messages are ordinary v1 envelopes, so existing envelope validation
and Linker registration remain unchanged. The schemas define logical messages,
not HTTP or WebSocket transport. New message types should be added with an
example and a compatibility test.
