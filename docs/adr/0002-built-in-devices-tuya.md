# ADR-0002: Built-in Devices and Tuya

Accepted: 2026-10-09. Supersedes the Linker path in ADR-0001.

Devices is core navigation in the server's React panel. The server owns credentials,
integration lifecycle, durable inventory and command routing. Adapters connect
existing smart-home systems through public APIs and live inside the server.
Tuya Cloud is first; Home Assistant is outside this change.

Real inventory/functions determine devices and permitted commands. Failed reads
retain data and mark devices unavailable. Local names/rooms/enabled flags survive
resync and restart. Cloud acceptance never confirms hardware state.

Light v1 remains through an adapter; `linker_id` identifies the integration.
Old IDs require rebinding. Linker/discovery/pairing APIs/services are retired;
published schemas stay available for SDK DTO compatibility. `linker` and
`server-linker` leave the active repository map.

Tuya requires internet, account linking and API permissions/quota. Unsupported DP
formats remain readable and are not made writable using guessed mappings.
