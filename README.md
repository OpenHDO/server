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
WebSockets, server-side discovery sessions, transient `light.updated` events,
validated environment configuration, and structured JSON logging. It does not
invent device data: lights enter the registry through a real Linker registration
message, and an empty discovery scan remains empty.

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
`OPENHDO_HOST`, `OPENHDO_PORT`, `OPENHDO_LOG_LEVEL`, `OPENHDO_API_TOKEN`,
`OPENHDO_AUTH_DB`, `OPENHDO_ADMIN_USERNAME`, and `OPENHDO_ADMIN_PASSWORD`.
Set the last two together on first startup to create the initial admin user;
the password is hashed and the SQLite auth database is kept outside the web
build under `data/openhdo-auth.sqlite3`. `OPENHDO_AUTH_DB` can override this
path.
For a standalone React app on another local origin, set
`OPENHDO_CORS_ORIGINS` to a comma-separated list of exact origins, for
example `http://localhost:5173,https://dashboard.example`. CORS is disabled
when it is unset; configured origins use explicit `GET`, `PATCH`, and `POST`
methods and the `Authorization`, `Content-Type`, `Accept`, and
`X-OpenHDO-Source` headers. Credentials are not allowed and `*` is rejected.
Binding to a non-local host requires the token. Browser control HTTP requests
use an HttpOnly, SameSite session cookie plus a CSRF header; native Linker and
backward-compatible service clients may continue using
`Authorization: Bearer <token>` when configured. The `/admin` static shell is
available without credentials and immediately shows the login screen; API
boundaries remain protected.
When the origin allowlist is configured, `/api/v1/events` requires an allowed
`Origin` header and closes with code `4403` if it is missing or disallowed.
`/api/v1/linkers/{linker_id}` also rejects a present but disallowed `Origin`
with `4403`, but permits a missing Origin for native Python Linkers. With no
allowlist, local WebSocket behavior is unchanged.

The v1 API currently includes:

- `GET /api/v1/health`;
- `POST /api/v1/auth/login`, `POST /api/v1/auth/register`,
  `GET /api/v1/auth/me`, and `POST /api/v1/auth/logout` for browser sessions;
- `GET /api/v1/admin/users`, `PATCH /api/v1/admin/users/{id}`, and
  `DELETE /api/v1/admin/users/{id}` for admin-only user and role management;
- `POST /api/v1/admin/linkers` for admin-side Linker endpoint registration
  (`host`, `port`, and `minisecret`);
- `GET /api/v1/linkers` for registered Linker manifests, live availability, and
  their abstract Light devices;
- `GET /api/v1/lights` and `GET /api/v1/lights/{id}`;
- `PATCH /api/v1/lights/{id}` for one ergonomic abstract `power`, `brightness`
  (`0..255`), or `rgb_color` change plus an idempotency key;
- `POST /api/v1/lights/{id}/commands` for a complete v1 command envelope;
- `POST /api/v1/discovery/sessions` and
  `GET /api/v1/discovery/sessions/{session_id}` for authenticated, transient
  discovery sessions;
- `WS /api/v1/events` for `light.updated`;
- `WS /api/v1/linker` is the server-initiated Linker connection; the Linker
  sends `link.register` first, then state reports and discovery replies, while
  the server sends commands and discovery starts;
- `WS /api/v1/linkers/{linker_id}` remains the legacy Linker-initiated path.

Discovery starts are forwarded on the connected Linker WebSocket as
`discovery.start`. The server correlates replies to that envelope's `id`, keeps
only abstract Wi-Fi candidates and their `requires_pairing` value, and marks a
session failed when the Linker is unavailable, disconnects, or the bounded
`1..60` second timeout expires. Session state is process-local and is not
durable.

Server-owned persistent runtime data lives under `data/`. Server module data
belongs under `data/modules/<module-name>/`. Linker-owned data remains in the
Linker data directory and is not managed by the server.

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
Configure `OPENHDO_ADMIN_USERNAME` and `OPENHDO_ADMIN_PASSWORD` before the
first start, then sign in at the shared `/auth` page or open `/admin` and use
the profile menu. Public registration creates user accounts. No password or
session token is embedded in the panel build.

## Checks

The Python package declares production dependencies and a `dev` extra. Run
the focused suite directly with `python -m unittest discover -s tests -v`.
The CI contract also runs the React/TypeScript production build.

Normative messages and payloads belong under `contracts/v1/`; each public
addition requires an example and compatibility test. See [technical
documentation](DOCS.md) and the [Phase 1 ADR](docs/adr/0001-phase-one-control-plane.md).
