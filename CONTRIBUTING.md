# Contributing to OpenHDO

The server owns integrations, credentials, inventory, policy and Devices.
Adapters live in the server and use public vendor APIs. Clients use versioned
APIs, never SQLite or vendor secrets.

Follow panel patterns: dark neutral surfaces, accent tokens, Phosphor icons,
responsive grids, loading/error/empty states and accessible forms. Devices
belongs to built-in navigation, not the module loader.
Use `useNotifications()` for errors and action confirmations. Notifications float
above the panel and dialogs; never insert status banners that shift forms or
cards. Loading and empty content states remain part of the view. Report cloud
commands as accepted, not as confirmed hardware changes.

Prefer standard-library/installed dependencies. Validate inventories and
commands. Never synthesize devices or report cloud acceptance as hardware
confirmation. Public additions require schemas, examples and compatibility tests.
Historical v1 schemas stay available to SDK consumers.

Run Python tests, compile/import/entrypoint checks and the web build in DOCS.md.
