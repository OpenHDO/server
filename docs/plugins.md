# Plugins v1

HDO discovers plugins in `<data_dir>/plugins/<id>/hdo.json` (`/data/plugins` in Docker). Install a `.hdop` from **Plugins → Install .hdop**, inspect its permissions and enable it. Installation alone never executes code. Copying a folder works too: use **Refresh** or restart HDO, then enable the plugin.

```text
/data/
  plugins/
    .state.json                 enabled state owned by HDO
    example.home/
      hdo.json
      backend/plugin.py
      web/plugin.js
      web/theme.json
  plugin-data/example.home/     persistent private state, never served as assets
    state.sqlite3
```

Plugin code ships with the application only when explicitly bundled. A `/data` Docker volume retains both installed code and plugin state across server releases. Server packages contain the host SDK; users need no separate Python SDK installation. Plugins use the host's Python environment; HDO never automatically runs pip/npm on uploaded code. Authors bundle Python sources and build TypeScript into ESM before packaging. Native wheels and external Python dependencies must be provisioned by the installation owner.

## Manifest

```json
{
  "schemaVersion": 1,
  "apiVersion": 1,
  "id": "example.home",
  "name": "Example Home",
  "version": "1.0.0",
  "permissions": ["api", "storage", "providers", "events", "tasks", "network"],
  "dependencies": {"openhdo.logic": 1},
  "entrypoints": {"python": "backend/plugin.py", "web": "web/plugin.js"},
  "contributes": {
    "modules": [{"id": "main"}],
    "providers": [{"id": "cloud", "name": "Example", "fields": [{"key": "token", "label": "Token", "type": "password", "required": true}]}],
    "themes": [{"id": "violet", "file": "web/violet.json"}],
    "languages": [{"id": "de", "name": "Deutsch", "file": "web/de.json"}],
    "widgets": [{"id": "energy"}],
    "deviceModels": [{"id": "socket"}],
    "flowNodes": [{"id": "notify"}],
    "settings": [{"id": "options"}]
  }
}
```

IDs are portable lowercase identifiers, versions use SemVer, API compatibility is an explicit major (`1`). Dependencies map plugin IDs to supported major versions and must be installed and enabled first. Cycles and incompatible dependencies fail activation. Disable dependents before removing, restarting or updating their dependency. No plugin can silently claim another plugin's namespaced IDs.

## Python SDK

```python
from openhdo_plugin import PluginContext

async def activate(ctx: PluginContext):
    ctx.store.migrate(1, lambda state: {**state, "options": state.get("options", {})})
    async def options(request, context):
        if request.method == "PUT":
            context.store.set("options", await request.json())
        return context.store.get("options", {})
    ctx.route("options", options, methods=("GET", "PUT"))
    ctx.on("device.changed", lambda event: ctx.log.info("Device %s", event["payload"]["id"]))
    # ctx.task(coroutine_factory): starts after activation, canceled/awaited on disable.
    # ctx.on_dispose(callback): close clients, subscriptions and other resources.
```

Routes appear under `/api/v1/plugins/<id>/api/<path>`. Authentication, declared role (`admin` by default; `user` for public account-readable data) and CSRF are enforced by HDO before invoking handlers. Use `openhdo_plugin.ProviderError(status_code, code, detail)` for expected provider errors, or FastAPI HTTPException for route errors. GET handlers must not mutate state. Private config and account credentials belong in the store, not manifest or public assets.

`ctx.provider(local_id, instance)` registers an implementation with async `devices(config)` and `command(config, external_id, code, value)`. Returned device snapshots contain `external_id`, `name`, `kind`, `product_name`, `available`, `controls`, `state`, `updated_at` and optional `status_specs`/`state_revision`. The host validates snapshots and commands, assigns stable IDs, persists rooms and polls automatically. The integration's configuration is private. Provider forms support adding and reconfiguring an integration while keeping device IDs and rooms. Its provider ID is `<plugin-id>:<local-id>`. Register exactly the providers declared in the manifest.

`ctx.service("devices")` exposes device/room service operations, and `ctx.service("http")` the host HTTP client; declare `providers`/`network` respectively. `ctx.extension(kind, id, implementation)` registers declared server extensions such as async flow-node actions `(config, event)`. `ctx.extensions(kind)` returns enabled implementations keyed by namespaced ID. `ctx.emit(type, payload)` publishes to a bounded asynchronous event queue. Host events include `devices.updated` and `device.changed`; handlers run outside device locks. Async event callbacks have a 30-second deadline. Slow or CPU-heavy work should run in a worker owned by the plugin, not block the server loop.

Providers may define `poll_interval` (seconds, clamped to 5–300) and optional `command_batch(config, external_id, code, value, preceding)` to send related commands together. A provider may set `acknowledges_commands = True` only if a successful command response confirms acceptance; otherwise the host reads device states back before acknowledging. Command results may return updated state fields (for example a camera stream URL). These hooks are optional: the four-argument `command` remains supported.

`ctx.store.get/set/delete` stores transactional JSON; `migrate(version, transform)` atomically transforms state once. Cleanup is reversed; background tasks are canceled before registrations and stores are disposed.

## TypeScript SDK

Install `@openhdo/plugin-sdk` from the SDK repository (`npm install /path/to/sdk/typescript` after its `npm run build`). Bundle imports of your own dependencies. Import host types with `import type`; use `host.React`, which is the panel's React instance. Never bundle another React runtime.

```ts
import type { PluginHost } from "@openhdo/plugin-sdk";
export function activate(host: PluginHost) {
  host.module({ id: "main", label: "Example", order: 25,
    component: ({context}) => host.React.createElement("button", {
      onClick: () => host.notify("success", "Ready")
    }, "Example") });
  // host.extension("widgets", {id:"energy", component: EnergyWidget});
  // host.extension("deviceModels", {id:"socket", kind:"cz", priority:10, component: SocketCard});
}
```

The host owns all registrations and disposes them on disable/update. Module IDs are namespaced. `replaces: "devices"` explicitly replaces the built-in Devices view; admin/security recovery views remain protected. `host.ui.DeviceCard` exposes the standard HDO card for dashboards and custom views. Settings extensions open from the plugin's settings button in Plugins. Registering a `providers` extension with the same declared local ID augments its metadata with a custom login component; it receives `provider`, `context`, `integration`, `connected` and `back`, enabling provider-specific OAuth flows. `host.extensions(kind)` discovers enabled panel extensions. Widget, custom device-model and flow-node registries exist, but their automatic consumption by the current built-in Dashboard, Devices and Logic views is not implemented. `host.request(path, init)` calls the plugin's authenticated API; `host.context.api.request` calls host APIs with CSRF. `host.asset` resolves public assets and `host.t(key, values)` translates panel strings. Use `host.onDispose` for intervals, workers and external subscriptions. Entry points may return a disposer or a Promise of one. Module rendering errors are contained by a boundary and shown as overlay notifications.

Theme JSON: `{"id":"violet","name":"Violet","base":"dark","variables":{"--color-accent":"#8b5cf6"}}`. Keys are CSS custom properties; values cannot inject rules or URLs. Language JSON is a flat key-to-string mapping. Both appear in Settings. A language contribution with `replace:true` explicitly overrides existing translations and restores them on disable. In JS use `host.language(code,name,strings,true)` for the same behavior.

The panel loads built ESM from `web/`; CSS must also be built by the plugin (Tailwind in HDO does not scan installed plugins). Add a stylesheet via `host.asset` and register removal with `onDispose`. Public assets are authenticated; only supported web file extensions are served, never backend files or the private data directory.

## Packaging and updates

Use [plugin-cli](https://github.com/OpenHDO/plugin-cli):

```sh
hdop init example-home --id example.home --runtime hybrid
cd example-home
npm install
hdop build .
hdop validate .
hdop pack . --out example-home.hdop
```

`.hdop` is a deterministic ZIP containing `hdo.json`, built code/assets and SHA-256 `checksums.json`. Limits: 64 MiB compressed, 256 MiB expanded, 4096 payload files. Paths must be portable and relative; symlinks, case-colliding/duplicate paths, incomplete inventories, mismatched hashes and unsupported API versions are rejected before extraction. Checksums detect corruption; they are **not publisher signatures**.

Update by installing a package with the same ID. HDO stages it privately, disposes the old plugin, atomically replaces its folder and reactivates it if previously enabled. Activation failure restores the previous code and reactivates it. Plugin data is retained on update and removal; plugin-authored side effects and data migrations are not automatically undone by code rollback. Back up `/data` before installing a version with irreversible migrations. Successful async task activation cannot predict a failure that happens later; these failures appear in plugin status and server logs.

Plugins are trusted code with the privileges of the HDO process/browser session. Declared capabilities are an SDK contract, not OS isolation. Installing third-party code is an admin operation; enabling shows the trust/permissions prompt. There is no marketplace, automatic dependency installation, hidden cloud account or sandbox claim.

The current panel retains its built-in Dashboard and Logic views. Separate plugin implementations exist in the plugin development worktree; migrating those views is a separate change.

## Repository standard and CI/CD

**One plugin = one repository.** Keep exactly one `hdo.json` at its root. A
hybrid plugin, its modules, provider, theme and languages are contributions of
that same plugin, not separate nested plugins. Independently versioned plugins
use separate repositories and manifest dependencies. The SDK and CLI remain
shared tooling repositories.

`hdop init` creates `.github/workflows/plugin.yml`, which calls the reusable
`OpenHDO/plugin-cli/.github/workflows/plugin-release.yml@v1.1.0` workflow.
Dashboard and Logic use the same workflow. It installs the versioned CLI,
builds the plugin, validates it, packages `.hdop`, validates that archive and
uploads an Actions artifact. Node dependencies use `npm ci` when a lockfile is
present; commit that lockfile for reproducible builds.

For publication, update the root manifest's `version` and push `v<version>`.
`hdop pack --tag` rejects a mismatched tag before writing a package. On a tag
push the workflow publishes the `.hdop` and `.hdop.sha256` to GitHub Releases,
with generated release notes. SemVer prereleases produce GitHub prereleases.
PRs and regular pushes only build artifacts. No extra credentials are needed:
only the release job has `contents: write`; the build job uses read permissions.
The workflow does not overwrite existing published releases.
