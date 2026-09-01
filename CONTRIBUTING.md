# Contributing to OpenHDO

Keep the core small and the boundaries explicit. The server owns shared state
and orchestration; Linkers own local hardware access; clients use public
contracts instead of internal C++ or SQLite details.

Before opening a change, run the checks from [DOCS.md](DOCS.md): CMake/CTest,
the web build, and Python unittest. New public messages belong under
`contracts/v1/` and must include a representative example.

Prefer standard-library and platform facilities over new dependencies. Add a
dependency only when it removes meaningful complexity or provides a security,
portability, or correctness guarantee that the project cannot reasonably own.
