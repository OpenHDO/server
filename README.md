# Mosaic Home

Mosaic Home is a local-first control plane for connecting devices, computers, services, dashboards, and automations in one customizable ecosystem.

## Status

Early design stage.

## Direction

- device and hardware SDKs;
- customizable dashboards and control panels;
- agents for Windows, Linux, and macOS;
- visual flows for connecting events, conditions, and actions;
- isolated plugins with explicit permissions;
- local Raspberry Pi deployment or remote VPS deployment.

The project is intentionally starting small: one core, one plugin contract, and one useful desktop agent before adding a larger ecosystem.

## Initial stack

- C++20/23 for the core runtime, edge nodes, and desktop agents;
- CMake for builds;
- SQLite for the first local persistence layer;
- HTTP/WebSocket APIs with JSON Schema contracts;
- out-of-process plugins communicating through a versioned RPC contract.

The first milestone is backend-only C++ runtime work. A React-based dashboard and panel SDK will be added later as a separate layer. C++ is the runtime choice, not a requirement for every extension: plugin contracts stay language-neutral so integrations can be written in other languages.
