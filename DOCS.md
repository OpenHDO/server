# OpenHDO Server — technical documentation

This document is limited to the server repository. Product-wide architecture,
repository ownership, naming, deployment roles, and roadmap live in the
[OpenHDO about repository](https://github.com/OpenHDO/about).

## Responsibility

`openhdo-server` is the central control plane. It owns:

- canonical abstract domain state and orchestration rules;
- commands, events, policies, and execution outcomes;
- registries of devices, capabilities, and Linker sessions;
- the versioned HTTP API and WebSocket paths;
- the configuration/authentication boundary and structured logs;
- persistence seams for a later durable repository;
- the built-in server admin/configuration panel host.

The server must not contain radio, USB, serial, pairing, vendor/model, device
protocol, DP mapping, credential, or real-device connection logic. Those remain
in the isolated `openhdo-linker` process close to the hardware. A Linker
registration contributes only the vendor-neutral manifest and Light capability
defined by `contracts/v1/`.

The reusable `server-dashboard` module is a client-facing consumer of server
contracts. It is not the server's admin/configuration panel and is not owned by
this repository.

## Runtime direction

Python is the only active server runtime/executable target. The implementation
is in `python/openhdo_server/` and uses FastAPI/Starlette, uvicorn, and typed
Pydantic models. React owns the panel source in `web/`; a production build is
served at `/admin` when `web/dist/` is present.

## Repository layout

```text
contracts/v1/        language-neutral envelope, Linker, and Light contracts
python/openhdo_server active Python runtime, models, repository, and service
python/tests/         runtime and contract-focused tests
web/                  server-owned React admin/configuration panel source
docs/adr/             architectural decisions
```

The server owns the source of truth. The built-in admin panel, reusable client
dashboards, Linkers, agents, and plugins use the public contracts; none may
treat panel state or storage tables as an API. The Python runtime starts with a
process-local repository and does not seed fake lights. A Light exists only
after a Linker sends `link.register` with its abstract capability.

## Public v1 boundary

The common envelope is defined in
[`contracts/v1/envelope.schema.json`](contracts/v1/envelope.schema.json).
Linker registration uses
[`contracts/v1/link-manifest.schema.json`](contracts/v1/link-manifest.schema.json)
and the `link.register` example. The RGB Light slice uses
[`contracts/v1/light-command.schema.json`](contracts/v1/light-command.schema.json),
[`contracts/v1/light-state.schema.json`](contracts/v1/light-state.schema.json),
and [`contracts/v1/light.schema.json`](contracts/v1/light.schema.json).

Light brightness and RGB channels are OpenHDO-defined integers in the inclusive
range `0..255`. Capabilities may advertise `RGB`, `RGBW`, or `CCT` where
applicable; no vendor/model/local-key fields are valid server capability data.

The active runtime exposes these transport adapters over the same v1 model:

- `GET /api/v1/health` is the unauthenticated liveness response;
- `GET /api/v1/lights` and `GET /api/v1/lights/{id}` read canonical state;
- `POST /api/v1/lights/{id}/commands` accepts a complete typed command
  envelope;
- `POST /api/v1/discovery/sessions` starts an authenticated bounded discovery
  session and `GET /api/v1/discovery/sessions/{session_id}` reads its current
  process-local state;
- `PATCH /api/v1/lights/{id}` adapts one `power`, `brightness`, or `rgb_color`
  change plus an idempotency key into that same typed command path;
- `WS /api/v1/linkers/{linker_id}` accepts `link.register`,
  `light.state.reported`, `command.result`, and discovery reply envelopes;
- `WS /api/v1/events` publishes canonical `light.updated` event envelopes.

The Linker WS is a message endpoint, not a device protocol adapter. The server
validates the v1 envelope, checks that the message source matches the connected
Linker identity, and updates only the abstract Light registry. Commands are
forwarded only to a currently connected Linker. A successful HTTP response
with status `202` means `accepted` for forwarding; it is not a claim that the
physical device applied the command. The later Linker `command.result` uses
the forwarded `light.command` envelope `id` as its `correlation_id`. Applied
results carrying state produce `light.updated` with the same correlation ID.

The process-local event observer is intentionally transient and bounded. It
does not promise durable delivery; persistence, replay, retry, and a dead-letter
channel belong behind an explicit future reliability requirement.

Discovery follows the same command/request-reply/correlation/observer boundary:
the server creates a UUID session, forwards `discovery.start` over the
connected Linker socket with `correlation_id` equal to the start envelope `id`,
and accepts only source-matching `discovery.candidate` and
`discovery.completed` messages for that session. The session is marked failed
on unavailable transport, an active Linker disconnect, a Linker-reported
failure, or timeout after 1..60 seconds. Candidates are never synthesized; a
successful scan may have an empty candidate list. The candidate contract is
intentionally limited to abstract Light capability data, Wi-Fi transport, and
the honest
`requires_pairing` flag.

Compatibility rules:

1. Reject unsupported protocol major versions before processing payloads.
2. Keep message names stable and use the envelope `id` as the correlation
   target for its reply/result.
3. Ignore unknown optional fields at a compatible external boundary; breaking
   required changes require a new major contract.
4. Add a schema or payload definition, example, and compatibility test before
   making a message public.
5. Keep authorization, validation, logging, and test seams at every runtime
   boundary.

The schema defines logical messages, not a remote deployment transport. Any
future remote transport must provide encryption, authentication, size limits,
timeouts, reconnect behavior, and an explicit delivery policy.

## Module boundaries

- `python/openhdo_server` owns configuration, authorization, canonical Light
  state/capability, command service, repository, and transport adapters.
- `web/` is the server-owned admin/configuration panel and is served only from
  this server's optional `web/dist/` build under `/admin`.
- `server-linker` owns Linker sessions and all vendor/model/pairing/protocol/
  DP/real-device work.
- `server-logic` may contribute validated flows, nodes, conditions, and
  actions through a later server-side seam.
- `server-dashboard` remains a reusable client dashboard and is not imported,
  copied, or hosted as the server admin panel.

## Configuration and authorization

Configuration is versioned (`OPENHDO_CONFIG_VERSION=1`) and loaded through the
typed `ServerSettings` boundary. Defaults bind to `127.0.0.1:8000`; a
non-local bind is rejected unless `OPENHDO_API_TOKEN` is set. Browser sessions
are backed by the server-owned SQLite auth store (`OPENHDO_AUTH_DB`, default
`openhdo-auth.sqlite3`). Set `OPENHDO_ADMIN_USERNAME` and
`OPENHDO_ADMIN_PASSWORD` together on first startup to bootstrap the initial
admin. Public registration creates viewer accounts. Passwords are stored as
scrypt hashes; sessions are revocable and are
sent to the browser in an HttpOnly, SameSite cookie with a separate CSRF
cookie/header check for state-changing requests.
The static `/admin` shell remains readable without credentials and exposes the
mini-profile guest state. Shared login and registration are served from the
minimal `/auth` page. Native Linker and backward-compatible service clients may
continue using a bearer token when `OPENHDO_API_TOKEN` is configured.
For a standalone React client on a separate origin,
`OPENHDO_CORS_ORIGINS` accepts a comma-separated allowlist of exact `http` or
`https` origins. CORS middleware is installed only when this list is non-empty,
with `allow_credentials=False`, methods limited to `GET`, `PATCH`, and `POST`,
and headers limited to `Authorization`, `Content-Type`, `Accept`, and
`X-OpenHDO-Source`; wildcard origins are rejected. For `/api/v1/events`, a
configured allowlist requires a present, allowed WebSocket `Origin`; missing
or disallowed origins close with code `4403`. For
`/api/v1/linkers/{id}`, a missing Origin is permitted for native Python
Linkers, while a present Origin must be allowed and otherwise closes with
`4403`. If unset, existing local WebSocket behavior is preserved. This origin
check does not replace bearer authorization.
Startup, shutdown, registration, forwarding, state, and result paths emit
structured JSON log events without logging credentials or vendor data.

## Development checks

```bash
cd python
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m compileall -q openhdo_server
openhdo-server --check
```

The optional panel build is:

```bash
cd web
npm ci
npm run build
```

After the build, run the server and open `/admin`. Without `web/dist/index.html`,
the server returns a clear `admin_panel_unavailable` 404 instead of serving
placeholder data.

See [`docs/adr/0001-phase-one-control-plane.md`](docs/adr/0001-phase-one-control-plane.md)
for the Phase 1 boundary choices.
