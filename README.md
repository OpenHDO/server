# OpenHDO

**Open Home Device Orchestration** — self-hosted platform for connecting devices, computers, operating systems, services, dashboards, and automations in one customizable ecosystem.

## What it is

- one server for local Raspberry Pi or remote VPS deployment;
- SDK for smart devices and hardware integrations;
- customizable dashboards and control panels;
- desktop and edge agents for interacting with operating systems;
- visual relationships between events, conditions, and actions;
- plugins with explicit permissions and versioned contracts;
- control from computers, phones, panels, and other clients.

The project is in the early design stage. The first milestone is a working C++ server with a configurable web panel, CLI, and extension contracts. React will be used for the panel implementation when frontend work begins.

## Repositories

```text
server              base server, web panel host, API, and CLI
server-dashboard    configurable dashboard module
server-logic        node-based logic and flow module
server-connector    connectors and device management module
sdk                 shared SDK repository, planned
app                 additional client application repository, planned
```

## Runtime tools

```text
openhdo-server   server executable
openhdo-sdk      SDK package and development tools
ohdocli          CLI for administration and diagnostics
openhdo-agent    planned desktop/edge agent
```

The initial server is a modular monolith. Separate processes are introduced only where isolation, permissions, crash containment, or independent updates make them useful.

## Technical overview

- C++20/23 runtime;
- CMake build system;
- SQLite for the first persistence layer;
- HTTP/WebSocket APIs;
- JSON Schema for shared contracts;
- out-of-process plugins with language-neutral communication.

See [DOCS.md](DOCS.md) for the architecture, implementation direction, contracts, deployment model, and roadmap.
