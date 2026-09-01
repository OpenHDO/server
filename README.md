# OpenHDO Server

The OpenHDO Server is the C++20 control plane: it owns shared state,
orchestration, the public API, authentication policy, persistence, and the
server-side module host.

The server is intentionally a modular monolith. Hardware access belongs in
the separate [OpenHDO Linker](https://github.com/OpenHDO/linker) process; web
clients and CLIs use the same public server contracts.

## What is in this repository

- `openhdo-server` — central server executable;
- `ohdocli` — administration and diagnostics CLI;
- `openhdo_core` — small reusable C++ runtime library;
- `contracts/v1/` — versioned language-neutral protocol contracts;
- `web/` — the built-in React + TypeScript + Tailwind + shadcn-style server
  admin/configuration panel shell;
- `python/` — dependency-free reference SDK for protocol clients and Linkers.

The current release is a buildable foundation. The long-running HTTP/WebSocket
service, SQLite store, authentication, and live Linker session are planned
server milestones, not hidden mock implementations.

## Build from source

Requirements: CMake 3.24+, a C++20 compiler, and Ninja or another supported
generator.

```bash
cmake --preset dev
cmake --build --preset dev
ctest --preset dev
build/dev/openhdo-server --check
build/dev/ohdocli --version
```

On Windows without Ninja, use `dev-mingw` instead of `dev`.

For the built-in server admin/configuration panel:

```bash
cd web
npm ci
npm run build
npm run dev
```

For the Python reference SDK:

```bash
cd python
python -m unittest discover -s tests -v
```

## Engineering checks

The CI contract is defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
CMake/CTest, TypeScript/Vite, and Python unittest must stay green. Public
messages belong under `contracts/v1/` and require an example plus a
compatibility test.

## Documentation

- [Server technical docs](DOCS.md)
- [Project overview and architecture](https://github.com/OpenHDO/about)
- [First-run guide](https://github.com/OpenHDO/get-started)
