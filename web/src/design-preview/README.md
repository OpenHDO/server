# Design preview

Open `/admin/design-preview/` on the HDO server, or
`http://localhost:4173/admin/design-preview/` with `npm run dev`.

The panel reuses the admin shell and the production `DeviceCard`, `DeviceSummary`,
slider, palette and color dialog. It does not request authentication, inventory,
integrations or device commands. Demo values live only in React state.

`fixtures.ts` contains the supported device layouts and capability combinations.
The Yandex catalogue covers all 54 documented device types, using the production
normalizer and the same icons and controls as actual devices. Each fixture has
on, off, offline, disabled, updating, missing-data and unknown-state variants.
Use the type and state filters to compare layouts; choose All states to show all
variants. The delay selector simulates independent asynchronous commands. Reset
restores fixtures and cancels pending demo actions. Settings edit demo names,
availability and controls without persistence.

Regenerate the Yandex fixtures offline from the repository's `server` directory:
`python scripts/generate_device_preview.py`. The shared catalogue lives in
`python/openhdo_server/device_types.json`. Demo capabilities illustrate the
documentation's recommendations; real devices expose only capabilities returned
by their provider. Door locks have no recommended capabilities in the current
documentation, so their preview does not invent lock commands.

Camera previews use a local demo scene and never request a real stream. Relative
volume buttons simulate commands without inventing an absolute volume reading.
