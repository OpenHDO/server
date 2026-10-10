# Build and run from source

This guide is for building HDO yourself. Release users do not need Node.js,
the source checkout or the build commands below.

## Requirements

- Python 3.11+
- Node.js 20+ with npm
- Git

## Build

```text
git clone https://github.com/OpenHDO/server.git
cd server/web
npm ci
npm run build
cd ../python
python -m pip install -e .
```

If you already have a checkout, start from its `web/` directory and skip cloning.
The server serves the built panel from `web/dist/`. Rebuild it after changing
frontend source. For a standalone Python installation, package the panel alongside
the server; the Python wheel alone does not contain the web build.

## First run

From `server/python/`, set the initial administrator credentials and start HDO.
Choose your own password with at least 8 characters.

PowerShell:

```powershell
$env:OPENHDO_ADMIN_USERNAME = 'admin'
$env:OPENHDO_ADMIN_PASSWORD = '<your password>'
python -m openhdo_server --check
python -m openhdo_server
```

Linux / macOS:

```sh
export OPENHDO_ADMIN_USERNAME='admin'
export OPENHDO_ADMIN_PASSWORD='<your password>'
python -m openhdo_server --check
python -m openhdo_server
```

Open `http://127.0.0.1:8000/admin/` and sign in. Bootstrap credentials create the
initial admin; they do not reset an existing account's password. Local settings,
rooms and account tokens are stored under `server/data/` by default.

## Integrations

Tuya account sign-in works through **Devices → Integrations → Add integration**.
See [Tuya connection](tuya.md).

Yandex is an optional `openhdo.yandex` plugin. Install its `.hdop`, enable it,
and configure your own OAuth application in Plugins → Yandex → Settings.
No shared client credentials are included in source, Docker or releases.
See [Yandex plugin setup](yandex.md). OAuth settings and personal tokens remain
in `/data/plugin-data/openhdo.yandex/` across server/plugin updates.

Runtime options and checks are in [DOCS.md](../DOCS.md).
