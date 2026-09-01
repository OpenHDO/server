# OpenHDO Server — technical documentation

This document is limited to the server repository. Product-wide architecture,
repository ownership, naming, deployment roles, and roadmap live in the
[OpenHDO about repository](https://github.com/OpenHDO/about).

## Responsibility

`openhdo-server` is the central control plane. It is responsible for:

- shared domain state and orchestration rules;
- commands, events, policies, and execution history;
- the registry of devices, entities, capabilities, Linker sessions, agents,
  and plugins;
- the public HTTP API and WebSocket stream when those milestones land;
- persistence and migrations;
- authentication, authorization, audit records, and structured logs;
- hosting the built-in admin/configuration panel and server-side Logic and
  Linker modules.

The server must not contain radio, USB, serial, or device-specific protocol
drivers. Those run in an isolated `openhdo-linker` process close to the
hardware.

## Runtime direction

Python is the primary backend/runtime direction for the server, and React owns
the web panels. The existing C++ runtime/foundation remains buildable as a
frozen baseline but must not gain new API or runtime features. Rewriting the
server runtime and API in Python is a separate follow-up task; the v1
contracts remain language-neutral during that migration.

## Repository layout

```text
include/openhdo/     public C++ headers
src/core/            reusable runtime library
src/server/          openhdo-server entry point
src/cli/             ohdocli entry point
tests/               CTest smoke checks
contracts/v1/        language-neutral JSON contracts
web/                 built-in server admin/configuration panel shell
python/              stdlib-only protocol SDK reference
```

The server owns the source of truth. The built-in admin panel in `web/`, CLI,
Linkers, agents, and plugins are clients or isolated extensions; none may
treat dashboard state or SQLite tables as a public API. The reusable
`server-dashboard` client module is a separate client-facing consumer of the
server contracts. It is not the server's admin/configuration panel and is not
owned by this repository.

## Public contract

The first stable contract is the versioned envelope in
[`contracts/v1/envelope.schema.json`](contracts/v1/envelope.schema.json).
Linker registration is represented by
[`contracts/v1/link-manifest.schema.json`](contracts/v1/link-manifest.schema.json)
and the `link.register` example. The RGB Light slice is defined by
[`contracts/v1/light-command.schema.json`](contracts/v1/light-command.schema.json),
[`contracts/v1/light-state.schema.json`](contracts/v1/light-state.schema.json),
and the shared payload definitions in
[`contracts/v1/light.schema.json`](contracts/v1/light.schema.json).
Light brightness is an OpenHDO-defined integer intensity from 0 to 255; RGB
channels use the same 0 to 255 range.
Linker registration may include the vendor-neutral device capability descriptor
from [`contracts/v1/light-capability.schema.json`](contracts/v1/light-capability.schema.json);
pairing, protocol, DP mapping, vendor/model details, local keys, and real
device connections remain exclusively Linker responsibilities.

Compatibility rules:

1. Reject unsupported protocol major versions before processing payloads.
2. Keep message names stable and use `correlation_id` for command results.
3. Ignore unknown optional fields; breaking required changes require a new
   major contract.
4. Add a schema or payload definition, example, and compatibility test before
   making a message public.

The schema defines logical messages, not a transport. The eventual remote
transport must provide encryption, authentication, message-size limits,
timeouts, and reconnect behavior.

## Module boundaries

- `web/` is the server-owned admin/configuration panel and is developed in
  this repository.
- `server-logic` contributes validated flows, nodes, conditions, and actions.
- `server-linker` contributes Linker sessions, device inventory, health, and
  command routing.

The reusable `server-dashboard` module is a client dashboard, not a server
module. Server-side modules are not automatic microservices. A separate
process is justified by isolation, permissions, crash containment, or
independent update requirements.

## Development baseline

Use the CMake presets described in [README.md](README.md). CI runs with
warnings-as-errors where supported and executes CTest, the web production
build, and Python protocol tests. Keep the core dependency-light until a
dependency buys a concrete security, portability, or correctness guarantee.

## Current and next milestones

Implemented: C++ runtime/CLI foundation, versioned configuration loader,
structured JSON-line logging, validated in-memory device registry, typed
command/event path, protocol v1 schemas, built-in admin panel shell, Python
reference SDK, CMake quality gates, and CI.

Next server milestones: the Python backend/API migration, then a wire adapter
for the command/event path, HTTP API, WebSocket events, SQLite persistence,
and a small authentication baseline.
The current local path is intentionally transport- and persistence-free; these
should be added behind the public contracts rather than leaking internal
classes or storage tables. See
[`docs/adr/0001-phase-one-control-plane.md`](docs/adr/0001-phase-one-control-plane.md)
for the Phase 1 boundary choices.

The initial configuration adapter reads `OPENHDO_CONFIG_VERSION`,
`OPENHDO_INSTANCE_NAME`, and `OPENHDO_LOG_LEVEL`. All three are optional and
use the same validated loader as future file or CLI adapters.
