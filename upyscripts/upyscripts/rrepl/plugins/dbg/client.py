"""Local-side wrapper for the rrepl ``dbg`` plugin.

The :class:`Dbg` class mirrors the server-side ``Debugger`` API one-to-one.
Every method renders a parametrised Python snippet, sends it to rrepl on
the configured session, and parses the ``__R__<json>`` line printed back.

Lazy loading: the plugin is imported into the rrepl session on first
call (or first :meth:`ensure_loaded` invocation) — no server endpoints
or background work required.

See ``GUIDE.md`` for the canonical client/agent guide.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .. import PluginBase

_LOAD_KEY = "DBG"
_BOOTSTRAP_SNIPPET = (
    "from upyscripts.rrepl.plugins.dbg.server import Debugger as _Debugger\n"
    f"{_LOAD_KEY} = globals().get({_LOAD_KEY!r}) or _Debugger()\n"
)


def _hexable(v: Any) -> Any:
    """Allow callers to pass ``int``, hex-string, or ``'0x...'`` for addrs."""
    if isinstance(v, str) and v.startswith(("0x", "0X")):
        return int(v, 16)
    return v


class Dbg(PluginBase):
    """rrepl ``dbg`` plugin client. One method per server method.

    Examples
    --------
    >>> d = Dbg("http://winhost:8765", session="dbg")
    >>> sp = d.spawn(r"C:\\Path\\To\\target.exe")
    >>> d.set_bp(sp["first_event"]["image_base"] + entry_rva)
    >>> ev = d.cont(timeout_ms=5000)
    >>> regs = d.get_regs()
    >>> d.kill()
    """

    _LOADED_KEY = _LOAD_KEY
    _BOOTSTRAP = _BOOTSTRAP_SNIPPET

    # ---- internal: hex-string-friendly call ----
    def _call(self, method: str, *args, **kwargs) -> Any:
        args = tuple(_hexable(a) for a in args)
        kwargs = {k: _hexable(v) for k, v in kwargs.items()}
        return super()._call(method, *args, **kwargs)

    # ---- lifecycle ----
    def spawn(self, path: str, args: str = "") -> dict: return self._call("spawn", path, args)
    def attach(self, pid: int) -> dict:                 return self._call("attach", pid)
    def detach(self) -> dict:                            return self._call("detach")
    def kill(self) -> dict:                              return self._call("kill")

    # ---- event pump ----
    def wait(self, timeout_ms: int = 500) -> dict:       return self._call("wait", timeout_ms)
    def continue_event(self, handled: bool = True) -> dict:
        return self._call("continue_event", handled)
    def cont(self, timeout_ms: int = 2000,
             handled: Optional[bool] = None,
             raw: bool = False) -> dict:
        return self._call("cont", timeout_ms, handled, raw)
    def step(self, n: int = 1) -> dict:                  return self._call("step", n)
    def step_over(self) -> dict:                         return self._call("step_over")

    # ---- breakpoints ----
    def set_bp(self, addr_or_symbol, condition: Optional[str] = None,
               action: Optional[str] = None,
               name: Optional[str] = None) -> dict:
        """Set a software BP. The address may be an int, hex string, or
        `module!name` symbol — server resolves against the live export tables.

        Optional server-side scripts:

        condition : Python expression (str). Falsy -> BP silently skipped
                    (transparent to the client). Truthy -> action runs (if
                    any) and the event surfaces.
        action    : Python source (multi-statement OK). Set
                    `result = "resume"` to auto-resume after running (e.g.
                    patch then continue without stopping).
        name      : optional human label (visible in list_bps).

        Script namespace: `dbg`, `regs` (current register snapshot),
        `bp` (the BP entry — `bp["state"]` survives across hits),
        `gstate` (cross-BP scratchpad), `ev` (the debug event dict).
        """
        return self._call("set_bp", addr_or_symbol,
                          condition, action, name)
    def clear_bp(self, addr_or_symbol) -> dict:
        return self._call("clear_bp", addr_or_symbol)
    def list_bps(self) -> list:                          return self._call("list_bps")

    # ---- hardware breakpoints (Dr0..Dr3) ----
    def set_hw_bp(self, addr_or_symbol, type: str = "x", size: int = 1,
                  condition: Optional[str] = None,
                  action: Optional[str] = None,
                  name: Optional[str] = None,
                  slot: Optional[int] = None,
                  threads: Optional[Iterable[int]] = None) -> dict:
        """Set a hardware BP via the CPU debug registers (max 4 slots).

        type   : "x" (execute, size=1), "w" (data write), "rw" (data R/W).
        size   : 1, 2, 4, 8 (8 is x64-only). Must be 1 when type="x".
        slot   : None to auto-allocate, else 0..3.
        threads: list of tids to restrict to; None = process-global
                 (current + future threads, propagated via CREATE_THREAD).
        condition / action / name: same shape and namespace as set_bp.
        """
        return self._call("set_hw_bp", addr_or_symbol, type, size,
                          condition, action, name, slot,
                          list(threads) if threads is not None else None)
    def clear_hw_bp(self, addr_or_slot) -> dict:
        return self._call("clear_hw_bp", addr_or_slot)
    def list_hw_bps(self) -> list:
        return self._call("list_hw_bps")

    # ---- registers ----
    def get_regs(self, tid: Optional[int] = None) -> dict:
        return self._call("get_regs", tid) if tid is not None else self._call("get_regs")
    def set_reg(self, name: str, value, tid: Optional[int] = None) -> dict:
        if tid is None:
            return self._call("set_reg", name, value)
        return self._call("set_reg", name, value, tid)

    # ---- raw memory ----
    def read_mem(self, addr, n: int) -> dict:            return self._call("read_mem", addr, n)
    def write_mem(self, addr, hex_or_bytes, flush: bool = True) -> dict:
        if isinstance(hex_or_bytes, (bytes, bytearray)):
            hex_or_bytes = bytes(hex_or_bytes).hex()
        return self._call("write_mem", addr, hex_or_bytes, flush)

    # ---- typed memory reads (little-endian) ----
    def read_int(self, addr, size: int = 8, signed: bool = False) -> int:
        return self._call("read_int", addr, size, signed)
    def read_u8 (self, addr) -> int: return self._call("read_u8",  addr)
    def read_u16(self, addr) -> int: return self._call("read_u16", addr)
    def read_u32(self, addr) -> int: return self._call("read_u32", addr)
    def read_u64(self, addr) -> int: return self._call("read_u64", addr)
    def read_i8 (self, addr) -> int: return self._call("read_i8",  addr)
    def read_i16(self, addr) -> int: return self._call("read_i16", addr)
    def read_i32(self, addr) -> int: return self._call("read_i32", addr)
    def read_i64(self, addr) -> int: return self._call("read_i64", addr)
    def read_ptr(self, addr) -> int: return self._call("read_ptr", addr)
    def read_f32(self, addr) -> float: return self._call("read_f32", addr)
    def read_f64(self, addr) -> float: return self._call("read_f64", addr)
    def read_cstr(self, addr, max_len: int = 256) -> str:
        return self._call("read_cstr", addr, max_len)
    def read_wstr(self, addr, max_chars: int = 256) -> str:
        return self._call("read_wstr", addr, max_chars)

    # ---- typed memory writes ----
    def write_int(self, addr, value: int, size: int = 8,
                  signed: bool = False) -> dict:
        return self._call("write_int", addr, value, size, signed)
    def write_u8 (self, addr, v) -> dict: return self._call("write_u8",  addr, v)
    def write_u16(self, addr, v) -> dict: return self._call("write_u16", addr, v)
    def write_u32(self, addr, v) -> dict: return self._call("write_u32", addr, v)
    def write_u64(self, addr, v) -> dict: return self._call("write_u64", addr, v)
    def write_i8 (self, addr, v) -> dict: return self._call("write_i8",  addr, v)
    def write_i16(self, addr, v) -> dict: return self._call("write_i16", addr, v)
    def write_i32(self, addr, v) -> dict: return self._call("write_i32", addr, v)
    def write_i64(self, addr, v) -> dict: return self._call("write_i64", addr, v)
    def write_ptr(self, addr, v) -> dict: return self._call("write_ptr", addr, v)
    def write_f32(self, addr, v) -> dict: return self._call("write_f32", addr, v)
    def write_f64(self, addr, v) -> dict: return self._call("write_f64", addr, v)
    def write_cstr(self, addr, s: str, nul: bool = True) -> dict:
        return self._call("write_cstr", addr, s, nul)
    def write_wstr(self, addr, s: str, nul: bool = True) -> dict:
        return self._call("write_wstr", addr, s, nul)

    # ---- asm / disasm ----
    def assemble(self, asm: str, addr=0) -> dict:        return self._call("assemble", asm, addr)
    def write_asm(self, addr, asm: str) -> dict:         return self._call("write_asm", addr, asm)
    def disasm(self, addr=None, count: int = 10) -> list:
        return self._call("disasm", addr, count)

    # ---- entry points ----
    def entry_points(self) -> list:                      return self._call("entry_points")
    def break_on_entry_points(self) -> list:             return self._call("break_on_entry_points")

    # ---- modules / threads ----
    def list_modules(self, with_exports: bool = False,
                     with_imports: bool = False) -> list:
        return self._call("list_modules", with_exports, with_imports)
    def module_info(self, key, with_exports: bool = False,
                    with_imports: bool = False) -> Optional[dict]:
        return self._call("module_info", key, with_exports, with_imports)
    def module_exports(self, key) -> list:
        return self._call("module_exports", key)
    def module_imports(self, key) -> list:
        return self._call("module_imports", key)
    def module_history(self, limit: int = 64) -> list:
        return self._call("module_history", limit)
    def resolve(self, symbol: str, follow_forwarders: bool = True) -> int:
        return self._call("resolve", symbol, follow_forwarders)
    def addr_to_symbol(self, addr) -> Optional[dict]:
        return self._call("addr_to_symbol", addr)
    def list_threads(self, enrich: bool = False,
                     reconcile: bool = False) -> list:
        return self._call("list_threads", enrich, reconcile)
    def thread_info(self, tid: int, enrich: bool = False) -> Optional[dict]:
        return self._call("thread_info", tid, enrich)
    def thread_history(self, limit: int = 64) -> list:
        return self._call("thread_history", limit)
    def suspend_thread(self, tid: int) -> dict:
        return self._call("suspend_thread", tid)
    def resume_thread(self, tid: int) -> dict:
        return self._call("resume_thread", tid)
    def suspend_all(self, exclude: Optional[Iterable[int]] = None) -> list:
        return self._call("suspend_all", list(exclude) if exclude else None)
    def resume_all(self, exclude: Optional[Iterable[int]] = None) -> list:
        return self._call("resume_all", list(exclude) if exclude else None)
    def current_thread(self) -> int:                     return self._call("current_thread")
    def event_info(self) -> Optional[dict]:              return self._call("event_info")

    # ---- guide ----
    @property
    def guide_path(self) -> str:
        from . import GUIDE_PATH
        return str(GUIDE_PATH)

    def guide(self) -> str:
        """Return the canonical client/agent guide as a string. Degrades
        gracefully to a short notice if the markdown wasn't packaged."""
        from . import GUIDE_PATH
        try:
            return GUIDE_PATH.read_text(encoding="utf-8")
        except OSError:
            return (
                "upy.rrepl-dbg guide unavailable: {} is not present in this "
                "install. See the GUIDE.md in the source tree or "
                "upyscripts/upyscripts/rrepl/plugins/dbg/GUIDE.md on GitHub."
            ).format(GUIDE_PATH)


# ----------------- pretty printers ----------------- #

def fmt_regs(r: dict) -> str:
    order = ("Rip","Rax","Rbx","Rcx","Rdx","Rsi","Rdi","Rsp","Rbp",
             "R8","R9","R10","R11","R12","R13","R14","R15","EFlags")
    return "\n".join(
        f"{n:>6} = {r[n]:#018x}" for n in order if n in r
    )


def fmt_disasm(rows: Iterable[dict]) -> str:
    return "\n".join(
        f"{ins['addr']:#018x}  {ins['bytes']:<22}  "
        f"{ins['mnemonic']} {ins['op_str']}"
        for ins in rows
    )


def fmt_modules(mods: Iterable[dict]) -> str:
    return "\n".join(
        f"{m['base']:#018x}  {m['name']:<32}  {m['path']}"
        for m in mods
    )
