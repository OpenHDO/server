# OpenHDO Server

The OpenHDO Server owns shared state, orchestration, the public API,
authentication policy, persistence, and the server-side module host. Python
is the chosen primary backend/runtime and React owns the web panels; the
existing C++20 foundation is a frozen compatibility/build baseline and is not
being extended.

The server is intentionally a modular monolith. Hardware access belongs in
the separate [OpenHDO Linker](https://github.com/OpenHDO/linker) process; web
clients and CLIs use the same public server contracts.

## What is in this repository

- `openhdo-server` — central server executable;
- `ohdocli` — administration and diagnostics CLI;
- `openhdo_core` — frozen C++ foundation library;
- `contracts/v1/` — versioned language-neutral protocol contracts;
- `web/` — the built-in React + TypeScript + Tailwind + shadcn-style server
  admin/configuration panel shell;
- `python/` — dependency-free protocol SDK and the future primary runtime
  location.

The current release is a buildable foundation. The Python backend/API
migration is a separate follow-up; no new C++ API/runtime work is part of that
migration. The long-running HTTP/WebSocket service, SQLite store,
authentication, and live Linker session are planned server milestones, not
hidden mock implementations.

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
