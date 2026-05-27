"""End-to-end tests for upy.rrepl-dbg against a live remote rrepl server.

These tests skip unless an rrepl URL is configured (env ``RREPL_URL`` or
``.claude/rrepl.json``) AND the remote host is Windows. They each
allocate their own session, spawn or kill notepad as needed, and clean
up after themselves.

Targets used:

  * ``C:\\Windows\\System32\\notepad.exe``  — 64-bit
  * ``C:\\Windows\\SysWoW64\\notepad.exe``  — 32-bit (WOW64)
  * ``user32!MessageBoxW``                  — symbol target for BPs

To trigger a BP we inject ``CreateRemoteThread`` pointing at
``MessageBoxW``; the thread fires the BP at the function prologue
before any argument is dereferenced, so the bogus arg vector is safe.
"""

from __future__ import annotations

import json
import textwrap
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exec(client, code: str, session: str) -> dict:
    """Run code on the remote rrepl, raise if the remote raised."""
    payload = client.exec(textwrap.dedent(code), session=session)
    if not payload.get("ok"):
        err = payload.get("error") or {}
        raise AssertionError(
            f"remote exec failed: {err.get('type')}: {err.get('message')}\n"
            f"{err.get('traceback', '')}\n--- code ---\n{code}"
        )
    return payload


def _stdout_json(payload: dict):
    """Tests print a single JSON line; this helper parses it back."""
    return json.loads(payload["stdout"].strip().splitlines()[-1])


@pytest.fixture
def dbg_session(rrepl_client, rrepl_dbg_available):
    """Per-test session name; tears down by best-effort killing any
    debuggee and deleting the session. Even if DBG.kill() hangs because
    the worker is stuck mid-BP-dance, the trailing taskkill / delete
    ensures the next test sees a clean rrepl host."""
    name = f"pytest-dbg-{uuid.uuid4().hex[:8]}"
    yield name
    try:
        rrepl_client.exec(
            textwrap.dedent("""
                import subprocess
                pid = None
                try:
                    pid = DBG.pid  # type: ignore[name-defined]
                except Exception:
                    pass
                try:
                    DBG.kill()      # type: ignore[name-defined]
                except Exception:
                    pass
                if pid:
                    subprocess.run(["taskkill","/F","/PID", str(pid)],
                                   capture_output=True)
            """),
            session=name,
        )
    except Exception:
        pass
    try:
        rrepl_client.delete_session(name)
    except Exception:
        pass


def _bootstrap_dbg(rrepl_client, session: str, target_path: str) -> dict:
    """Spawn the target under the debugger in `session`, settle the loader,
    and return {pid, wow64, threads, modules}."""
    payload = _exec(
        rrepl_client,
        f"""
        from upyscripts.rrepl.plugins.dbg.server import Debugger as _D
        DBG = _D()
        sp = DBG.spawn(r"{target_path}")
        ev = DBG.cont(timeout_ms=4000)
        import json
        print(json.dumps({{
            "pid": sp["pid"],
            "wow64": sp["wow64"],
            "settle": ev.get("event"),
            "threads": len(DBG._impl._threads),
            "modules": len(DBG._impl._modules),
        }}))
        """,
        session,
    )
    return _stdout_json(payload)


# ---------------------------------------------------------------------------
# version() smoke
# ---------------------------------------------------------------------------

def test_version_returns_plugin_and_build(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    payload = _exec(
        rrepl_client,
        """
        from upyscripts.rrepl.plugins.dbg.server import Debugger as _D
        DBG = _D()
        import json; print(json.dumps(DBG.version()))
        """,
        dbg_session,
    )
    info = _stdout_json(payload)
    assert info.get("plugin") == "upy.rrepl-dbg"
    # build id may be a git SHA or fallback string — just require non-empty.
    assert info.get("build")


# ---------------------------------------------------------------------------
# Module exports / resolve / addr_to_symbol
# ---------------------------------------------------------------------------

def test_module_exports_and_resolve_user32_messageboxw(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    info = _bootstrap_dbg(rrepl_client, dbg_session,
                          r"C:\\Windows\\System32\\notepad.exe")
    assert info["wow64"] is False
    assert info["modules"] >= 5

    payload = _exec(
        rrepl_client,
        """
        import json
        m = DBG.module_info("user32")
        exps = DBG.module_exports("user32")
        a = DBG.resolve("user32!MessageBoxW")
        sym = DBG.addr_to_symbol(a)
        out = {
            "have_user32": m is not None,
            "size": m["size"] if m else None,
            "machine": m["machine"] if m else None,
            "export_count": len(exps),
            "found_messagebox": any(e["name"] == "MessageBoxW" for e in exps),
            "resolved_addr": a,
            "sym_module": (sym or {}).get("module"),
            "sym_name": (sym or {}).get("name"),
        }
        print(json.dumps(out))
        DBG.kill()
        """,
        dbg_session,
    )
    out = _stdout_json(payload)
    assert out["have_user32"] is True
    assert out["machine"] == 0x8664           # x64 PE
    assert out["export_count"] > 100
    assert out["found_messagebox"] is True
    assert out["resolved_addr"] != 0
    assert out["sym_name"] == "MessageBoxW"


# ---------------------------------------------------------------------------
# WOW64 (32-bit) coverage
# ---------------------------------------------------------------------------

def test_wow64_spawn_yields_32bit_register_set(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    info = _bootstrap_dbg(rrepl_client, dbg_session,
                          r"C:\\Windows\\SysWoW64\\notepad.exe")
    assert info["wow64"] is True

    payload = _exec(
        rrepl_client,
        """
        import json
        regs = DBG.get_regs()
        m = DBG.module_info("user32")
        out = {
            "has_eip": "Eip" in regs,
            "has_rip": "Rip" in regs,
            "has_eax": "Eax" in regs,
            "machine": m["machine"] if m else None,
            "user32_path": (m or {}).get("path", "").lower(),
        }
        print(json.dumps(out))
        DBG.kill()
        """,
        dbg_session,
    )
    out = _stdout_json(payload)
    assert out["has_eip"] is True
    assert out["has_rip"] is False
    assert out["has_eax"] is True
    assert out["machine"] == 0x14C            # i386
    assert "syswow64" in out["user32_path"]


# ---------------------------------------------------------------------------
# Conditional / action breakpoints
# ---------------------------------------------------------------------------

_INJECT_HELPER = textwrap.dedent("""
    import ctypes, ctypes.wintypes as wt
    _k32 = ctypes.windll.kernel32
    _k32.CreateRemoteThread.argtypes = [
        wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
        ctypes.POINTER(wt.DWORD),
    ]
    _k32.CreateRemoteThread.restype = wt.HANDLE

    def _inject_n(n: int):
        h_proc = DBG._impl.h_process
        addr = DBG.resolve("user32!MessageBoxW")
        handles = []
        for _ in range(n):
            handles.append(_k32.CreateRemoteThread(
                h_proc, None, 0, ctypes.c_void_p(addr), None, 0, None))
        return handles
""")


def test_conditional_bp_with_false_condition_is_silent(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    """A condition that always evaluates falsy must produce no client-
    visible BP event, even though the underlying `int 3` fires. We don't
    constrain whether `cont()` returns "timeout" or some downstream
    exception (the resumed injected thread tends to AV inside MessageBoxW
    once it dereferences the bogus arg vector); we only require the
    *next surfaced event* to NOT carry `hit_bp`, and the counters to
    show the silent skips."""
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    code = _INJECT_HELPER + textwrap.dedent("""
        import json
        bp = DBG.set_bp("user32!MessageBoxW",
                        condition="False", name="never_stop")
        _inject_n(3)
        # Pump a little so all injected threads get a chance to hit.
        last = {}
        leaked = False
        for _ in range(4):
            last = DBG.cont(timeout_ms=2000)
            if "hit_bp" in last:
                leaked = True
                break
        rows = DBG.list_bps()
        out = {
            "set": bp.get("set"),
            "leaked": leaked,
            "hits": rows[0]["hits"],
            "skipped": rows[0]["skipped"],
        }
        print(json.dumps(out))
        DBG.kill()
    """)
    payload = _exec(rrepl_client, code, dbg_session)
    out = _stdout_json(payload)
    assert out["set"] is True
    # No conditional-skipped hit may ever surface to the client.
    assert out["leaked"] is False
    # At least one of the injected calls hit; every hit that was counted
    # was silently skipped. (The exact count is racy for a software BP
    # hammered by concurrent threads: during one thread's re-arm
    # single-step the 0xCC is briefly the original byte, so a sibling
    # executing that address in that window slips through untrapped.)
    assert out["hits"] >= 1
    assert out["skipped"] == out["hits"]


def test_action_bp_resumes_then_suspends_with_persistent_state(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    action = textwrap.dedent("""
        state["count"] = state.get("count", 0) + 1
        result = "suspend" if state["count"] >= 3 else "resume"
    """).strip()

    # Drive the BP deterministically: a one-byte `ret` stub in an RWX page,
    # fired by one injected thread at a time. Serial firing avoids the
    # software-BP re-arm race (during a thread's single-step the 0xCC is
    # briefly the original byte, so a concurrent sibling could slip past
    # uncounted). A bare `ret` cleanly returns into the thread init thunk,
    # so resumed threads exit without the access-violation noise that
    # MessageBoxW(bogus args) would produce.
    code = textwrap.dedent(f"""
        import ctypes, ctypes.wintypes as wt, json
        k32 = ctypes.windll.kernel32
        k32.VirtualAllocEx.argtypes = [
            wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
        k32.VirtualAllocEx.restype = ctypes.c_void_p
        k32.CreateRemoteThread.argtypes = [
            wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
            ctypes.POINTER(wt.DWORD)]
        k32.CreateRemoteThread.restype = wt.HANDLE

        h_proc = DBG._impl.h_process
        page = k32.VirtualAllocEx(h_proc, None, 0x1000, 0x3000, 0x40)  # RWX
        stub = DBG.assemble("ret")
        DBG.write_mem(page, stub["hex"])

        action = {action!r}
        bp = DBG.set_bp(page, action=action, name="stop_on_3rd")

        surfaced = []
        for i in range(3):
            k32.CreateRemoteThread(h_proc, None, 0, ctypes.c_void_p(page),
                                   None, 0, None)
            ev = DBG.cont(timeout_ms=3000)
            surfaced.append("hit_bp" in ev)

        rows = DBG.list_bps()
        meta = ev.get("bp_script") or {{}}
        out = {{
            "surfaced": surfaced,
            "had_hit_bp": "hit_bp" in ev,
            "meta_hits": meta.get("hits"),
            "action_result": meta.get("action_result"),
            "row_hits": rows[0]["hits"],
            "row_skipped": rows[0]["skipped"],
        }}
        print(json.dumps(out))
        DBG.kill()
    """)
    payload = _exec(rrepl_client, code, dbg_session)
    out = _stdout_json(payload)
    # First two hits auto-resume (silent), the third suspends.
    assert out["surfaced"] == [False, False, True]
    assert out["had_hit_bp"] is True
    assert out["meta_hits"] == 3
    assert out["action_result"] == "suspend"
    assert out["row_hits"] == 3
    assert out["row_skipped"] == 2


def test_set_bp_by_symbol_records_symbol_metadata(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    payload = _exec(
        rrepl_client,
        """
        import json
        bp = DBG.set_bp("user32!MessageBoxW")
        addr = bp["addr"]
        rows = DBG.list_bps()
        out = {
            "set": bp.get("set"),
            "has_symbol": "symbol" in bp,
            "symbol_name": bp.get("symbol", {}).get("name"),
            "row_symbol": rows[0].get("symbol"),
            "addr_nonzero": addr != 0,
        }
        print(json.dumps(out))
        DBG.kill()
        """,
        dbg_session,
    )
    out = _stdout_json(payload)
    assert out["set"] is True
    assert out["has_symbol"] is True
    assert out["symbol_name"] == "MessageBoxW"
    assert "MessageBoxW" in (out["row_symbol"] or "")
    assert out["addr_nonzero"] is True


def test_attach_reconciles_existing_threads(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    """Spawn -> detach (notepad keeps running standalone) ->  attach to it
    and verify reconciled_threads > 0 (since DebugActiveProcess does not
    always synthesize CREATE_THREAD events for pre-existing threads)."""
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    payload = _exec(
        rrepl_client,
        """
        import json, time
        pid = DBG.pid
        DBG.detach()
        # fresh debugger instance, attach to the still-running notepad
        DBG2 = type(DBG)()
        time.sleep(0.3)
        r = DBG2.attach(pid)
        rows = DBG2.list_threads()
        out = {
            "pid": pid,
            "wow64": r.get("wow64"),
            "reconciled_threads": r.get("reconciled_threads"),
            "rows_after_attach": len(rows),
        }
        print(json.dumps(out))
        DBG2.kill()
        """,
        dbg_session,
    )
    out = _stdout_json(payload)
    assert out["reconciled_threads"] is not None
    # notepad spawns several pool threads; we should at least pick up >0.
    assert out["reconciled_threads"] >= 1
    assert out["rows_after_attach"] >= 1


# ---------------------------------------------------------------------------
# Hardware breakpoints (Dr0..Dr3)
# ---------------------------------------------------------------------------

def test_hw_bp_execute_on_messageboxw(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    """Hardware execute BP at user32!MessageBoxW. Inject one
    CreateRemoteThread → MessageBoxW; verify the surfaced event carries
    `hit_hw_bp` with the resolved slot/addr/type."""
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    code = _INJECT_HELPER + textwrap.dedent("""
        import json
        bp = DBG.set_hw_bp("user32!MessageBoxW", name="hw_msgbox")
        addr = bp["addr"]
        _inject_n(1)
        for _ in range(8):
            ev = DBG.cont(timeout_ms=2000)
            if "hit_hw_bp" in ev:
                break
        rows = DBG.list_hw_bps()
        out = {
            "set": bp.get("set"),
            "slot": bp.get("slot"),
            "addr": addr,
            "had_hit_hw_bp": "hit_hw_bp" in ev,
            "hit_slot": (ev.get("hit_hw_bp") or {}).get("slot"),
            "hit_addr": (ev.get("hit_hw_bp") or {}).get("addr"),
            "hit_type": (ev.get("hit_hw_bp") or {}).get("type"),
            "row_hits": rows[0]["hits"] if rows else 0,
            "row_count": len(rows),
        }
        print(json.dumps(out))
        DBG.kill()
    """)
    payload = _exec(rrepl_client, code, dbg_session)
    out = _stdout_json(payload)
    assert out["set"] is True
    assert out["slot"] == 0
    assert out["had_hit_hw_bp"] is True
    assert out["hit_slot"] == 0
    assert out["hit_addr"] == out["addr"]
    assert out["hit_type"] == "x"
    assert out["row_hits"] >= 1
    assert out["row_count"] == 1


def test_hw_bp_propagates_to_new_threads(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    """Set the HW BP first, then inject 3 threads. Each newly-created
    thread must inherit the BP via the CREATE_THREAD propagation hook."""
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    code = _INJECT_HELPER + textwrap.dedent("""
        import json
        DBG.set_hw_bp("user32!MessageBoxW", name="hw_propagate")
        _inject_n(3)
        # Pump until the BP has fired at least 3 times (one per injected
        # thread). Each fire suspends; we just count via list_hw_bps()
        # between conts. We continue past suspends with another cont().
        for _ in range(20):
            ev = DBG.cont(timeout_ms=2000)
            if DBG.list_hw_bps()[0]["hits"] >= 3:
                break
        rows = DBG.list_hw_bps()
        out = {"hits": rows[0]["hits"]}
        print(json.dumps(out))
        DBG.kill()
    """)
    payload = _exec(rrepl_client, code, dbg_session)
    out = _stdout_json(payload)
    assert out["hits"] >= 3


def test_hw_bp_data_write_watchpoint(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    """Allocate a 4-byte buffer in the debuggee, set a HW write
    watchpoint on it, write to it from a remote thread, verify the BP
    fires with `type == "w"`."""
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    code = textwrap.dedent("""
        import ctypes, ctypes.wintypes as wt, json
        k32 = ctypes.windll.kernel32
        k32.VirtualAllocEx.argtypes = [
            wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
            wt.DWORD, wt.DWORD,
        ]
        k32.VirtualAllocEx.restype = ctypes.c_void_p
        k32.CreateRemoteThread.argtypes = [
            wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
            ctypes.POINTER(wt.DWORD),
        ]
        k32.CreateRemoteThread.restype = wt.HANDLE

        h_proc = DBG._impl.h_process
        MEM_COMMIT_RESERVE     = 0x3000
        PAGE_READWRITE         = 0x04
        PAGE_EXECUTE_READWRITE = 0x40

        # Data buffer to watch + an RX page holding a tiny stub that
        # writes to it. The stub takes the buffer pointer in rcx (x64
        # thread-start arg) and stores a dword: a guaranteed user-mode
        # write that trips the data watchpoint.
        data = k32.VirtualAllocEx(h_proc, None, 0x1000,
                                  MEM_COMMIT_RESERVE, PAGE_READWRITE)
        code_page = k32.VirtualAllocEx(h_proc, None, 0x1000,
                                       MEM_COMMIT_RESERVE,
                                       PAGE_EXECUTE_READWRITE)
        stub = DBG.assemble("mov dword ptr [rcx], 0x12345678; ret")
        DBG.write_mem(code_page, stub["hex"])

        bp = DBG.set_hw_bp(data, type="w", size=4, name="hw_write")
        k32.CreateRemoteThread(h_proc, None, 0,
                               ctypes.c_void_p(code_page),
                               ctypes.c_void_p(data), 0, None)

        ev = {}
        for _ in range(6):
            ev = DBG.cont(timeout_ms=1500)
            if "hit_hw_bp" in ev:
                break

        rows = DBG.list_hw_bps()
        out = {
            "data": data,
            "set": bp.get("set"),
            "type": bp.get("type"),
            "had_hit_hw_bp": "hit_hw_bp" in ev,
            "hit_type": (ev.get("hit_hw_bp") or {}).get("type"),
            "hit_addr": (ev.get("hit_hw_bp") or {}).get("addr"),
            "hits": rows[0]["hits"] if rows else 0,
        }
        print(json.dumps(out))
        DBG.kill()
    """)
    payload = _exec(rrepl_client, code, dbg_session)
    out = _stdout_json(payload)
    assert out["set"] is True
    assert out["type"] == "w"
    assert out["had_hit_hw_bp"] is True
    assert out["hit_type"] == "w"
    assert out["hit_addr"] == out["data"]
    assert out["hits"] >= 1


def test_hw_bp_conditional_skips_silently(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    """Same shape as the SW-BP silent-skip test: condition='False'
    means every hit is absorbed server-side. The surfaced event must
    NOT carry hit_hw_bp."""
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    code = _INJECT_HELPER + textwrap.dedent("""
        import json
        bp = DBG.set_hw_bp("user32!MessageBoxW",
                           condition="False", name="hw_skip")
        _inject_n(3)
        for _ in range(8):
            ev = DBG.cont(timeout_ms=2000)
            if DBG.list_hw_bps()[0]["hits"] >= 3:
                break
        rows = DBG.list_hw_bps()
        out = {
            "set": bp.get("set"),
            "had_hit_hw_bp": "hit_hw_bp" in ev,
            "hits": rows[0]["hits"],
            "skipped": rows[0]["skipped"],
        }
        print(json.dumps(out))
        DBG.kill()
    """)
    payload = _exec(rrepl_client, code, dbg_session)
    out = _stdout_json(payload)
    assert out["set"] is True
    assert out["had_hit_hw_bp"] is False
    assert out["hits"] == 3
    assert out["skipped"] == 3


# ---------------------------------------------------------------------------
# Review-fix regression tests
# ---------------------------------------------------------------------------

def test_worker_thread_released_and_debuggee_killed_on_reset(
    rrepl_client, rrepl_dbg_available,
):
    """Dropping a session's DBG (here via reset) must stop its dbg-worker
    thread and kill the spawned debuggee — i.e. no thread/handle leak per
    session. Guards the worker-shutdown fix."""
    import time

    measure = "pytest-measure"
    target = "pytest-worker-leak"

    def worker_count():
        return _stdout_json(_exec(
            rrepl_client,
            "import threading, json, gc; gc.collect(); "
            "print(json.dumps({'n': sum(1 for t in threading.enumerate() "
            "if t.name == 'dbg-worker')}))",
            measure,
        ))["n"]

    base = worker_count()

    info = _stdout_json(_exec(rrepl_client, textwrap.dedent("""
        import threading, json
        from upyscripts.rrepl.plugins.dbg.server import Debugger as _D
        DBG = _D()
        sp = DBG.spawn(r"C:\\Windows\\System32\\notepad.exe")
        n = sum(1 for t in threading.enumerate() if t.name == 'dbg-worker')
        print(json.dumps({"pid": sp["pid"], "n": n}))
    """), target))
    pid = info["pid"]
    assert info["n"] >= base + 1          # the new worker is running

    # Drop the only reference to DBG. With the cycle broken + close()/__del__
    # this stops the worker and (spawned) kills the debuggee.
    rrepl_client.reset(target)

    final = base + 1
    for _ in range(12):
        final = worker_count()
        if final <= base:
            break
        time.sleep(0.5)
    assert final <= base, f"dbg-worker thread leaked: base={base} final={final}"

    chk = textwrap.dedent("""
        import subprocess, json
        out = subprocess.run(["tasklist", "/FI", "PID eq %d"],
                             capture_output=True, text=True).stdout
        print(json.dumps({"alive": "%d" in out}))
    """) % (pid, pid)
    alive = _stdout_json(_exec(rrepl_client, chk, measure))["alive"]
    assert alive is False, f"spawned debuggee pid {pid} was not killed on reset"

    rrepl_client.delete_session(target)
    rrepl_client.delete_session(measure)


def test_module_imports_addresses_are_aslr_correct(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    """module_imports() must report runtime IAT addresses, not the file's
    preferred-base VAs. Every IAT slot must lie within the importing
    module's image, and reading a bound slot must resolve into the named
    target module — which only holds when the RVA is re-based onto the
    runtime load address."""
    _bootstrap_dbg(rrepl_client, dbg_session,
                   r"C:\\Windows\\System32\\notepad.exe")

    code = textwrap.dedent("""
        import json
        u = DBG.module_info("user32")
        imps = DBG.module_imports("user32")
        mods = {m["name"].lower(): m for m in DBG.list_modules()}

        within_user32 = True
        resolved = []
        for imp in imps:
            iat = imp["iat_addr"]
            if not iat:
                continue
            if not (u["base"] <= iat < u["base"] + u["size"]):
                within_user32 = False
            tgt = mods.get(imp["module"].lower())
            if tgt and tgt.get("size") and len(resolved) < 10:
                try:
                    ptr = DBG.read_ptr(iat)
                except Exception:
                    continue
                resolved.append(
                    tgt["base"] <= ptr < tgt["base"] + tgt["size"])
        out = {
            "count": len(imps),
            "within_user32": within_user32,
            "resolved_checked": len(resolved),
            "resolved_all_in_target": all(resolved) if resolved else False,
        }
        print(json.dumps(out))
        DBG.kill()
    """)
    out = _stdout_json(_exec(rrepl_client, code, dbg_session))
    assert out["count"] > 0
    assert out["within_user32"] is True
    assert out["resolved_checked"] >= 1
    assert out["resolved_all_in_target"] is True


def _entry_points_probe(rrepl_client, session, target):
    _bootstrap_dbg(rrepl_client, session, target)
    code = textwrap.dedent("""
        import json
        eps = DBG.entry_points()
        exe = next(m for m in DBG.list_modules() if m.get("is_image"))
        entry_eps = [e for e in eps if e["kind"] == "entry"]
        out = {
            "wow64": bool(DBG._impl._wow64),
            "entry_addr": entry_eps[0]["addr"] if entry_eps else None,
            "exe_entry": exe.get("entry"),
            "n_tls": sum(1 for e in eps if e["kind"] == "tls"),
        }
        print(json.dumps(out))
        DBG.kill()
    """)
    return _stdout_json(_exec(rrepl_client, code, session))


def test_entry_points_entry_matches_pe_x64(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    out = _entry_points_probe(rrepl_client, dbg_session,
                              r"C:\\Windows\\System32\\notepad.exe")
    assert out["wow64"] is False
    assert out["entry_addr"] == out["exe_entry"]


def test_entry_points_entry_matches_pe_wow64(
    rrepl_client, rrepl_dbg_available, dbg_session,
):
    # WOW64 path exercises the 4-byte TLS-pointer width fix; the final
    # EntryPoint cross-check guards entry_points() on 32-bit targets.
    out = _entry_points_probe(rrepl_client, dbg_session,
                              r"C:\\Windows\\SysWoW64\\notepad.exe")
    assert out["wow64"] is True
    assert out["entry_addr"] == out["exe_entry"]
