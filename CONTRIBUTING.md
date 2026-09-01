# Contributing to OpenHDO

Keep the core small and the boundaries explicit. The server owns shared state
and orchestration; Linkers own local hardware access; clients use public
contracts instead of internal Python or storage details.

Before opening a change, run the checks from [DOCS.md](DOCS.md): Python
unittest/import checks, the optional CMake compatibility checks, and the web
build. New public messages belong under
`contracts/v1/` and must include a representative example.

Prefer standard-library and platform facilities over new dependencies. Add a
dependency only when it removes meaningful complexity or provides a security,
portability, or correctness guarantee that the project cannot reasonably own.
