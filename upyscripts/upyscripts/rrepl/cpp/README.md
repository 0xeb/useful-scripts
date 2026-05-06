# rrepl C++ Client

This folder contains a small C++ HTTP JSON client example for the Python
`upy.rrepl` server.

Build:

```bash
cmake -S . -B build
cmake --build build
```

Run:

```bash
./build/rrepl_client http://127.0.0.1:8765 demo "print('hello from C++')"
```

Arguments:

```text
rrepl_client [base_url] [session] [code...]
```

If code is omitted, the client reads Python code from stdin.
