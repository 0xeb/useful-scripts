# `upy.rrepl-dbg` — single-file guide for clients & AI agents

This is the **only** document you need to use the Windows x86/x64
user-mode debugger plugin over `upy.rrepl`. The plugin auto-detects
WOW64 (32-bit guest under 64-bit Windows) on `spawn()`/`attach()` and
adapts its register, disasm, and assemble paths transparently —
`get_regs()` returns `Eax/Ebx/.../Eip/EFlags` for 32-bit targets and
`Rax/Rbx/.../Rip/EFlags` for 64-bit. The full API, event shapes,
recipes, troubleshooting, and an async / stateful operation note for AI
coding agents follow.

If you're an AI agent: skim TL;DR → "For AI agents" → API table.
Everything else is on-demand reference.

---

## 0. TL;DR

```bash
# On the rrepl server host (Windows):
pip install upyscripts[rrepl-dbg]
python -m upyscripts.rrepl.cli serve --host 0.0.0.0 --port 8765
```

```python
# From any client (any OS):
from upyscripts.rrepl.plugins.dbg import Dbg

d = Dbg("http://winhost:8765", session="dbg")
sp = d.spawn(r"C:\path\to\target.exe")              # 1st call lazy-loads plugin
entry = sp["first_event"]["image_base"] + 0x1000    # placeholder offset
d.set_bp(entry)
d.cont(timeout_ms=5000)                             # runs until the BP fires
print(d.get_regs()["Rip"])
d.kill()
```

The first `Dbg` method call sends one tiny `import` line into the rrepl
session and creates the singleton `DBG`. From that moment, the
debugger's whole state lives on the server in that session — surviving
across every subsequent HTTP request from any client.

---

## 1. Why this exists (especially for AI agents)

`rrepl` is an HTTP REPL with **named, persistent Python sessions**. The
`dbg` plugin layers a Win32 user-mode debugger on top of one of those
sessions. The combination is purpose-built for **asynchronous, stateful
agent loops**:

- Agent starts a process at 10:00 ("`d.spawn(...)`").
- At 10:15 it inspects registers (`d.get_regs()`).
- At 10:42 it patches some memory and changes RIP.
- At 11:30 it finally `d.cont()`s and watches an exception fire.

Each of those is one independent HTTP request. The agent does **not**
hold a debugger handle in its own memory; the OS process being debugged
and the Python `Debugger` object both live in the rrepl session on the
Windows host. Restarting the agent, the Claude conversation, the local
script, even the agent's container — none of those touch the debuggee.
Only an explicit `d.kill()`, session reset, or rrepl-host restart does.

Every action you can take is just one POST to `/api/v1/exec` carrying a
small Python snippet. Nothing more exotic.

---

## 2. Architecture in one picture

```
+----------------------+        HTTP        +--------------------------------+
|  agent / client      |   /api/v1/exec     |  rrepl on Windows :8765         |
|  (any OS)            |  ───────────────▶  |--------------------------------|
|  Dbg(...)            |  {"code","session" |  session 'dbg' globals:        |
|  -> RReplClient      |    : "dbg"}        |    DBG = Debugger() (singleton)|
|     .exec(snippet)   |                    |    └─ worker thread             |
|                      |  ◀───────────────  |       └─ Win32 Debug API       |
|                      |  {"stdout":"…",    |          ├─ debuggee child     |
|                      |   "ok":true}       |          ├─ BP table           |
+----------------------+                    |          └─ module/thread state|
                                            +--------------------------------+
```

Two essentials:

1. **Worker-thread inside the session.** Win32 ties
   `WaitForDebugEvent`/`ContinueDebugEvent` to the OS thread that
   created the debuggee, but rrepl serves each HTTP request on a
   different thread. To bridge that, `Debugger.__init__` starts a
   dedicated daemon thread (`dbg-worker`); every public method posts a
   callable onto its queue. You don't need to think about it — it's
   transparent. But this is why everything is reliable across your
   stateless HTTP calls.

2. **Bounded HTTP calls.** Every method that resumes the debuggee uses
   `WaitForDebugEvent(timeout_ms)` with a finite budget (default
   2000 ms). If nothing fires in that window, you get
   `{"event": "timeout", "running": true}`. Loop on it; never expect
   one HTTP call to "wait forever".

---

## 3. Setup

### Server (Windows host running rrepl)

```bash
pip install upyscripts[rrepl-dbg]
# installs upyscripts + capstone + keystone-engine. pefile is already a
# top-level dep of upyscripts, so no extra step.

python -m upyscripts.rrepl.cli serve --host 0.0.0.0 --port 8765
# binds 0.0.0.0 so other machines can reach it. Run inside a trusted LAN.
```

The plugin module sits idle on the filesystem until a session imports
it. **No** debug capability is exposed at process startup; the server
is just an HTTP REPL.

### Client (anywhere)

```bash
pip install upyscripts          # gives you Dbg + RReplClient
```

The client wrapper uses only stdlib + `requests`. No Windows-only deps.

### Verifying it works

```python
from upyscripts.rrepl.plugins.dbg import Dbg
d = Dbg("http://winhost:8765", session="dbg")
print(d.cli.health())   # {'ok': True, 'service': 'rrepl'}
```

### Discovering installed plugins

```python
from upyscripts.rrepl.plugins import list_plugins, load_manifest
list_plugins()
# [{'name': 'dbg', 'manifest': {...}, 'module': 'upyscripts.rrepl.plugins.dbg'}]
load_manifest("dbg")
# {'name':'dbg','version':'0.1.0','platform':'win32',
#  'server_requires':[...], 'loaded_key':'DBG', 'guide': '/path/to/GUIDE.md',
#  'client_class':'upyscripts.rrepl.plugins.dbg.client:Dbg', ...}
```

---

## 4. The lazy plugin-load mechanism

The first `Dbg` method call (or explicit `d.ensure_loaded()`) sends one
small probe + bootstrap into the rrepl session:

```python
# probe (run by ensure_loaded → is_loaded)
import json as _j
print("__R__" + _j.dumps("DBG" in globals() and globals().get("DBG") is not None))

# if probe says False:
from upyscripts.rrepl.plugins.dbg.server import Debugger as _Debugger
DBG = globals().get("DBG") or _Debugger()
```

After this, the session globals contain:

| name        | value                                                  |
| ----------- | ------------------------------------------------------ |
| `DBG`       | `Debugger` singleton (worker-thread + `_DbgImpl`)      |
| `_Debugger` | the class itself                                       |

Every subsequent `Dbg.<method>()` call sends:

```python
import json as _j
_args = _j.loads('[…json args…]')
_kw   = _j.loads('{…json kwargs…}')
_r = DBG.<method>(*_args, **_kw)
print("__R__" + _j.dumps(_r, default=str))
```

The client parses the line that starts with `__R__` and returns the
JSON-decoded value. That's the entire protocol.

You can also drop into raw mode at any time:

```python
d.exec_inline("DBG.list_modules()[0]['name']")  # raw exec; returns ExecResponse dict
```

---

## 5. Where the process is suspended on first spawn

Empirically (verified against an x64 console PE on Windows 10):

| right after `d.spawn(...)`                                        |
| ----------------------------------------------------------------- |
| `first_event = CREATE_PROCESS_DEBUG_EVENT`                        |
| `image_base = <runtime ASLR base>`                                |
| **thread RIP NOW** = somewhere inside `ntdll!RtlUserThreadStart`/ |
| `LdrInitializeThunk` — i.e. *before* the user-mode loader runs   |
| `list_modules()` shows only the EXE; ntdll is mapped but Windows  |
|     never fires a LOAD_DLL event for it                           |
| nothing in the EXE has executed: not entry, not TLS, not CRT      |

This is the perfect moment to set breakpoints. Sequence after
`cont()`:

1. `LdrInitializeThunk` runs → many `LOAD_DLL_DEBUG_EVENT`s
2. OS injects an `int3` (the **loader breakpoint**)
3. Each DLL's `DllMain(DLL_PROCESS_ATTACH)`
4. EXE's TLS callbacks (in order from `IMAGE_TLS_DIRECTORY.AddressOfCallBacks`,
   stopping at the first NULL pointer)
5. EXE `AddressOfEntryPoint`
6. CRT startup → `main` / `WinMain`

`d.entry_points()` returns 4 + 5 in execution order;
`d.break_on_entry_points()` arms a software BP on each.

---

## 6. Full API reference

All addresses accept `int`, hex string `"0x140..."`, or plain decimal
strings. All numeric returns are `int`. Memory `hex` fields are
lowercase hex strings. Every dict returned is JSON-serialisable.

### 6.1 Lifecycle

| method                          | returns                                                          |
| ------------------------------- | ---------------------------------------------------------------- |
| `spawn(path, args="")`          | `{pid, tid, image_base, first_event}` — debuggee paused at CREATE_PROCESS |
| `attach(pid)`                   | `{pid, first_event}` — first event is the OS-injected break-in   |
| `detach()`                      | `{detached: bool}` — clears all BPs first                        |
| `kill()`                        | `{killed: True, exit_code}` — drains EXIT_PROCESS                |

### 6.2 Event pump & resume

| method                                            | returns                                                          |
| ------------------------------------------------- | ---------------------------------------------------------------- |
| `wait(timeout_ms=500)`                            | one event dict, or `{event:"timeout", running:true}` — does not ack |
| `continue_event(handled=True)`                    | the event that was acked, or `None`                              |
| `cont(timeout_ms=2000, handled=None, raw=False)`  | next event; with `raw=True`, no internal-event filtering         |
| `step(n=1)`                                       | last event (typically `EXCEPTION/SINGLE_STEP`)                   |
| `step_over()`                                     | last event — `CALL`/`REP*` are stepped over via a one-shot BP   |

`handled` semantics for `cont` / `continue_event`:

- `True` → `DBG_CONTINUE` (debugger handled the exception).
- `False` → `DBG_EXCEPTION_NOT_HANDLED` (let SEH propagate to the
  program).
- `None` (default for `cont`) → auto: BP / SINGLE_STEP / WX86 are
  treated handled; anything else → unhandled.

### 6.3 Breakpoints

| method                          | returns                                                       |
| ------------------------------- | ------------------------------------------------------------- |
| `set_bp(addr_or_symbol, condition=None, action=None, name=None)` | `{set: bool, addr, orig?, name?, condition?, action?, symbol?}`. Refuses on a real `int3`. Accepts an int, hex string, or `module!name` symbol. **Conditional/action scripts run on the worker thread when the BP fires.** `condition` is an expression — falsy → BP silently skipped (transparent: no client event). `action` is a Python block — set `result = "resume"` to auto-resume after running (e.g. patch then continue). Namespace: `dbg`, `regs` (snapshot), `bp` (entry, `bp["state"]` survives across hits), `gstate` (cross-BP), `ev` (event). Errors fail-stop: if `condition` raises, the BP surfaces with `bp_script.condition_error`. |
| `clear_bp(addr_or_symbol)`      | `{cleared: bool, addr, orig?, name?, hits?, skipped?}` — same input forms as `set_bp`. Includes per-BP counters when the entry existed. |
| `list_bps()`                    | `[{addr, orig, name, hits, skipped, condition?, action?, condition_error?, action_error?, symbol?}, …]` |
| `set_hw_bp(addr_or_symbol, type="x", size=1, condition=None, action=None, name=None, slot=None, threads=None)` | Hardware BP via Dr0..Dr3 + Dr7. Up to **4 slots**, process-global by default (auto-applied to existing threads and to threads created later via the CREATE_THREAD hook). `type ∈ {"x","w","rw"}` — `"x"` = execute (size must be 1), `"w"` / `"rw"` = data watchpoint (size 1/2/4/8; 8 is x64-only). `"io"` is rejected (needs CR4.DE). `slot` auto-allocates by default. `threads=[tid,...]` restricts the BP to specific threads. Returns `{set: bool, slot, addr, type, size, name?, condition?, action?, applied_to: [tids], symbol?, apply_errors?}`; failures return `{set: false, reason, ...}`. Same `condition`/`action` semantics and namespace as `set_bp`. |
| `clear_hw_bp(addr_or_slot)`     | Remove by slot int, address, or `module!name` symbol. Zeroes Dr_n + Dr7 bits on every thread the BP was applied to. Returns `{cleared: bool, slot, addr, type, size, name?, hits, skipped}`. |
| `list_hw_bps()`                 | `[{slot, addr, type, size, name, hits, skipped, condition?, action?, condition_error?, action_error?, threads?, symbol?}, …]` sorted by slot. |

Patching memory over a software BP automatically invalidates that BP
(the saved "original" byte no longer applies). Hardware BPs don't
touch memory, so they survive code patches and integrity checks.

When a hardware BP fires, the event has `ev["hit_hw_bp"] = {slot, addr,
type, size, name, dr6_raw}` (a single dict, distinct from `hit_bp`
which is a bare int address for software BPs). For data watchpoints
`ev["address"]` reports the *next* instruction (Intel
"instruction-after-fault" semantics), while the watched address is the
`addr` field of `hit_hw_bp`.

`detach()` clears all DRs on every tracked thread before
`DebugActiveProcessStop`, so a detached debuggee never inherits stale
debug-register state.

### 6.4 Registers

| method                                | returns                                                |
| ------------------------------------- | ------------------------------------------------------ |
| `get_regs(tid=None)`                  | `{Rip, Rax..R15, EFlags, SegCs..SegSs}`                |
| `set_reg(name, value, tid=None)`      | `{set, register, value}` — name is case-insensitive    |

`set_reg("Rip", new_addr)` redirects execution; the next `cont`/`step`
resumes from there. If a BP was awaiting re-arm at the old RIP, it is
re-armed cleanly and the debugger does not single-step the old
instruction.

### 6.5 Memory — raw bytes

| method                                            | returns                            |
| ------------------------------------------------- | ---------------------------------- |
| `read_mem(addr, n)`                               | `{addr, size, hex}`                |
| `write_mem(addr, hex_or_bytes, flush=True)`       | `{addr, wrote, flushed}`           |

`write_mem` accepts a hex string (spaces ok), or a `bytes`/`bytearray`
object. It always calls `FlushInstructionCache` — harmless on data,
necessary if you happen to be writing executable code.

### 6.6 Memory — typed (little-endian, x64 native)

| read                                           | write                                          |
| ---------------------------------------------- | ---------------------------------------------- |
| `read_u8 / u16 / u32 / u64(addr)`              | `write_u8 / u16 / u32 / u64(addr, v)`          |
| `read_i8 / i16 / i32 / i64(addr)`              | `write_i8 / i16 / i32 / i64(addr, v)`          |
| `read_ptr(addr)` — u64 alias                   | `write_ptr(addr, v)`                           |
| `read_f32 / f64(addr)`                         | `write_f32 / f64(addr, v)`                     |
| `read_cstr(addr, max_len=256)`                 | `write_cstr(addr, s, nul=True)` (Latin-1)      |
| `read_wstr(addr, max_chars=256)`               | `write_wstr(addr, s, nul=True)` (UTF-16 LE)    |
| `read_int(addr, size, signed=False)` (generic) | `write_int(addr, v, size, signed=False)`       |

### 6.7 Assembly / disassembly

| method                                | returns                                                       |
| ------------------------------------- | ------------------------------------------------------------- |
| `assemble(asm, addr=0)`               | `{hex, size, count}` — keystone x64                           |
| `write_asm(addr, asm)`                | `{addr, wrote, count}` — assemble + patch + flush + invalidate-overlapping-BPs |
| `disasm(addr=None, count=10)`         | `[{addr, size, bytes, mnemonic, op_str}, …]` — capstone, hides live `0xCC` of user BPs |

### 6.8 Modules / threads / event state

| method                          | returns                                              |
| ------------------------------- | ---------------------------------------------------- |
| `list_modules(with_exports=False, with_imports=False)` | rich rows: `{base, name, path, size, entry_rva, entry, is_image, machine, timestamp, loaded_at, loaded_seq[, exports, imports]}` populated from CREATE_PROCESS / LOAD_DLL events, removed on UNLOAD_DLL. Cheap PE-header parse runs at insert time; exports/imports lazy-load on first request and cache. `with_exports/imports=True` is heavy (ntdll has ~2500 exports) — prefer per-module fetch below. |
| `module_info(name_or_base, with_exports=False, with_imports=False)` | One row, or `None`. Name match is case-insensitive on basename, path, or stem; numeric/hex strings match base. |
| `module_exports(name_or_base)`  | `[{name, ordinal, rva, addr, forwarder}, …]` parsed via `pefile`. Forwarded entries have `forwarder="OTHER.Symbol"` and `addr=0`. |
| `module_imports(name_or_base)`  | `[{module, name, ordinal, iat_rva, iat_addr}, …]` |
| `module_history(limit=64)`      | recent UNLOAD_DLL entries (`{base, name, path, size, entry, loaded_at, loaded_seq, unloaded_at, unloaded_seq, lifetime_ms}`). Bounded ring buffer (default 64); survives `kill()`. |
| `resolve(symbol, follow_forwarders=True)` | int — translates `module!name`, `module!#<ordinal>`, or a bare `name` (searched across all loaded modules) to a virtual address. Returns 0 when unresolved. |
| `addr_to_symbol(addr)`          | best-effort closest-export resolution: `{module, name, ordinal, rva, offset, in_module}` or `None`. |
| `list_threads(enrich=False, reconcile=False)` | `[{tid, start_address, is_main, created_at, created_seq, discovered, current[, start_module, start_offset, start_symbol, start_symbol_offset]}, …]` from event-driven tracking. `enrich=True` adds `rip`, `suspend_count`, `rip_module`, `rip_offset[, rip_symbol, rip_symbol_offset]` (briefly suspends each thread for a coherent read). `reconcile=True` merges in any tid present in a Toolhelp32 snapshot but missing from the table (will be flagged `discovered=True`). |
| `thread_info(tid, enrich=False)`| One tracked row, or `None` if the tid isn't tracked. |
| `thread_history(limit=64)`      | Up to `limit` most-recent EXIT_THREAD entries (oldest first), each with `tid, start_address, is_main, exit_code, created_at, exited_at, lifetime_ms, created_seq, exited_seq`. Bounded ring buffer (default 256). Survives `kill()` so callers can post-mortem. |
| `suspend_thread(tid)` / `resume_thread(tid)` | `{tid, prev_count, count}` — wraps `SuspendThread`/`ResumeThread`. Thread actually runs again only when count reaches 0. Records `discovered=True` for any tid passed in that we hadn't seen via debug events. |
| `suspend_all(exclude=None)` / `resume_all(exclude=None)` | one row per tracked tid (skipping any in `exclude`) with the same shape, or `{tid, error}` on failure. |
| `current_thread()`              | int — tid of last stop                               |
| `event_info()`                  | the most recent event dict, or `None`                |

The `_threads` table is maintained from CREATE_PROCESS / CREATE_THREAD /
EXIT_THREAD events absorbed by the worker (these are filtered as
`internal` so they don't surface to `cont()`); the `discovered=True` flag
marks rows whose handle was opened lazily via `OpenThread` rather than
seen as a debug event (e.g. an attach that happened before the thread
was created, or a tid you handed to `suspend_thread`).

### 6.9 Entry points

| method                          | returns                                              |
| ------------------------------- | ---------------------------------------------------- |
| `entry_points()`                | `[{kind, addr, source[, index]}, …]` — TLS callbacks (loader-stops at first NULL) then PE EntryPoint |
| `break_on_entry_points()`       | same list, augmented with each entry's `{bp: …}`     |

Static info comes from `pefile` against the on-disk EXE (path is
collected from `CREATE_PROCESS_DEBUG_EVENT`); the **callback array
contents** are read from the live process so ASLR-relocated pointers
are returned.

---

## 7. Event dictionary reference

`wait()` and `cont(raw=True)` return one of these shapes:

| `event`                | fields                                                                                              |
| ---------------------- | --------------------------------------------------------------------------------------------------- |
| `CREATE_PROCESS`       | `pid, tid, image_base, image_path, entry` *(lpStartAddress)*                                        |
| `CREATE_THREAD`        | `pid, tid, start_address`                                                                           |
| `LOAD_DLL`             | `pid, tid, base, path`                                                                              |
| `UNLOAD_DLL`           | `pid, tid, base, name`                                                                              |
| `EXIT_THREAD`          | `pid, tid, exit_code`                                                                               |
| `EXIT_PROCESS`         | `pid, tid, exit_code, running=False`                                                                |
| `OUTPUT_DEBUG_STRING`  | `pid, tid, string` *(already decoded; ASCII or UTF-16 per fUnicode)*                                |
| `EXCEPTION`            | `pid, tid, exception, code` *(NTSTATUS u32)*, `address, first_chance, hit_bp?, loader_bp?`           |
| `timeout`              | `running=True` — try again                                                                          |

The `cont()` filter swallows internal events (LOAD_DLL, UNLOAD_DLL,
CREATE_THREAD, EXIT_THREAD, OUTPUT_DEBUG_STRING, the OS loader BP, our
own re-arm single-step). Pass `raw=True` if you want everything.

---

## 8. Recipes

### 8.1 Minimum working example (covers ~80% of the API)

```python
from upyscripts.rrepl.plugins.dbg import Dbg, fmt_disasm, fmt_regs
import time

d = Dbg("http://winhost:8765", session="dbg")
sp = d.spawn(r"C:\Path\To\target.exe")
print("paused at", hex(d.get_regs()["Rip"]))      # inside ntdll

# walk the natural startup flow
d.break_on_entry_points()
for ep in d.entry_points():
    end = time.time() + 10
    while time.time() < end:
        ev = d.cont(timeout_ms=2000)
        if ev.get("hit_bp"): break
    print(f"hit {ep['kind']}: RIP={d.get_regs()['Rip']:#x}")
print(fmt_disasm(d.disasm(count=4)))

# poke around
print(fmt_regs(d.get_regs()))
print(d.read_u32(d.get_regs()["Rsp"]))            # top stack u32
d.write_asm(d.get_regs()["Rip"], "nop; nop; nop") # live patch
d.set_reg("Rip", d.get_regs()["Rip"] + 3)         # skip them
d.step(3)

d.kill()
```

### 8.2 Walk every debug event with full parameters

```python
sp = d.spawn(r"C:\target.exe")
while True:
    ev = d.cont(timeout_ms=2000, raw=True)
    if ev["event"] == "timeout":  continue
    print(ev["event"], ev.get("path") or ev.get("exception") or "")
    if ev["event"] == "EXIT_PROCESS": break
    if ev["event"] == "EXCEPTION" and ev.get("hit_bp"): break
```

### 8.3 Manual loop with explicit ack

`wait` does **not** ack — the OS won't deliver another event until you
do. Order matters: ack the previous event before requesting the next.

```python
sp = d.spawn(r"C:\target.exe")
while True:
    d.continue_event(handled=True)            # ack previous
    ev = d.wait(timeout_ms=500)
    if ev["event"] == "timeout":             continue
    print("EVENT:", ev["event"])
    if ev["event"] == "EXIT_PROCESS": break
```

### 8.4 Resume options — let an exception propagate to SEH

```python
ev = d.cont(timeout_ms=2000)
if ev["event"] == "EXCEPTION" and ev["first_chance"] and not ev.get("hit_bp"):
    print("first-chance exc:", ev["exception"], hex(ev["address"]))
    # let the program's __try/__except handle it
    d.continue_event(handled=False)
```

### 8.5 Break on an exported function in a named DLL

```python
def export_addr(d, mod_name: str, fn: str) -> int:
    m = d.module_info(mod_name)
    assert m, f"module not loaded: {mod_name}"
    code = f'''
import pefile, json as _j
pe = pefile.PE({m['path']!r}, fast_load=True)
pe.parse_data_directories(directories=[
    pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
rva = None
for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if exp.name and exp.name.decode(errors='ignore').lower() == {fn.lower()!r}:
        rva = exp.address; break
print('__R__' + _j.dumps(rva))
'''
    rva = d._exec_marker(code)
    return m["base"] + int(rva)

addr = export_addr(d, "kernel32.dll", "CreateFileW")
d.set_bp(addr)
d.cont(timeout_ms=8000)
```

(Works after `kernel32.dll` is loaded — i.e. after the first `cont`,
not at CREATE_PROCESS.)

### 8.6 Live patch with mnemonics

```python
d.write_asm(d.get_regs()["Rip"], "nop; nop; xor eax, eax")
print(fmt_disasm(d.disasm(count=4)))
```

### 8.7 Redirect execution

```python
d.set_reg("Rip", new_address)
# next cont/step resumes from new_address; any pending BP re-arm is honored
```

### 8.8 Read / write typed data

```python
d.write_u32(addr, 0xDEADC0DE);          d.read_u32(addr)
d.write_i32(addr, -42);                 d.read_i32(addr)
d.write_u64(addr, 0x1122334455667788);  d.read_u64(addr)
d.write_ptr(addr, image_base);          d.read_ptr(addr)
d.write_f64(addr, 3.14159265358979);    d.read_f64(addr)
d.write_cstr(addr, "hello");            d.read_cstr(addr)
d.write_wstr(addr, "wide 中文");        d.read_wstr(addr)
```

### 8.9 Recover a wedged session

```bash
# kill the debuggee inside the session
curl -s -X POST http://winhost:8765/api/v1/exec \
     -H "Content-Type: application/json" \
     -d '{"session":"dbg","code":"DBG.kill()"}'

# wipe the session entirely (DBG goes; debuggee is gone too thanks to
# DebugSetProcessKillOnExit set on spawn)
curl -s -X POST http://winhost:8765/api/v1/reset \
     -H "Content-Type: application/json" \
     -d '{"session":"dbg"}'
```

Last resort: `taskkill /F /IM target.exe` on the Windows host.

### 8.10 Detach vs kill

| operation       | effect                                                                  |
| --------------- | ----------------------------------------------------------------------- |
| `d.detach()`    | clears all BPs, debuggee keeps running, debugger releases the process   |
| `d.kill()`      | `TerminateProcess` then drains EXIT_PROCESS                             |
| session reset   | drops `DBG`; OS auto-kills (KillOnExit was set on spawn)                |

If you used `attach()` instead of `spawn()`, KillOnExit is **False**, so
session reset will not take the process down with it.

### 8.11 Inline Python when the API doesn't have what you need

For pure inspection, just call `DBG` from inline code:

```python
result = d.exec_inline(r"""
import json
out = [m for m in DBG.list_modules() if m["name"].lower().startswith("ntdll")]
print("__R__" + json.dumps(out))
""")
print(result["stdout"])
```

For ad-hoc work that needs Win32 Debug API calls (WFDE/CDE,
GetThreadContext, …), post onto the worker queue so thread-affinity
holds:

```python
d.exec_inline(r"""
import queue, json
reply = queue.Queue()
def _work():
    rip = DBG._impl.get_regs()["Rip"]
    return {"rip": rip, "bytes": DBG._impl.read_mem(rip, 16)["hex"]}
DBG._q.put((_work, (), {}, reply))
kind, val = reply.get()
print("__R__" + json.dumps(val if kind == "ok" else {"error": str(val)}))
""")
```

Promote useful patterns to real methods: add to `_DbgImpl`, append to
`Debugger._PROXY_METHODS`, and add a one-line proxy on `Dbg`.

---

## 9. Troubleshooting

| symptom                                                               | what's likely going on                                                                                          |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: capstone` (or keystone)                         | server admin forgot `pip install upyscripts[rrepl-dbg]`                                                         |
| `set_bp(...)` returns `{"reason": "real_int3"}`                       | byte at addr is already `0xCC` — either an actual `int3` in the binary or a previous BP wasn't restored        |
| `cont()` keeps returning `{"event":"timeout"}`                        | nothing's firing in the budget — process is in user code with no events, or you set the BP after it was passed |
| `RIP == addr+1` after a BP hit                                        | shouldn't happen with current code; check that `_pending_reArm` wasn't cleared by manual `set_reg("Rip", …)`   |
| `Dbg(...).spawn(...)` hangs ~30s                                      | rrepl HTTP timeout; the host is unreachable. `d.cli.health()` first.                                            |
| `Dbg(...).spawn(...)` raises `RReplExecutionError: ImportError`       | server doesn't have the rrepl-dbg extras installed                                                              |
| Debuggee survived after I killed my agent / closed my laptop          | exactly as designed — local clients don't own the debuggee. Run `d.kill()` or curl-reset the session            |

---

## 10. For AI agents

You are the intended audience. A few notes that save tokens and round-trips:

- **This file is the entire learning surface.** No external docs are
  required. `Dbg.guide()` returns its contents as a string;
  `Dbg.guide_path` gives the absolute path on disk.
- **The wrapper is idempotent.** Calling `Dbg(...)` and a method again
  in a fresh process re-uses the same session state on the server.
  `is_loaded()` is a cheap probe. `ensure_loaded()` is safe to call
  often.
- **You don't carry any state.** All debugger state lives on the
  server, keyed by session name. Pick a memorable session name (e.g.
  `"dbg"` or `"dbg-investigation-42"`) so you can reconnect later.
- **Errors come back structured.** `RReplExecutionError.payload["error"]`
  has `type`, `message`, `traceback` — feed that back to your reasoning
  loop verbatim instead of paraphrasing.
- **Bounded calls, never blocking.** Default `cont(timeout_ms=2000)`.
  Loop with bigger budgets if needed; never assume one HTTP request
  can wait forever.
- **Pre-existing in-session globals** after lazy load: `DBG`,
  `_Debugger`, plus everything `server.py` imported at the top
  (`ctypes`, `struct`, `pefile`, `capstone`, `keystone`, `os`, `queue`,
  `threading`). Useful when you need an inline snippet.
- **The session is yours alone if you pick a unique name.** Multiple
  debuggees can be active simultaneously across different sessions
  with no interference.

### Minimum reconnect template

If you're an agent picking up an existing investigation:

```python
from upyscripts.rrepl.plugins.dbg import Dbg
d = Dbg("http://winhost:8765", session="dbg-<your-id>")

# Probe what's there. is_loaded returns True iff DBG already exists.
if not d.is_loaded():
    print("session is empty — no debuggee. Use d.spawn(...) to start one.")
else:
    # Pick up where you (or an earlier agent) left off
    print("RIP:", hex(d.get_regs()["Rip"]))
    print("BPs:", d.list_bps())
    print("modules:", len(d.list_modules()))
```

That's it. Everything else is in §6 and §8 above.
