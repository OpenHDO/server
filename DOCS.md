# OpenHDO technical documentation

OpenHDO means **Open Home Device Orchestration**. The name describes the first use case, while the platform itself is intended to cover the wider personal environment: home devices, computers, operating systems, services, dashboards, and automation.

This document describes the planned architecture and implementation direction. The repository is still at the early design stage; items marked as planned are not implemented yet.

## Product model

OpenHDO has one central control plane and configurable server modules around it. The base `server` repository contains the runtime, API, CLI, and web panel host. A separate `connector` repository contains standalone connector processes for physical devices. The `server-connector` repository is the server-side module that connects, registers, and manages those connector processes from the main server panel.

```text
                         +----------------------------+
                         | configurable web panel    |
                         | served by `server`         |
                         +-------------+--------------+
                                       |
+-------------+          +-------------v-------------+          +----------------+
|   ohdocli   +---------->          server            <----------+ openhdo-agent  |
| admin/diag  |          | openhdo-server + API       |          | OS/edge access |
+-------------+          | panel + module host       |          +----------------+
                          +-----+----------+----------+
                                |          |
                         +------v--+   +---v----------------+
                         | SQLite  |   | server-connector   |
                         | state   |   | connector sessions |
                         +---------+   +---------+----------+
                                                  |
                                      versioned connector protocol
                                                  |
                                      +-----------v-----------+
                                      | connector process(es) |
                                      | `connector` repo       |
                                      | Wi-Fi / BT / Zigbee   |
                                      +------------------------+
```

The server owns shared state and orchestration rules. The web panel and CLI are clients of the same server API. `server-connector` owns the server-side connection to connector processes; `connector` owns local device protocols and hardware access. A connector can run on the same machine as the server or on another computer, Raspberry Pi, gateway, or other edge host.

## Repository layout

The workspace root is a folder for multiple independent repositories, not a repository itself:

```text
HomeProtocol/
├── server/              base server, web panel host, API, and `ohdocli`
├── server-dashboard/    configurable dashboard module
├── server-logic/        node-based logic and flow module
├── server-connector/    server-side connector connection module
├── connector/           standalone physical-device connector process
├── sdk/                 shared SDK repository
└── app/                 additional client application repository
```

Only `server/` exists in the initial workspace. The other directories represent planned repositories and can be added independently when their first implementation is ready.

## Components

### `server` / `openhdo-server`

The base repository and central deployable C++ process. It contains:

- the core runtime, API, persistence, and orchestration;
- the configurable web panel host;
- `ohdocli` for administration and diagnostics;
- the module and plugin host;
- shared contracts used by server modules and external clients.

The web panel is a configurable control surface, not a separate source of truth. It uses the same API and permissions model as the CLI and other clients. React is the planned implementation technology for the web UI.

The first version is a modular monolith: the server has clear internal boundaries but does not split every boundary into a networked microservice. This keeps local deployment simple and avoids distributed-systems overhead before it is justified.

### `server-dashboard`

The configurable dashboard module. It defines the user-facing dashboard model and the pieces that can be arranged from the server panel:

- pages, views, layouts, and navigation;
- widgets and control cards;
- device and flow views;
- user-specific or role-specific visibility;
- saved panel configuration and reusable layouts.

The base `server` repository provides the panel host and API integration. `server-dashboard` provides the dashboard-specific module contract and implementation.

### `server-logic`

The node-based logic module for connecting system behavior. It represents automation as a graph of nodes, ports, and connections:

- event and state input nodes;
- conditions and transformations;
- command and action nodes;
- timers, schedules, and delays;
- execution status and error paths.

The module should allow logic to be created and edited from the server panel, stored as data, validated, and executed by the server runtime without recompiling the core.

### `server-connector`

The server-side connector module and repository. It is loaded by the main `server` and is responsible for connecting it to one or more standalone `connector` processes, then exposing them in the web panel and CLI.

It manages:

- connector process registration and identity;
- authentication and connection sessions;
- connector locations and metadata;
- connector health, heartbeat, and capabilities;
- device inventory received from each connector;
- remote configuration and connector lifecycle;
- routing device commands and events through the correct connector.

`server-connector` does not contain the low-level Wi-Fi, Bluetooth, Zigbee, USB, or serial implementation. It speaks the connector protocol and delegates physical access to the appropriate `connector` process.

### `connector`

The standalone connector process and its repository. It is the physical access layer — the "hands" of the main server — and can run on the same host as `server` or on a separate machine.

A connector process is responsible for:

- connecting to physical devices through supported transports and protocols;
- Wi-Fi, Bluetooth, Zigbee, USB, serial, TCP, and future adapters;
- discovering and pairing devices where the protocol allows it;
- adding or removing devices from its local inventory;
- translating device-specific state and commands into OpenHDO contracts;
- publishing device events and accepting commands from the main server;
- reporting health, capabilities, and connection status.

The connector process is a natural place for protocol drivers, local credentials, radio access, and hardware-specific dependencies. Those drivers can be implemented as connector plugins using `sdk` contracts.

`chdocli` is the planned CLI for installing, configuring, diagnosing, and pairing a connector process. The name is provisional.

The separation allows, for example, a PC to run `openhdo-server` while a Raspberry Pi runs `openhdo-connector` next to the Zigbee or Bluetooth hardware. Multiple connector processes can connect to one main server.

### `sdk` / `openhdo-sdk`

The SDK for building device integrations, connector drivers, agents, panels, and other extensions.

The initial SDK direction is C++-first because the runtime is C++, while the plugin boundary remains language-neutral. A module or plugin should be able to run as a separate process and communicate through a documented versioned contract rather than depending on server internals.

### `ohdocli`

The command-line client for administration, diagnostics, configuration, migrations, and scripted operation. It is part of the base `server` product and a client of `openhdo-server`, not an internal server module.

### `openhdo-agent` — planned

A separately running desktop or edge process for capabilities that should not live inside the central server:

- operating-system integration;
- local processes and applications;
- machine-specific OS sensors and actions;
- restricted execution under a separate identity.

Physical device protocols and local radio/hardware access belong to the standalone `connector` process. The agent is for desktop and operating-system capabilities that do not fit the connector model.

The agent can connect to a local server or a remote server, subject to authentication and permissions.

### `app` — planned

An additional client application repository for native or specialized clients. It will use the public server API and will not duplicate the server's state or orchestration logic.

## Configurable modules in the server panel

The web panel is the main place where the server is assembled and configured. Modules should appear as first-class sections with their own settings, status, permissions, and user-facing tools.

Every module can contribute a small, explicit surface to the panel:

- settings and configuration forms;
- status, health, and diagnostics;
- pages, widgets, and control views;
- entities, commands, and events exposed to other modules;
- permissions and required capabilities;
- import/export of module configuration.

The first modules are:

1. **Dashboard** (`server-dashboard`) — configure pages, layouts, widgets, navigation, and control views.
2. **Logic** (`server-logic`) — create and edit node graphs that connect events, conditions, transformations, and actions between devices and services.
3. **Connector** (`server-connector`) — connect to standalone `connector` processes, configure their locations and sessions, and manage the devices they expose.

Physical device protocols are implemented by the standalone `connector` process, not by the main server panel. Modules are configured from the server panel, but their state remains part of the server's versioned configuration model. The panel is an interface for managing modules; it is not a separate orchestration engine.

## Server boundaries

The initial `server` repository contains these logical services. Product modules use these boundaries without turning each one into a separate microservice:

```text
server-dashboard   panel host, API, view/configuration model
server-logic       core orchestrator, flow engine, event/command model
server-connector   connector sessions, device inventory, registry, routing
```

### Core orchestrator

Owns commands, events, state transitions, policies, and coordination between the other modules.

### Registry

Tracks devices, entities, capabilities, connector sessions, agents, plugins, versions, and connection status. Device records received from connectors are represented in the main server registry for use by the logic and dashboard modules.

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

- **Device** — a physical or virtual controllable thing discovered or added by a connector and represented in the main server registry;
- **Entity** — a concrete value or controllable endpoint exposed by a device;
- **Capability** — a typed feature such as power, brightness, temperature, position, playback, or process control;
- **Event** — a fact that happened in the system or an integration;
- **Command** — a requested operation with validated arguments;
- **Action** — a flow step that invokes a command or produces another effect;
- **Flow** — triggers, conditions, actions, and execution policy;
- **Node** — a logic module unit with typed inputs and outputs;
- **Port** — an input or output of a node;
- **Connection** — an edge connecting compatible node ports;
- **Location** — a physical or logical place containing devices or connectors;
- **Connector** — a standalone process that provides access to local devices and transports;
- **Connector session** — the authenticated server-side connection to a connector process;
- **Transport** — a physical or network protocol such as Wi-Fi, Bluetooth, Zigbee, USB, serial, or TCP;
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

### Connector protocol

The connector protocol links `server-connector` in the main server with a standalone `connector` process. It is bidirectional and versioned so the main server can send configuration and commands while the connector publishes devices, state, events, and health.

The protocol should support:

- connector registration and identity;
- authentication, heartbeat, and reconnect;
- capability and protocol negotiation;
- location and connector metadata;
- device discovery, pairing, addition, removal, and updates;
- device state and event publication;
- command dispatch and structured results;
- health, diagnostics, and transport status;
- safe remote configuration.

The connection may be local or remote. A remote connector must use authenticated and encrypted transport. The exact wire transport is intentionally left open until the contract is defined.

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

There are two extension locations:

- **server plugins** — extend the main `server` process with server-side capabilities;
- **connector drivers** — extend the standalone `connector` process with physical device protocols and transport support.

Connector drivers run close to the hardware. They are not loaded into the main server just because the device is visible in its registry.

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

OpenHDO has two independently deployable roles:

- `openhdo-server` — central control plane, panel, API, state, and orchestration;
- `openhdo-connector` — local device access, protocol drivers, discovery, and device events.

The connector boundary exists because physical devices and radios often need to stay near a particular machine or location. It is a deliberate hardware and network boundary, not a generic split of every server module into microservices.

### Same host

`openhdo-server` and one or more `openhdo-connector` processes run on the same Raspberry Pi, PC, or always-on local machine.

### Separate connector host

`openhdo-server` runs on a PC or VPS while `openhdo-connector` runs on another machine with the required hardware. For example, a PC can host the main server while a Raspberry Pi near a Zigbee coordinator or Bluetooth devices acts as the connector host.

### Multiple locations

Several connector processes can connect to one main server. Each connector has its own identity, location, transports, devices, credentials, health state, and reconnect behavior.

### Development

The server and connector can run on one developer machine or be started separately to reproduce a remote deployment. `ohdocli` administers the main server; `chdocli` administers a connector.

The first deployment target is a single main server plus an optional connector process. Clustering, distributed storage, and generic microservice decomposition are outside the initial scope.

## Technology choices

- **C++20/23** — main server, connector runtime, agents, and the first SDK;
- **CMake** — build and dependency integration;
- **SQLite** — initial embedded persistence;
- **HTTP/WebSocket** — client and live-update APIs;
- **JSON Schema** — validation and compatibility contracts;
- **React** — planned implementation technology for the server web panel and dashboard module;
- **language-neutral RPC contract** — plugin and connector protocol boundary;
- **Wi-Fi, Bluetooth, Zigbee, USB, serial, and other transports** — connector-side integrations.

C++ is a runtime choice, not a restriction on the ecosystem. Integrations should be able to use other languages once the external protocol is stable.

## Implementation roadmap

### Phase 1: core foundation

- project and CMake layout;
- configuration and structured logging;
- typed commands and events;
- minimal registry;
- configurable panel host and `ohdocli` connection/diagnostics;
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

### Phase 4: standalone connector

- `connector` repository and `openhdo-connector` process;
- `chdocli` administration and diagnostics CLI;
- server-to-connector protocol;
- connector identity, authentication, heartbeat, and reconnect;
- one reference transport and device integration;
- device discovery, pairing, onboarding, and event forwarding.

### Phase 5: configurable server modules

- `server-dashboard` module contract;
- `server-logic` node graph and execution model;
- `server-connector` connector session and device inventory model;
- module settings, permissions, health, and configuration persistence;
- module contributions to the server panel.

### Phase 6: local machine integration

- `openhdo-agent`;
- process and OS capabilities;
- local OS integration bridge;
- remote-agent authentication and policy.

### Phase 7: client applications

- React implementation of the server web panel;
- dashboard views and widgets;
- visual logic editor;
- connector, location, and device onboarding;
- `app` client applications;
- live logs and execution inspection.

## Non-goals for the first version

- splitting every logical module into a microservice;
- forcing physical device protocols and radio access into the main server process;
- building a full React interface before the server contracts stabilize;
- requiring a cloud account for local use;
- allowing plugins direct access to internal storage;
- supporting every device protocol before the extension boundary works;
- committing to a specific message broker or distributed database prematurely.
