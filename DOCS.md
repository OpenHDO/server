# OpenHDO technical documentation

OpenHDO means **Open Home Device Orchestration**. The name describes the first use case, while the platform itself is intended to cover the wider personal environment: home devices, computers, operating systems, services, dashboards, and automation.

This document describes the planned architecture and implementation direction. The repository is still at the early design stage; items marked as planned are not implemented yet.

## Product model

OpenHDO has one central control plane and multiple clients and extensions around it:

```text
                         +------------------+
                         |  OpenHDO Panel   |
                         |  future React UI |
                         +---------+--------+
                                   |
+-------------+          +---------v---------+          +----------------+
|   ohdocli   +---------->  openhdo-server   <----------+ openhdo-agent  |
| admin/diag  |          | central runtime   |          | OS/edge access |
+-------------+          +----+---------+----+
                              |         |
                    +---------v-+     +-v----------+
                    | SQLite    |     | Plugins    |
                    | state     |     | processes  |
                    +-----------+     +------------+
```

The server owns the shared state and orchestration rules. Clients display state or submit commands. Integrations translate between OpenHDO contracts and external devices or services.

## Components

### `openhdo-server`

The central deployable C++ process. It exposes the public API, stores configuration and state, evaluates flows, dispatches commands, and coordinates plugins and agents.

The first version is a modular monolith: the server has clear internal boundaries but does not split every boundary into a networked microservice. This keeps local deployment simple and avoids distributed-systems overhead before it is justified.

### `openhdo-sdk`

The SDK for building device integrations, agents, panels, and other extensions.

The initial SDK direction is C++-first because the runtime is C++, while the plugin boundary remains language-neutral. A plugin should be able to run as a separate process and communicate through a documented versioned contract rather than depending on server internals.

### `ohdocli`

The command-line client for administration, diagnostics, configuration, migrations, and scripted operation. It is a client of `openhdo-server`, not an internal server module.

### `openhdo-agent` — planned

A separately running desktop or edge process for capabilities that should not live inside the central server:

- operating-system integration;
- local processes and applications;
- USB, Bluetooth, serial, and other local hardware;
- machine-specific sensors and actions;
- restricted execution under a separate identity.

The agent can connect to a local server or a remote server, subject to authentication and permissions.

### `openhdo-panel` — planned

A React-based web client and future panel SDK. It will consume the same server API as the CLI and other clients. The frontend is intentionally not part of the first backend milestone.

## Server boundaries

The initial server contains these logical services:

### Core orchestrator

Owns commands, events, state transitions, policies, and coordination between the other modules.

### Registry

Tracks devices, entities, capabilities, agents, plugins, versions, and connection status.

### Flow engine

Evaluates triggers, conditions, actions, schedules, and execution results. Flows should be represented as data so they can be created from a UI, imported, validated, and executed without recompiling the server.

### API

Provides HTTP endpoints for administration and configuration plus WebSocket streams for live state, events, logs, and execution updates.

### Store

Persists configuration, registry data, flows, execution history, and migrations. SQLite is the initial storage backend because it works well for a single local server and keeps deployment small.

### Audit and logging

Produces structured logs and security-relevant history: who or what issued a command, what changed, whether execution succeeded, and which plugin or agent was involved.

### Plugin host

Discovers plugin manifests, starts and monitors plugin processes, negotiates protocol versions, applies permissions, and routes events and commands between plugins and the core.

These are internal boundaries, not promises that each item will become a separate deployable service. A separate process is justified by isolation, permissions, crash containment, resource limits, or independent update requirements.

## Core data model

The exact schema is not finalized, but the first model is expected to revolve around:

- **Device** — a physical or virtual controllable thing;
- **Entity** — a concrete value or controllable endpoint exposed by a device;
- **Capability** — a typed feature such as power, brightness, temperature, position, playback, or process control;
- **Event** — a fact that happened in the system or an integration;
- **Command** — a requested operation with validated arguments;
- **Action** — a flow step that invokes a command or produces another effect;
- **Flow** — triggers, conditions, actions, and execution policy;
- **Agent** — a trusted client that exposes local OS or hardware capabilities;
- **Plugin** — an isolated extension that contributes devices, capabilities, events, commands, or services.

The model should be serializable, versioned, and independent of any particular dashboard. A panel is a view and control surface, not the source of truth.

## Communication

### Client API

The server-facing API is planned around:

- HTTP for queries, configuration, administration, and command submission;
- WebSocket for live updates and long-running execution status;
- JSON payloads validated against versioned JSON Schemas.

The API should expose stable domain concepts instead of leaking C++ classes or SQLite tables.

### Plugin protocol

Plugins run out of process and communicate through a versioned RPC-style contract. The contract should support:

- plugin discovery and manifest exchange;
- capability and version negotiation;
- event publication;
- command requests and responses;
- health and lifecycle messages;
- permission checks;
- structured errors and timeouts.

The transport is deliberately left open at this stage. The important constraint is that the contract stays language-neutral and can be implemented by a non-C++ integration later.

### Agent protocol

Agents use the public server protocol with an agent-specific capability model. A server should be able to distinguish a command issued by a user, a flow, a plugin, or an agent and apply the appropriate policy.

## Plugin model

A plugin is an independently versioned package or process that extends OpenHDO without changing the server core.

The initial plugin requirements are:

1. a manifest with identity, version, supported protocol, and requested permissions;
2. explicit declarations of provided devices, capabilities, events, and commands;
3. process isolation from the main server;
4. bounded resources and lifecycle supervision;
5. structured diagnostics and health status;
6. compatibility checks before activation.

Plugins should not access the database directly. They use the protocol and public contracts so storage and internal implementation can evolve independently.

## Security direction

Security is part of the platform boundary rather than an afterthought for the dashboard:

- local-first deployment with no mandatory cloud dependency;
- authentication for remote clients and agents;
- explicit permissions for plugins, agents, users, and flows;
- least-privilege access to OS and hardware capabilities;
- audit records for security-sensitive operations;
- validation of all external payloads;
- timeouts and failure containment for integrations.

The first implementation should keep the security model small and understandable. More advanced identity and multi-user features can be added when the basic command and capability model is stable.

## Deployment

The same server should support several deployment sizes:

### Local

`openhdo-server` runs on a Raspberry Pi or another always-on local machine with SQLite and local integrations.

### Remote

`openhdo-server` runs on a VPS and remote agents connect back to it. This mode requires explicit authentication, encrypted transport, and careful exposure of the public API.

### Development

All components can run on one developer machine. Plugins and agents remain separate processes when their production boundary matters.

The first deployment target is a single server process. Clustering, distributed storage, and independently deployable microservices are outside the initial scope.

## Technology choices

- **C++20/23** — core runtime, server, agents, and the first SDK;
- **CMake** — build and dependency integration;
- **SQLite** — initial embedded persistence;
- **HTTP/WebSocket** — client and live-update APIs;
- **JSON Schema** — validation and compatibility contracts;
- **React** — planned dashboard and panel SDK;
- **language-neutral RPC contract** — plugin process boundary.

C++ is a runtime choice, not a restriction on the ecosystem. Integrations should be able to use other languages once the external protocol is stable.

## Implementation roadmap

### Phase 1: core foundation

- project and CMake layout;
- configuration and structured logging;
- typed commands and events;
- minimal registry;
- `ohdocli` connection and diagnostics;
- in-memory execution path.

### Phase 2: persistent server

- `openhdo-server` process;
- HTTP API;
- WebSocket event stream;
- SQLite store and migrations;
- authentication baseline;
- command and flow execution history.

### Phase 3: extension boundary

- plugin manifest;
- protocol versioning;
- plugin lifecycle supervision;
- permissions;
- one reference integration;
- `openhdo-sdk` starter API.

### Phase 4: local machine integration

- `openhdo-agent`;
- process and OS capabilities;
- local hardware bridge;
- remote-agent authentication and policy.

### Phase 5: user interfaces

- React dashboard;
- device and capability views;
- flow editor;
- panel SDK;
- live logs and execution inspection.

## Non-goals for the first version

- splitting every logical module into a microservice;
- building a full React frontend before the server contracts stabilize;
- requiring a cloud account for local use;
- allowing plugins direct access to internal storage;
- supporting every device protocol before the extension boundary works;
- committing to a specific message broker or distributed database prematurely.
