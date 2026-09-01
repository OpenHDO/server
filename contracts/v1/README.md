# OpenHDO protocol contracts v1

This directory contains the language-neutral contracts shared by the server,
OpenHDO Linker processes, agents, plugins, and clients.

The JSON Schema files define the logical message shape, not a transport. A
transport may be local or remote, but remote traffic must provide encryption,
authentication, bounded message sizes, timeouts, and reconnect handling.

## Compatibility rules

- `v` is the protocol major version. A receiver must reject unsupported major
  versions before processing a payload.
- `type` is a stable domain message name such as `link.register` or
  `command.result`.
- Unknown optional fields may be ignored; required field changes require a new
  major contract.
- Every message has a unique `id`, an ISO-8601 UTC timestamp, a `source`, and
  an object `payload`.
- Commands and results use `correlation_id` to connect a response to a request.

The contract is deliberately small until the first end-to-end server/linker
flow is implemented. New message types should be added with an example and a
compatibility test.
