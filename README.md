# OpenHDO Server

The OpenHDO Server is the Python control-plane runtime. It owns canonical
abstract device state, orchestration, public API, authorization policy,
configuration, persistence boundaries, and structured logs. React provides the
server-owned admin panel. The reusable `server-dashboard` module is a separate
client consumer and is not this panel.

Hardware access belongs in the separate [OpenHDO Linker](https://github.com/OpenHDO/linker)
process. Linker owns vendor/model details, pairing, protocol and DP mapping,
credentials, and real-device connections; the server receives only the
vendor-neutral contracts in `contracts/v1/`.

## Repository contents

- `python/openhdo_server/` — active FastAPI/Starlette + uvicorn runtime;
- `contracts/v1/` — versioned language-neutral envelope and Light contracts;
- `web/` — server-owned React admin/configuration panel source;

The current Python vertical slice provides health and Light inventory HTTP
endpoints, abstract Light command forwarding, Linker registration/state/result
WebSockets, transient `light.updated` events, validated environment
configuration, and structured JSON logging. It does not invent device data:
lights enter the registry through a real Linker registration message.

## Run the server

Requirements: Python 3.11+.

```bash
cd python
python -m venv .venv
python -m pip install -e ".[dev]"
openhdo-server --check
python -m unittest discover -s tests -v
openhdo-server
```

The default bind is local-only (`127.0.0.1:8000`). Supported configuration
variables are `OPENHDO_CONFIG_VERSION`, `OPENHDO_INSTANCE_NAME`,
`OPENHDO_HOST`, `OPENHDO_PORT`, `OPENHDO_LOG_LEVEL`, and `OPENHDO_API_TOKEN`.
For a standalone React app on another local origin, set
`OPENHDO_CORS_ORIGINS` to a comma-separated list of exact origins, for
example `http://localhost:5173,https://dashboard.example`. CORS is disabled
when it is unset; configured origins use explicit `GET`, `PATCH`, and `POST`
methods and the `Authorization`, `Content-Type`, `Accept`, and
`X-OpenHDO-Source` headers. Credentials are not allowed and `*` is rejected.
Binding to a non-local host requires the token. Control HTTP and WebSocket
surfaces require `Authorization: Bearer <token>` when configured.
When the origin allowlist is configured, both WebSocket endpoints also require
an allowed `Origin` header and close with code `4403` otherwise. With no
allowlist, local WebSocket behavior is unchanged.

The v1 API currently includes:

- `GET /api/v1/health`;
- `GET /api/v1/lights` and `GET /api/v1/lights/{id}`;
- `PATCH /api/v1/lights/{id}` for one ergonomic abstract `power`, `brightness`
  (`0..255`), or `rgb_color` change plus an idempotency key;
- `POST /api/v1/lights/{id}/commands` for a complete v1 command envelope;
- `WS /api/v1/events` for `light.updated`;
- `WS /api/v1/linkers/{linker_id}` for `link.register`, state reports, and
  command results.

## Server admin panel

Build the server-owned panel from `web/`:

```bash
cd web
npm ci
npm run build
```

When `web/dist/index.html` exists, the Python runtime serves it under
`/admin`. The build is optional; if the distribution is absent, `/admin`
returns a clear `admin_panel_unavailable` response and the API remains usable.
No dashboard or device data is embedded in the panel build.

## Checks

The Python package declares production dependencies and a `dev` extra. Run
the focused suite directly with `python -m unittest discover -s tests -v`.
The CI contract also runs the React/TypeScript production build.

Normative messages and payloads belong under `contracts/v1/`; each public
addition requires an example and compatibility test. See [technical
documentation](DOCS.md) and the [Phase 1 ADR](docs/adr/0001-phase-one-control-plane.md).
