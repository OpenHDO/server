# Runtime and development

Python 3.11+ / FastAPI, React / TypeScript. See README.md and docs/tuya.md.
Yandex account setup and secret placement: [docs/yandex.md](docs/yandex.md).
ADR-0002 supersedes the Linker hardware path.

integrations.py owns SQLite inventory, lifecycle, metadata, sync and validation.
tuya_account.py authorizes accounts and uses Tuya's sharing SDK for devices and
commands. tuya.py retains developer-key compatibility and shared device normalization. lights.py adapts
lamps to Light v1. app.py owns auth, CSRF, events and panel hosting.
web/src/builtins/devices.tsx is the core Devices screen.
Yandex is provided by the optional `openhdo.yandex` plugin, not the server.
Its private OAuth application settings and account tokens belong to
`data/plugin-data/openhdo.yandex/state.sqlite3`. No shared credentials ship.
Plugin lifecycle and packaging: [docs/plugins.md](docs/plugins.md).

## Configuration

- OPENHDO_CONFIG_VERSION (1), OPENHDO_INSTANCE_NAME, OPENHDO_HOST (127.0.0.1),
  OPENHDO_PORT (8000), OPENHDO_LOG_LEVEL.
- OPENHDO_API_TOKEN: bearer token, required for non-local binds.
- OPENHDO_ADMIN_USERNAME / OPENHDO_ADMIN_PASSWORD: initial admin, set together.
- OPENHDO_AUTH_DB: auth database path; passwords are hashed.
- OPENHDO_DATA_DIR: integration data directory (default server/data).
- OPENHDO_CORS_ORIGINS: exact comma-separated origins; wildcard is rejected.
  Configured event sockets require an allowed Origin. GET/POST/PUT/PATCH/DELETE
  are allowed; cookie mutations require X-OpenHDO-CSRF.

Auth lives in data/openhdo-auth.sqlite3; credentials/inventory in
 data/devices/integrations.sqlite3. Failed reads never replace valid inventory.
Metadata survives sync/restart. Removing an integration removes local data,
not physical devices. Protect credential-bearing storage/backups.
Yandex caches the `user/info` inventory for five minutes and queries each device's
current state every 15 seconds, with at most two requests in parallel. Confirmed
`offline` is applied immediately. Failed state requests set `state_stale=true`:
last known values remain stored, but the UI shows unknown power instead of on/off.
Previously available devices retain command access for at most 60 seconds after
a successful read; repeated failures back off per device to 120 seconds.
HTTP 429 observes Retry-After (15–300 seconds, default 60) per account; commands
are never automatically retried. Revoked authorization is not hidden by caches.
The official Yandex user API does not expose a device-event subscription;
its notifications API accepts provider-to-Yandex reports, not incoming events.

Each integration has an independent worker. Tuya polls every five seconds;
whole-integration failures back off to 60 seconds and retain inventory.
`/api/v1/events?devices=1` adds authenticated `devices.updated` envelopes with
full device inventory, integrations and rooms. It emits `devices.heartbeat`
every 20 seconds. The panel uses events as its primary channel, reconnects,
and only falls back to ten-second local HTTP reads when no event has arrived
for 45 seconds or the socket has disconnected. These HTTP reads do not poll
providers. Commands and external changes cannot be overwritten by older reads.
Tuya account specifications are cached for ten minutes; device state is always
read afresh. Cloud propagation can add delay to external changes.
Old registries and published schemas remain for recovery/compatibility, but
legacy runtime paths and linkerct are removed.

## Verify

```powershell
cd python
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m compileall -q openhdo_server
python -m openhdo_server --check
cd ../web
npm ci
npm run build
```

Checks use mocked HTTP. For real verification connect Tuya in Devices, change
power and compare refreshed state with the app. Acceptance is not confirmation.
