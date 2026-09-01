# OpenHDO Python SDK

This is the first stdlib-only reference implementation for OpenHDO protocol
clients and Linker drivers. It provides validated versioned envelopes while
leaving transport, device libraries, credentials, and reconnect policy to the
embedding application. `LinkerManifest` is enough to produce the first
`link.register` message from a Python-based Linker.

Run its self-check from this directory:

```bash
python -m unittest discover -s tests -v
```
