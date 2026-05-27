# rrepl

`rrepl` is a small HTTP JSON Python REPL server for UPyScripts. It keeps named
Python sessions alive between requests, so clients can run setup code once and
reuse the same interpreter namespace later.

Warning: this server executes arbitrary Python code. It binds to `0.0.0.0` by
default for LAN use, so only run it on trusted networks.

> **Driving rrepl from an AI / LLM agent?** Read
> [`AGENT-GUIDE.md`](AGENT-GUIDE.md) — bootstrap, worked example, and
> session hygiene targeted at programmatic clients. The dbg plugin's
> reference lives in [`plugins/dbg/GUIDE.md`](plugins/dbg/GUIDE.md).

## CLI

```bash
upy.rrepl serve --port 8765
upy.rrepl exec "x = 41"
upy.rrepl exec "print(x + 1)"
upy.rrepl exec "name = 'Ada'" --session demo
upy.rrepl sessions
upy.rrepl reset --session demo
upy.rrepl delete demo
```

## HTTP API

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/api/v1/sessions
curl -X POST http://127.0.0.1:8765/api/v1/exec \
  -H 'Content-Type: application/json' \
  -d '{"session":"demo","code":"print(\"hello\")"}'
```

## Python Client

```python
from upyscripts.rrepl.client import RReplClient

client = RReplClient("http://127.0.0.1:8765")
client.exec("x = 10", session="demo")
print(client.exec("print(x)", session="demo")["stdout"])
```

## C++ Client

The `cpp/` folder contains a small `rrepl_client` HTTP example:

```bash
cmake -S upyscripts/rrepl/cpp -B build/rrepl-cpp
cmake --build build/rrepl-cpp
./build/rrepl-cpp/rrepl_client http://127.0.0.1:8765 demo "print('hello')"
```
