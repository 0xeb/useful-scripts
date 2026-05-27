# `upy.rrepl` — agent guide

This document is for AI / LLM agents using this repository as a
**client**. Read it first; everything beyond it (`README.md`,
`plugins/dbg/GUIDE.md`, the test files) is reference, not bootstrap.

---

## 1. What this is

`upy.rrepl` is an HTTP JSON Python REPL server. A long-running rrepl
process holds **named, persistent sessions** — each session is its own
Python interpreter namespace that survives between requests, so you can
set state once and use it for hours of conversation.

`upy.rrepl-dbg` is a plugin running inside any rrepl session that gives
you a Windows x86/x64 user-mode debugger (spawn / attach, software
breakpoints, single-step, register & memory R/W, capstone disassembly,
keystone assembly, conditional + action breakpoints with server-side
scripts, transparent WOW64 support).

You drive both over plain HTTP (or via the bundled Python client).

---

## 2. Bootstrap (do this first)

### 2.1 Find the rrepl URL

In order:

1. **Environment**: `RREPL_URL` (e.g. `http://winhost:8765`).
2. **Local config**: `.claude/rrepl.json` walked upward from the
   current working directory. Schema:
   ```json
   {
     "url": "http://...:8765",
     "vm_repo_path": "C:\\Users\\…\\useful-scripts",
     "vm_python":   "C:\\Users\\…\\_plan\\Scripts\\python.exe"
   }
   ```
   The `.claude/` folder is gitignored — local-only.
3. **Otherwise**: ask the human for the URL.

### 2.2 Verify reachability

```bash
curl -s "$RREPL_URL/health"     # → {"ok":true,"service":"rrepl"}
```

If `/health` answers, you're good. If `/api/v1/reload` returns 404, the
running rrepl predates that endpoint and the human needs to restart it
once — this only matters if you're going to push & hot-reload code.

### 2.3 Install the Python client (recommended)

```bash
pip install -e ./upyscripts          # from a checkout of this repo
```

You can drive everything via raw `curl` against `/api/v1/exec`, but the
`Dbg` Python client is significantly more ergonomic.

### 2.4 Pick a unique session name

Multiple agents may share one rrepl host. Use something distinctive,
e.g. `agent-claude-2026-05-06` or `pytest-dbg-<uuid>`. Don't use
`default`.

---

## 3. Connect & drive

### Python client path (preferred)

```python
from upyscripts.rrepl.plugins.dbg.client import Dbg

d = Dbg("http://winhost:8765", session="agent-yourname")
d.spawn(r"C:\Windows\System32\notepad.exe")     # or d.attach(pid)
```

The plugin auto-imports server-side on first call — no setup endpoint
to call. The session keeps `DBG` alive between requests so subsequent
calls reuse the same debugger / debuggee.

### Raw HTTP path

```bash
curl -X POST "$RREPL_URL/api/v1/exec" \
     -H 'Content-Type: application/json' \
     -d '{"session":"agent-yourname",
          "code":"from upyscripts.rrepl.plugins.dbg.server import Debugger as _D\nDBG = _D()\nprint(DBG.spawn(r\"C:\\\\Windows\\\\System32\\\\notepad.exe\"))"}'
```

You'll write Python snippets and ship them as the `code` field. Output
goes back as `{"ok": bool, "stdout": str, "stderr": str, "error": …}`.

---

## 4. Worked example — conditional BP on `user32!MessageBoxW`

This is the canonical end-to-end you can copy and adapt. Spawns a
64-bit notepad, sets a server-side action breakpoint that lets the
first two hits pass through and stops on the third, triggers the BP via
`CreateRemoteThread`, and cleans up.

```python
from upyscripts.rrepl.plugins.dbg.client import Dbg
import textwrap

d = Dbg("http://winhost:8765", session="agent-demo")

# 1. Spawn the target and let the loader settle.
sp = d.spawn(r"C:\Windows\System32\notepad.exe")
print("pid:", sp["pid"], "wow64:", sp["wow64"])
d.cont(timeout_ms=4000)                  # absorbs LOAD_DLL / loader BP

# 2. Set a BP by symbol with a server-side action script.
#    `state` survives across hits on this BP. `regs`, `dbg`, `bp`, `ev`,
#    `gstate` are also in scope. Set `result = "resume"` to make the hit
#    transparent (no client event). Default = "suspend".
action = textwrap.dedent("""
    state["count"] = state.get("count", 0) + 1
    result = "suspend" if state["count"] >= 3 else "resume"
""").strip()
bp = d.set_bp("user32!MessageBoxW", action=action, name="stop_on_3rd")
print("BP set at", hex(bp["addr"]), bp.get("symbol"))

# 3. Inject 5 calls to MessageBoxW so the BP fires 3+ times.
#    Use exec_inline so the ctypes work happens server-side on the
#    rrepl host.
d.exec_inline(textwrap.dedent("""
    import ctypes, ctypes.wintypes as wt
    k32 = ctypes.windll.kernel32
    k32.CreateRemoteThread.argtypes = [
        wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
        ctypes.POINTER(wt.DWORD),
    ]
    k32.CreateRemoteThread.restype = wt.HANDLE
    h_proc = DBG._impl.h_process
    addr = DBG.resolve("user32!MessageBoxW")
    for _ in range(5):
        k32.CreateRemoteThread(h_proc, None, 0, ctypes.c_void_p(addr),
                               None, 0, None)
    print("__R__null")
"""))

# 4. Pump events until the BP surfaces (the third hit, where the action
#    returned "suspend"). cont() may return a non-BP first-chance
#    exception in between — keep going until counters say we hit ≥3.
for _ in range(8):
    ev = d.cont(timeout_ms=2000)
    rows = d.list_bps()
    if rows[0]["hits"] >= 3 and "hit_bp" in ev:
        break

print("paused at:", ev["bp_script"])      # {addr, name, hits=3, action_result="suspend"}
print("counters:", rows[0])               # hits=3, skipped=2

# 5. Inspect — get_regs() returns Rip/Rax/... on x64, Eip/Eax/... on WOW64.
regs = d.get_regs()
print("Rip:", hex(regs["Rip"]))
print("at:", d.addr_to_symbol(regs["Rip"]))   # → user32.dll!MessageBoxW+0x0

# 6. Disassemble around Rip (capstone, bitness-aware).
for ins in d.disasm(regs["Rip"], 4):
    print(f"  {ins['addr']:#x}  {ins['mnemonic']} {ins['op_str']}")

# 7. Clean up. detach() leaves the debuggee running standalone;
#    kill() terminates it.
d.clear_bp("user32!MessageBoxW")
d.kill()
```

If you ever need behaviour the typed wrappers don't cover, drop into
`d.exec_inline("…")` to run arbitrary Python on the worker thread.
That's how the test suite exercises ad-hoc Win32 calls.

---

## 5. Session hygiene

* **Pick a unique session name.** Multiple agents on one rrepl host
  step on each other if they share a session.
* **Don't strand debuggees.** Always end with `d.kill()` or
  `d.detach()`. A spawned notepad you forget about stays attached to
  rrepl and consumes a worker thread until rrepl restarts.
* **Reset to wipe state.** `POST /api/v1/reset {"session":"name"}`
  drops the namespace; `DELETE /api/v1/sessions/<name>` deletes the
  session entirely.
* **Hot-reload after pulling new plugin code.** `POST /api/v1/reload`
  drops `upyscripts.rrepl.plugins.*` from `sys.modules`, re-runs any
  editable-install finders, and resets all sessions.

---

## 6. Stateful operation — what survives

| across calls          | survives? | how to clear |
| --------------------- | --------- | ------------ |
| session globals (`DBG`, your variables) | yes | `/reset` |
| `DBG._impl._modules` / `_threads` tables | yes (until detach/kill) | `kill()` |
| BP table + per-BP `state` dict | yes | `clear_bp()` / `kill()` |
| `gstate` (cross-BP scratchpad) | yes per session | `/reset` |
| thread / module history ring buffers | yes (post-mortem available after kill) | `/reset` |
| spawned debuggee | yes (until kill / detach / process exit) | `kill()` |
| imported plugin modules | yes | `/api/v1/reload` |

You can have a session with a debuggee parked at a BP, walk away,
return hours later, `d.list_bps()` / `d.list_threads(enrich=True)` to
re-orient, and continue. This is the design — the debugger is meant
for asynchronous AI-driven workflows.

---

## 7. Deploy / hot-reload (only if you're editing this repo)

```bash
git push origin <branch>

# git pull on the VM (driven through rrepl)
curl -X POST "$RREPL_URL/api/v1/exec" -H 'Content-Type: application/json' \
     -d '{"session":"deploy","code":"import subprocess; print(subprocess.check_output([\"git\",\"-C\",r\"<vm_repo_path>\",\"pull\",\"--ff-only\"], text=True, stderr=subprocess.STDOUT))"}'

# pick up the new code
curl -X POST "$RREPL_URL/api/v1/reload" -H 'Content-Type: application/json' -d '{}'
```

If `/api/v1/reload` is 404, the rrepl process is older than the
endpoint — ask the human to restart `upy.rrepl serve` once.

---

## 8. Constraints & safety

* **rrepl executes arbitrary Python on the host.** The default bind is
  `0.0.0.0` for LAN use. Treat it like an SSH shell.
* **BP scripts run on the dbg worker thread and block the event pump.**
  Keep them fast — quick state updates, memory peeks, the occasional
  patch. Anything that can take seconds belongs in the client.
* **Conditional BP errors fail-stop.** If your `condition` raises, the
  BP surfaces with `bp_script.condition_error` set so you see what
  broke; `action` errors are recorded but the BP still surfaces.
* **WOW64 is transparent at the API surface, with one caveat:**
  `get_regs()` returns native register names — `Rip/Rax/...` on x64,
  `Eip/Eax/...` on 32-bit. Code that hardcodes one set won't work
  against the other.
* **Forwarded exports** (`kernel32!HeapAlloc` →
  `ntdll!RtlAllocateHeap`) are followed transparently by `resolve()`.

---

## 9. Where to look next

* **`plugins/dbg/GUIDE.md`** — full API reference, every event shape
  the debugger can return, recipes (TLS callbacks, EntryPoint, hot-
  patching), troubleshooting. ~600 lines, but searchable.
* **`tests/test_rrepl_dbg_remote.py`** — executable spec. If you're
  unsure how to drive a feature, the test does it cleanly. Patterns to
  copy: `_INJECT_HELPER`, `_bootstrap_dbg`, the action-BP loop.
* **`tests/test_rrepl.py`, `tests/test_rrepl_reload.py`** — rrepl core
  behaviour tests.
* **`README.md` (in this directory)** — humans / setup view of rrepl.
* **`plugins/dbg/cpp/`** — minimal C++ client if you need to drive
  rrepl from native code.

---

## 10. Quick-reference cheat sheet

```python
# Session lifecycle
d = Dbg(url, session="agent-name")          # connect
d.spawn(path) / d.attach(pid)               # debuggee on
d.detach() / d.kill()                       # debuggee off

# Run / stop
d.cont(timeout_ms=2000)                     # run until next event
d.step(n=1) / d.step_over()                 # single-step / step over CALL
d.continue_event(handled=True)              # ack last event manually

# Software breakpoints (int 3)
d.set_bp("module!sym")                      # by symbol
d.set_bp(0x140001000)                       # by address
d.set_bp(addr, condition="regs['Rcx']==0",  # only stop when arg1==0
        action="state['n']=state.get('n',0)+1\nresult='resume' if state['n']<3 else 'suspend'",
        name="my_bp")
d.clear_bp(addr_or_symbol)                  # remove
d.list_bps()                                # all + counters

# Hardware breakpoints (Dr0..Dr3; max 4 slots; survive code patches)
d.set_hw_bp("user32!MessageBoxW")           # execute BP, default size=1
d.set_hw_bp(addr, type="w", size=4)         # data write watchpoint
d.set_hw_bp(addr, type="rw", size=8)        # data R/W (x64 only)
d.set_hw_bp(addr, condition=..., action=..., name="...")
d.set_hw_bp(addr, threads=[tid])            # restrict to specific thread(s)
d.clear_hw_bp(addr_or_slot)
d.list_hw_bps()
# On hit: ev["hit_hw_bp"] == {slot, addr, type, size, name, dr6_raw}.
# detach() clears all DRs automatically; kill() is safe regardless.

# State
d.get_regs() / d.set_reg("Rip", val)
d.read_mem(addr, n) / d.write_mem(addr, hex_or_bytes)
d.read_u32(addr) / d.read_cstr(addr) / d.read_wstr(addr)
d.disasm(addr, count=10)
d.assemble("mov rax, 1; ret")

# Lookup
d.resolve("module!name")                    # → addr (0 if unresolved)
d.addr_to_symbol(addr)                      # → {module, name, offset}
d.list_modules() / d.module_info("user32")
d.module_exports("user32") / d.module_imports("user32")
d.list_threads(enrich=True)                 # tid, Eip/Rip, suspend_count, …
d.thread_history()                          # exited threads
d.suspend_all() / d.resume_all()

# Meta
d.version()                                 # build id (git SHA + pkg version)
d.event_info()                              # last debug event dict
```
