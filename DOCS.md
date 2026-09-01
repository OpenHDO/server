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
- hosting the server-side Dashboard, Logic, and Linker modules.

The server must not contain radio, USB, serial, or device-specific protocol
drivers. Those run in an isolated `openhdo-linker` process close to the
hardware.

## Repository layout

```text
include/openhdo/     public C++ headers
src/core/            reusable runtime library
src/server/          openhdo-server entry point
src/cli/             ohdocli entry point
tests/               CTest smoke checks
contracts/v1/        language-neutral JSON contracts
web/                 React/TypeScript panel shell
python/              stdlib-only protocol SDK reference
```

The server owns the source of truth. The panel, CLI, Linkers, agents, and
plugins are clients or isolated extensions; none may treat dashboard state or
SQLite tables as a public API.

## Public contract

The first stable contract is the versioned envelope in
[`contracts/v1/envelope.schema.json`](contracts/v1/envelope.schema.json).
Linker registration is represented by
[`contracts/v1/link-manifest.schema.json`](contracts/v1/link-manifest.schema.json)
and the `link.register` example.

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

- `server-dashboard` contributes pages, widgets, layouts, and control views.
- `server-logic` contributes validated flows, nodes, conditions, and actions.
- `server-linker` contributes Linker sessions, device inventory, health, and
  command routing.

These are server modules, not automatic microservices. A separate process is
justified by isolation, permissions, crash containment, or independent update
requirements.

## Development baseline

Use the CMake presets described in [README.md](README.md). CI runs with
warnings-as-errors where supported and executes CTest, the web production
build, and Python protocol tests. Keep the core dependency-light until a
dependency buys a concrete security, portability, or correctness guarantee.

## Current and next milestones

Implemented: C++ runtime/CLI foundation, protocol v1 schemas, panel shell,
Python reference SDK, CMake quality gates, and CI.

Next server milestones: a real configuration model, structured logging,
in-memory registry, HTTP API, WebSocket events, SQLite persistence, and a
small authentication baseline. These should be implemented behind the public
contracts rather than leaking internal classes or storage tables.
