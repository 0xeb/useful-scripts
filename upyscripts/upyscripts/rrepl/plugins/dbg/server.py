"""Server-side x64 user-mode debugger for the upy.rrepl ``dbg`` plugin.

This module is imported INSIDE an rrepl session on a Windows host (by
the lazy bootstrap that ``upyscripts.rrepl.plugins.dbg.client.Dbg`` sends
on first use). It is Windows-only: ctypes wrappers around the Win32
Debug API plus a Debugger class providing spawn/attach,
run/cont/step/step_over, software breakpoints, register R/W (incl. RIP),
memory R/W (with FlushInstructionCache for code patches), typed memory
helpers, module/thread enumeration, capstone-backed disassembly,
keystone-backed assemble + write_asm, and a TLS-callback + EntryPoint
walker (`entry_points`).

Every method that resumes the debuggee uses a bounded
WaitForDebugEvent timeout so the wrapping HTTP request stays
responsive. Long waits are the client's responsibility (loop on
`wait`/`cont`).
"""

from __future__ import annotations

import sys

if sys.platform != "win32":
    raise ImportError(
        "upyscripts.rrepl.plugins.dbg.server is Windows-only "
        "(uses Win32 Debug API via ctypes); current platform: " + sys.platform
    )

import ctypes
import ctypes.wintypes as wt
import os
import queue
import struct
import threading
from collections import deque
from ctypes import (
    POINTER,
    Structure,
    Union,
    byref,
    c_byte,
    c_int64,
    c_long,
    c_size_t,
    c_ubyte,
    c_uint16,
    c_uint32,
    c_uint64,
    c_void_p,
    c_wchar,
    c_wchar_p,
    sizeof,
    windll,
)

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

DEBUG_PROCESS = 0x00000001
DEBUG_ONLY_THIS_PROCESS = 0x00000002
CREATE_NEW_CONSOLE = 0x00000010
CREATE_SUSPENDED = 0x00000004
INFINITE = 0xFFFFFFFF

DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001

EXCEPTION_DEBUG_EVENT = 1
CREATE_THREAD_DEBUG_EVENT = 2
CREATE_PROCESS_DEBUG_EVENT = 3
EXIT_THREAD_DEBUG_EVENT = 4
EXIT_PROCESS_DEBUG_EVENT = 5
LOAD_DLL_DEBUG_EVENT = 6
UNLOAD_DLL_DEBUG_EVENT = 7
OUTPUT_DEBUG_STRING_EVENT = 8
RIP_EVENT = 9

EVENT_NAMES = {
    1: "EXCEPTION",
    2: "CREATE_THREAD",
    3: "CREATE_PROCESS",
    4: "EXIT_THREAD",
    5: "EXIT_PROCESS",
    6: "LOAD_DLL",
    7: "UNLOAD_DLL",
    8: "OUTPUT_DEBUG_STRING",
    9: "RIP",
}

EXCEPTION_BREAKPOINT = 0x80000003
EXCEPTION_SINGLE_STEP = 0x80000004
EXCEPTION_ACCESS_VIOLATION = 0xC0000005
EXCEPTION_ILLEGAL_INSTR = 0xC000001D
STATUS_WX86_BREAKPOINT = 0x4000001F
STATUS_WX86_SINGLE_STEP = 0x4000001E

EXCEPTION_NAMES = {
    0x80000003: "BREAKPOINT",
    0x80000004: "SINGLE_STEP",
    0xC0000005: "ACCESS_VIOLATION",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC0000096: "PRIV_INSTRUCTION",
    0xC00000FD: "STACK_OVERFLOW",
    0x4000001F: "WX86_BREAKPOINT",
    0x4000001E: "WX86_SINGLE_STEP",
}

# CONTEXT flags (AMD64)
CONTEXT_AMD64 = 0x00100000
CONTEXT_CONTROL = CONTEXT_AMD64 | 0x1
CONTEXT_INTEGER = CONTEXT_AMD64 | 0x2
CONTEXT_SEGMENTS = CONTEXT_AMD64 | 0x4
CONTEXT_FLOATING_POINT = CONTEXT_AMD64 | 0x8
CONTEXT_DEBUG_REGISTERS = CONTEXT_AMD64 | 0x10
CONTEXT_FULL = CONTEXT_CONTROL | CONTEXT_INTEGER | CONTEXT_SEGMENTS
CONTEXT_ALL = CONTEXT_FULL | CONTEXT_FLOATING_POINT | CONTEXT_DEBUG_REGISTERS

# Process / thread access
PROCESS_ALL_ACCESS = 0x1FFFFF
THREAD_ALL_ACCESS = 0x1FFFFF

# EFLAGS
EFLAGS_TF = 0x100
EFLAGS_RF = 0x10000  # resume flag — suppress an instruction
# (execute) breakpoint for one insn

# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

LPVOID = c_void_p
HANDLE = wt.HANDLE
DWORD = wt.DWORD
WORD = wt.WORD
BYTE = wt.BYTE
ULONG = wt.ULONG
ULONG64 = c_uint64


class M128A(Structure):
    _fields_ = [("Low", c_uint64), ("High", c_int64)]


class XMM_SAVE_AREA32(Structure):
    _fields_ = [
        ("ControlWord", c_uint16),
        ("StatusWord", c_uint16),
        ("TagWord", c_ubyte),
        ("Reserved1", c_ubyte),
        ("ErrorOpcode", c_uint16),
        ("ErrorOffset", c_uint32),
        ("ErrorSelector", c_uint16),
        ("Reserved2", c_uint16),
        ("DataOffset", c_uint32),
        ("DataSelector", c_uint16),
        ("Reserved3", c_uint16),
        ("MxCsr", c_uint32),
        ("MxCsr_Mask", c_uint32),
        ("FloatRegisters", M128A * 8),
        ("XmmRegisters", M128A * 16),
        ("Reserved4", c_ubyte * 96),
    ]


class CONTEXT(Structure):
    _pack_ = 16
    _fields_ = [
        ("P1Home", c_uint64),
        ("P2Home", c_uint64),
        ("P3Home", c_uint64),
        ("P4Home", c_uint64),
        ("P5Home", c_uint64),
        ("P6Home", c_uint64),
        ("ContextFlags", c_uint32),
        ("MxCsr", c_uint32),
        ("SegCs", c_uint16),
        ("SegDs", c_uint16),
        ("SegEs", c_uint16),
        ("SegFs", c_uint16),
        ("SegGs", c_uint16),
        ("SegSs", c_uint16),
        ("EFlags", c_uint32),
        ("Dr0", c_uint64),
        ("Dr1", c_uint64),
        ("Dr2", c_uint64),
        ("Dr3", c_uint64),
        ("Dr6", c_uint64),
        ("Dr7", c_uint64),
        ("Rax", c_uint64),
        ("Rcx", c_uint64),
        ("Rdx", c_uint64),
        ("Rbx", c_uint64),
        ("Rsp", c_uint64),
        ("Rbp", c_uint64),
        ("Rsi", c_uint64),
        ("Rdi", c_uint64),
        ("R8", c_uint64),
        ("R9", c_uint64),
        ("R10", c_uint64),
        ("R11", c_uint64),
        ("R12", c_uint64),
        ("R13", c_uint64),
        ("R14", c_uint64),
        ("R15", c_uint64),
        ("Rip", c_uint64),
        ("FltSave", XMM_SAVE_AREA32),
        ("VectorRegister", M128A * 26),
        ("VectorControl", c_uint64),
        ("DebugControl", c_uint64),
        ("LastBranchToRip", c_uint64),
        ("LastBranchFromRip", c_uint64),
        ("LastExceptionToRip", c_uint64),
        ("LastExceptionFromRip", c_uint64),
    ]


INTEGER_REGS = (
    "Rax",
    "Rcx",
    "Rdx",
    "Rbx",
    "Rsp",
    "Rbp",
    "Rsi",
    "Rdi",
    "R8",
    "R9",
    "R10",
    "R11",
    "R12",
    "R13",
    "R14",
    "R15",
    "Rip",
)
SEG_REGS = ("SegCs", "SegDs", "SegEs", "SegFs", "SegGs", "SegSs")

# ---------------------------------------------------------------------------
# WOW64 (32-bit guest under 64-bit host) structures and constants
# ---------------------------------------------------------------------------

WOW64_CONTEXT_i386 = 0x00010000
WOW64_CONTEXT_CONTROL = WOW64_CONTEXT_i386 | 0x1
WOW64_CONTEXT_INTEGER = WOW64_CONTEXT_i386 | 0x2
WOW64_CONTEXT_SEGMENTS = WOW64_CONTEXT_i386 | 0x4
WOW64_CONTEXT_FLOATING_POINT = WOW64_CONTEXT_i386 | 0x8
WOW64_CONTEXT_DEBUG_REGISTERS = WOW64_CONTEXT_i386 | 0x10
WOW64_CONTEXT_FULL = (
    WOW64_CONTEXT_CONTROL | WOW64_CONTEXT_INTEGER | WOW64_CONTEXT_SEGMENTS
)
WOW64_CONTEXT_ALL = (
    WOW64_CONTEXT_FULL | WOW64_CONTEXT_FLOATING_POINT | WOW64_CONTEXT_DEBUG_REGISTERS
)

WOW64_SIZE_OF_80387_REGISTERS = 80
WOW64_MAXIMUM_SUPPORTED_EXTENSION = 512


class WOW64_FLOATING_SAVE_AREA(Structure):
    _fields_ = [
        ("ControlWord", c_uint32),
        ("StatusWord", c_uint32),
        ("TagWord", c_uint32),
        ("ErrorOffset", c_uint32),
        ("ErrorSelector", c_uint32),
        ("DataOffset", c_uint32),
        ("DataSelector", c_uint32),
        ("RegisterArea", c_ubyte * WOW64_SIZE_OF_80387_REGISTERS),
        ("Spare0", c_uint32),
    ]


class WOW64_CONTEXT(Structure):
    _fields_ = [
        ("ContextFlags", c_uint32),
        ("Dr0", c_uint32),
        ("Dr1", c_uint32),
        ("Dr2", c_uint32),
        ("Dr3", c_uint32),
        ("Dr6", c_uint32),
        ("Dr7", c_uint32),
        ("FloatSave", WOW64_FLOATING_SAVE_AREA),
        ("SegGs", c_uint32),
        ("SegFs", c_uint32),
        ("SegEs", c_uint32),
        ("SegDs", c_uint32),
        ("Edi", c_uint32),
        ("Esi", c_uint32),
        ("Ebx", c_uint32),
        ("Edx", c_uint32),
        ("Ecx", c_uint32),
        ("Eax", c_uint32),
        ("Ebp", c_uint32),
        ("Eip", c_uint32),
        ("SegCs", c_uint32),
        ("EFlags", c_uint32),
        ("Esp", c_uint32),
        ("SegSs", c_uint32),
        ("ExtendedRegisters", c_ubyte * WOW64_MAXIMUM_SUPPORTED_EXTENSION),
    ]


WOW64_INTEGER_REGS = ("Eax", "Ecx", "Edx", "Ebx", "Esp", "Ebp", "Esi", "Edi", "Eip")

# ---------------------------------------------------------------------------
# Hardware breakpoint encoding (Dr0..Dr7)
# ---------------------------------------------------------------------------

# Dr7 control bits
DR7_LE = 0x100  # local exact (must be 1 for accurate trapping)
DR7_GE = 0x200  # global exact
DR7_RESERVED_MUST_BE_1 = 0x400  # bit 10 — Intel says always 1

# Dr6 status bits (sticky; must be cleared by debugger after a hit)
DR6_B0 = 0x1
DR6_B1 = 0x2
DR6_B2 = 0x4
DR6_B3 = 0x8
DR6_BS = 0x4000  # single-step (TF)

# Per-slot Dr7 layout: enable bit at (slot*2), RW field at (16 + slot*4),
# LEN field at (18 + slot*4).
HW_BP_RW_BITS = {"x": 0b00, "w": 0b01, "io": 0b10, "rw": 0b11}
HW_BP_LEN_BITS = {1: 0b00, 2: 0b01, 4: 0b11, 8: 0b10}  # 8 → x64 only


class EXCEPTION_RECORD(Structure):
    pass


EXCEPTION_RECORD._fields_ = [
    ("ExceptionCode", c_uint32),
    ("ExceptionFlags", c_uint32),
    ("ExceptionRecord", POINTER(EXCEPTION_RECORD)),
    ("ExceptionAddress", c_void_p),
    ("NumberParameters", c_uint32),
    ("ExceptionInformation", c_uint64 * 15),
]


class EXCEPTION_DEBUG_INFO(Structure):
    _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", c_uint32)]


class CREATE_THREAD_DEBUG_INFO(Structure):
    _fields_ = [
        ("hThread", HANDLE),
        ("lpThreadLocalBase", c_void_p),
        ("lpStartAddress", c_void_p),
    ]


class CREATE_PROCESS_DEBUG_INFO(Structure):
    _fields_ = [
        ("hFile", HANDLE),
        ("hProcess", HANDLE),
        ("hThread", HANDLE),
        ("lpBaseOfImage", c_void_p),
        ("dwDebugInfoFileOffset", c_uint32),
        ("nDebugInfoSize", c_uint32),
        ("lpThreadLocalBase", c_void_p),
        ("lpStartAddress", c_void_p),
        ("lpImageName", c_void_p),
        ("fUnicode", c_uint16),
    ]


class EXIT_THREAD_DEBUG_INFO(Structure):
    _fields_ = [("dwExitCode", c_uint32)]


class EXIT_PROCESS_DEBUG_INFO(Structure):
    _fields_ = [("dwExitCode", c_uint32)]


class LOAD_DLL_DEBUG_INFO(Structure):
    _fields_ = [
        ("hFile", HANDLE),
        ("lpBaseOfDll", c_void_p),
        ("dwDebugInfoFileOffset", c_uint32),
        ("nDebugInfoSize", c_uint32),
        ("lpImageName", c_void_p),
        ("fUnicode", c_uint16),
    ]


class UNLOAD_DLL_DEBUG_INFO(Structure):
    _fields_ = [("lpBaseOfDll", c_void_p)]


class OUTPUT_DEBUG_STRING_INFO(Structure):
    _fields_ = [
        ("lpDebugStringData", c_void_p),
        ("fUnicode", c_uint16),
        ("nDebugStringLength", c_uint16),
    ]


class RIP_INFO(Structure):
    _fields_ = [("dwError", c_uint32), ("dwType", c_uint32)]


class _DEBUG_EVENT_U(Union):
    _fields_ = [
        ("Exception", EXCEPTION_DEBUG_INFO),
        ("CreateThread", CREATE_THREAD_DEBUG_INFO),
        ("CreateProcessInfo", CREATE_PROCESS_DEBUG_INFO),
        ("ExitThread", EXIT_THREAD_DEBUG_INFO),
        ("ExitProcess", EXIT_PROCESS_DEBUG_INFO),
        ("LoadDll", LOAD_DLL_DEBUG_INFO),
        ("UnloadDll", UNLOAD_DLL_DEBUG_INFO),
        ("DebugString", OUTPUT_DEBUG_STRING_INFO),
        ("RipInfo", RIP_INFO),
    ]


class DEBUG_EVENT(Structure):
    _fields_ = [
        ("dwDebugEventCode", c_uint32),
        ("dwProcessId", c_uint32),
        ("dwThreadId", c_uint32),
        ("u", _DEBUG_EVENT_U),
    ]


class STARTUPINFOW(Structure):
    _fields_ = [
        ("cb", c_uint32),
        ("lpReserved", c_wchar_p),
        ("lpDesktop", c_wchar_p),
        ("lpTitle", c_wchar_p),
        ("dwX", c_uint32),
        ("dwY", c_uint32),
        ("dwXSize", c_uint32),
        ("dwYSize", c_uint32),
        ("dwXCountChars", c_uint32),
        ("dwYCountChars", c_uint32),
        ("dwFillAttribute", c_uint32),
        ("dwFlags", c_uint32),
        ("wShowWindow", c_uint16),
        ("cbReserved2", c_uint16),
        ("lpReserved2", c_void_p),
        ("hStdInput", HANDLE),
        ("hStdOutput", HANDLE),
        ("hStdError", HANDLE),
    ]


class PROCESS_INFORMATION(Structure):
    _fields_ = [
        ("hProcess", HANDLE),
        ("hThread", HANDLE),
        ("dwProcessId", c_uint32),
        ("dwThreadId", c_uint32),
    ]


# ---------------------------------------------------------------------------
# Win32 bindings
# ---------------------------------------------------------------------------

k32 = windll.kernel32
psapi = windll.psapi

k32.CreateProcessW.argtypes = [
    c_wchar_p,
    c_wchar_p,
    c_void_p,
    c_void_p,
    wt.BOOL,
    c_uint32,
    c_void_p,
    c_wchar_p,
    POINTER(STARTUPINFOW),
    POINTER(PROCESS_INFORMATION),
]
k32.CreateProcessW.restype = wt.BOOL

k32.WaitForDebugEvent.argtypes = [POINTER(DEBUG_EVENT), c_uint32]
k32.WaitForDebugEvent.restype = wt.BOOL
k32.ContinueDebugEvent.argtypes = [c_uint32, c_uint32, c_uint32]
k32.ContinueDebugEvent.restype = wt.BOOL
k32.DebugActiveProcess.argtypes = [c_uint32]
k32.DebugActiveProcess.restype = wt.BOOL
k32.DebugActiveProcessStop.argtypes = [c_uint32]
k32.DebugActiveProcessStop.restype = wt.BOOL
k32.DebugSetProcessKillOnExit.argtypes = [wt.BOOL]
k32.DebugSetProcessKillOnExit.restype = wt.BOOL

k32.OpenProcess.argtypes = [c_uint32, wt.BOOL, c_uint32]
k32.OpenProcess.restype = HANDLE
k32.OpenThread.argtypes = [c_uint32, wt.BOOL, c_uint32]
k32.OpenThread.restype = HANDLE

k32.GetThreadContext.argtypes = [HANDLE, POINTER(CONTEXT)]
k32.GetThreadContext.restype = wt.BOOL
k32.SetThreadContext.argtypes = [HANDLE, POINTER(CONTEXT)]
k32.SetThreadContext.restype = wt.BOOL
k32.SuspendThread.argtypes = [HANDLE]
k32.SuspendThread.restype = c_uint32
k32.ResumeThread.argtypes = [HANDLE]
k32.ResumeThread.restype = c_uint32

# WOW64 thread context (32-bit guest under 64-bit host).
# Wow64GetThreadContext / Wow64SetThreadContext are kernel32 exports on
# 64-bit Windows; on a pure 32-bit host they don't exist.
try:
    k32.Wow64GetThreadContext.argtypes = [HANDLE, POINTER(WOW64_CONTEXT)]
    k32.Wow64GetThreadContext.restype = wt.BOOL
    k32.Wow64SetThreadContext.argtypes = [HANDLE, POINTER(WOW64_CONTEXT)]
    k32.Wow64SetThreadContext.restype = wt.BOOL
    _HAS_WOW64_CONTEXT = True
except AttributeError:
    _HAS_WOW64_CONTEXT = False

# IsWow64Process: a 64-bit Windows API. Tells us whether a process is a
# 32-bit (WOW64) guest. Always False for native x64 processes.
try:
    k32.IsWow64Process.argtypes = [HANDLE, POINTER(wt.BOOL)]
    k32.IsWow64Process.restype = wt.BOOL
    _HAS_ISWOW64 = True
except AttributeError:
    _HAS_ISWOW64 = False

k32.ReadProcessMemory.argtypes = [
    HANDLE,
    c_void_p,
    c_void_p,
    c_size_t,
    POINTER(c_size_t),
]
k32.ReadProcessMemory.restype = wt.BOOL
k32.WriteProcessMemory.argtypes = [
    HANDLE,
    c_void_p,
    c_void_p,
    c_size_t,
    POINTER(c_size_t),
]
k32.WriteProcessMemory.restype = wt.BOOL
k32.FlushInstructionCache.argtypes = [HANDLE, c_void_p, c_size_t]
k32.FlushInstructionCache.restype = wt.BOOL

k32.TerminateProcess.argtypes = [HANDLE, c_uint32]
k32.TerminateProcess.restype = wt.BOOL
k32.CloseHandle.argtypes = [HANDLE]
k32.CloseHandle.restype = wt.BOOL
k32.GetLastError.restype = c_uint32

# psapi
psapi.GetMappedFileNameW.argtypes = [HANDLE, c_void_p, c_wchar_p, c_uint32]
psapi.GetMappedFileNameW.restype = c_uint32
psapi.GetModuleFileNameExW.argtypes = [HANDLE, HANDLE, c_wchar_p, c_uint32]
psapi.GetModuleFileNameExW.restype = c_uint32

# Toolhelp32 (for thread enumeration)
TH32CS_SNAPTHREAD = 0x00000004


class THREADENTRY32(Structure):
    _fields_ = [
        ("dwSize", c_uint32),
        ("cntUsage", c_uint32),
        ("th32ThreadID", c_uint32),
        ("th32OwnerProcessID", c_uint32),
        ("tpBasePri", c_long),
        ("tpDeltaPri", c_long),
        ("dwFlags", c_uint32),
    ]


k32.QueryDosDeviceW.argtypes = [c_wchar_p, c_wchar_p, c_uint32]
k32.QueryDosDeviceW.restype = c_uint32

k32.CreateToolhelp32Snapshot.argtypes = [c_uint32, c_uint32]
k32.CreateToolhelp32Snapshot.restype = HANDLE
k32.Thread32First.argtypes = [HANDLE, POINTER(THREADENTRY32)]
k32.Thread32First.restype = wt.BOOL
k32.Thread32Next.argtypes = [HANDLE, POINTER(THREADENTRY32)]
k32.Thread32Next.restype = wt.BOOL


def _winerror(api: str) -> OSError:
    code = k32.GetLastError()
    return OSError(code, f"{api} failed (GetLastError={code})")


# ---------------------------------------------------------------------------
# Aligned CONTEXT helper
# ---------------------------------------------------------------------------


def _alloc_context(flags: int = CONTEXT_ALL):
    """Allocate a 16-byte-aligned CONTEXT. Keeps backing buffer alive."""
    raw = (c_byte * (sizeof(CONTEXT) + 16))()
    addr = ctypes.addressof(raw)
    aligned = (addr + 15) & ~15
    ctx = CONTEXT.from_address(aligned)
    # Zero and set flags.
    ctypes.memset(aligned, 0, sizeof(CONTEXT))
    ctx.ContextFlags = flags
    return raw, ctx


def _alloc_wow64_context(flags: int = WOW64_CONTEXT_ALL):
    """Allocate a WOW64_CONTEXT. No alignment requirement (32-bit struct)."""
    ctx = WOW64_CONTEXT()
    ctypes.memset(ctypes.addressof(ctx), 0, sizeof(WOW64_CONTEXT))
    ctx.ContextFlags = flags
    return ctx, ctx  # raw, ctx — keep symmetric with _alloc_context


# ---------------------------------------------------------------------------
# Disassembler (lazy)
# ---------------------------------------------------------------------------

_cs_cache: dict[bool, object] = {}


def _md(wow64: bool = False):
    """Cached capstone disassembler. wow64=True uses 32-bit mode."""
    if wow64 in _cs_cache:
        return _cs_cache[wow64]
    import capstone

    mode = capstone.CS_MODE_32 if wow64 else capstone.CS_MODE_64
    cs = capstone.Cs(capstone.CS_ARCH_X86, mode)
    cs.detail = True
    _cs_cache[wow64] = cs
    return cs


_ks_cache: dict[bool, object] = {}


def _ks_engine(wow64: bool = False):
    """Cached keystone assembler. wow64=True uses 32-bit mode."""
    if wow64 in _ks_cache:
        return _ks_cache[wow64]
    import keystone

    mode = keystone.KS_MODE_32 if wow64 else keystone.KS_MODE_64
    ks = keystone.Ks(keystone.KS_ARCH_X86, mode)
    _ks_cache[wow64] = ks
    return ks


# ---------------------------------------------------------------------------
# Build / version info
# ---------------------------------------------------------------------------

_BUILD_INFO_CACHE: dict | None = None


def _plugin_build_info() -> dict:
    """Return ``{plugin, build, git_head, package_version}``. Cached after
    the first call so we don't shell out to git on every version() call."""
    global _BUILD_INFO_CACHE
    if _BUILD_INFO_CACHE is not None:
        return dict(_BUILD_INFO_CACHE)

    git_head = None
    package_version = None

    # Try git rev-parse against the package's source tree.
    try:
        import subprocess

        here = os.path.dirname(os.path.abspath(__file__))
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=here,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        if sha:
            git_head = sha
            try:
                dirty = subprocess.check_output(
                    ["git", "status", "--porcelain"],
                    cwd=here,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                ).strip()
                if dirty:
                    git_head += "-dirty"
            except Exception:
                pass
    except Exception:
        pass

    # importlib.metadata is the cross-Python-version PEP 566 reader.
    try:
        from importlib.metadata import version as _pkg_version

        package_version = _pkg_version("upyscripts")
    except Exception:
        pass

    build = git_head or package_version or "unknown"
    _BUILD_INFO_CACHE = {
        "plugin": "upy.rrepl-dbg",
        "build": build,
        "git_head": git_head,
        "package_version": package_version,
    }
    return dict(_BUILD_INFO_CACHE)


# ---------------------------------------------------------------------------
# Debugger
# ---------------------------------------------------------------------------


class _DbgImpl:
    """Actual debugger logic. Must run entirely on a single OS thread because
    Win32 Debug API ties WaitForDebugEvent/ContinueDebugEvent to the thread
    that created the debuggee. The public `Debugger` class pins this."""

    _EXITED_HISTORY_MAX = 256
    _MODULE_HISTORY_MAX = 64

    def __init__(self):
        self.pid: int = 0
        self.h_process: int = 0
        self.attached: bool = False
        self.spawned: bool = False
        # Live module table, populated from CREATE_PROCESS / LOAD_DLL events
        # and removed on UNLOAD_DLL. Each entry (after _parse_pe_headers):
        #   {base, name, path, size, entry_rva, entry, machine, timestamp,
        #    is_image, loaded_at, loaded_seq, pe_error?,
        #    exports?, exports_error?,         # lazy
        #    imports?, imports_error?}         # lazy
        self._modules: dict[int, dict] = {}
        # Bounded history of unloaded modules. Each entry:
        #   {base, name, path, size, entry, loaded_at, loaded_seq,
        #    unloaded_at, unloaded_seq, lifetime_ms}
        self._unloaded_modules: deque = deque(maxlen=self._MODULE_HISTORY_MAX)
        # Live thread table, populated from CREATE_PROCESS / CREATE_THREAD
        # debug events (and lazily from OpenThread for any tid the user names
        # before we've seen its event). Each entry:
        #   {tid, handle, start_address, is_main, created_at, created_seq,
        #    discovered}
        self._threads: dict[int, dict] = {}
        # Bounded history of exited threads (oldest dropped). Each entry:
        #   {tid, start_address, is_main, exit_code, created_at, exited_at,
        #    lifetime_ms, created_seq, exited_seq}
        self._exited_threads: deque = deque(maxlen=self._EXITED_HISTORY_MAX)
        self._event_seq: int = 0
        # Live breakpoint table. Each entry:
        #   {addr, orig, name?, condition?, condition_compiled?,
        #    action?, action_compiled?, condition_error?, action_error?,
        #    hits, skipped, state, last_decision?}
        # state is a per-BP dict the user can read/write from the
        # condition/action scripts. It outlives individual hits but is
        # cleared when the BP is removed.
        self._bps: dict[int, dict] = {}
        # Hardware breakpoints — at most 4 slots (Dr0..Dr3). Keyed by slot.
        # Each entry:
        #   {slot, addr, type ("x"|"w"|"rw"|"io"), size,
        #    name?, condition?, condition_compiled?,
        #    action?, action_compiled?,
        #    condition_error?, action_error?,
        #    hits, skipped, state, threads (None = process-global), symbol?}
        self._hw_bps: dict[int, dict] = {}
        # Cross-BP scratchpad available to scripts as `gstate`.
        self._bp_gstate: dict = {}
        self._pending_reArm: int = 0  # addr to re-arm after step
        self._loader_bp_seen: bool = False
        self._last_event: dict | None = None
        self._cur_tid: int = 0
        self._cur_event_code: int = 0
        self._exit_code: int | None = None
        # True if the debuggee is a 32-bit (WOW64) process running under
        # 64-bit Windows. Set after the first CREATE_PROCESS event of
        # spawn()/attach() once we have a process handle.
        self._wow64: bool = False

    # ---------------- lifecycle ----------------
    def spawn(self, path: str, args: str = "") -> dict:
        if self.attached or self.spawned:
            raise RuntimeError(
                "already attached/spawned; call kill() or detach() first"
            )
        si = STARTUPINFOW()
        si.cb = sizeof(STARTUPINFOW)
        pi = PROCESS_INFORMATION()
        cmdline = f'"{path}"' + (f" {args}" if args else "")
        flags = DEBUG_PROCESS | DEBUG_ONLY_THIS_PROCESS | CREATE_NEW_CONSOLE
        ok = k32.CreateProcessW(
            path,
            ctypes.c_wchar_p(cmdline),
            None,
            None,
            False,
            flags,
            None,
            None,
            byref(si),
            byref(pi),
        )
        if not ok:
            raise _winerror("CreateProcessW")
        self.pid = pi.dwProcessId
        self.h_process = pi.hProcess
        self.spawned = True
        k32.DebugSetProcessKillOnExit(True)
        # Wait for initial CREATE_PROCESS to populate module table & main thread.
        first = self.wait(timeout_ms=5000)
        self._detect_wow64()
        return {
            "pid": self.pid,
            "tid": pi.dwThreadId,
            "image_base": first.get("image_base"),
            "wow64": self._wow64,
            "first_event": first,
        }

    def attach(self, pid: int) -> dict:
        if self.attached or self.spawned:
            raise RuntimeError("already attached")
        if not k32.DebugActiveProcess(int(pid)):
            raise _winerror("DebugActiveProcess")
        self.pid = int(pid)
        self.attached = True
        k32.DebugSetProcessKillOnExit(False)
        first = self.wait(timeout_ms=5000)
        # Open process handle if not provided by CREATE_PROCESS event.
        if not self.h_process:
            self.h_process = k32.OpenProcess(PROCESS_ALL_ACCESS, False, self.pid)
            if not self.h_process:
                raise _winerror("OpenProcess")
        self._detect_wow64()
        # Windows does not always synthesize CREATE_THREAD events for threads
        # that existed before DebugActiveProcess; reconcile from a Toolhelp32
        # snapshot so the live thread table reflects reality from the start.
        added = self._reconcile_threads()
        return {
            "pid": self.pid,
            "wow64": self._wow64,
            "reconciled_threads": added,
            "first_event": first,
        }

    def _reconcile_threads(self) -> int:
        """Walk a Toolhelp32 thread snapshot and bring any tids belonging to
        self.pid that aren't tracked into the table (handle opened lazily,
        marked discovered=True). Returns the number of new entries added.

        Used internally by attach() (Windows does not always synthesize
        CREATE_THREAD events for threads that existed before we attached)
        and exposed via list_threads(reconcile=True)."""
        if not self.pid:
            return 0
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if not snap or snap == HANDLE(-1).value:
            return 0
        added = 0
        try:
            te = THREADENTRY32()
            te.dwSize = sizeof(THREADENTRY32)
            ok = k32.Thread32First(snap, byref(te))
            while ok:
                if (
                    te.th32OwnerProcessID == self.pid
                    and te.th32ThreadID not in self._threads
                ):
                    try:
                        self._open_thread(te.th32ThreadID)
                        added += 1
                    except OSError:
                        pass
                ok = k32.Thread32Next(snap, byref(te))
        finally:
            k32.CloseHandle(snap)
        return added

    def _detect_wow64(self):
        """Set self._wow64 from IsWow64Process(self.h_process). Returns the
        flag. False on pure 32-bit hosts or when the API is missing."""
        self._wow64 = False
        if not _HAS_ISWOW64 or not self.h_process:
            return self._wow64
        flag = wt.BOOL(0)
        if k32.IsWow64Process(self.h_process, byref(flag)):
            self._wow64 = bool(flag.value)
        return self._wow64

    def detach(self) -> dict:
        if not (self.attached or self.spawned):
            return {"detached": False}
        # restore all software BPs first
        for addr in list(self._bps.keys()):
            try:
                self.clear_bp(addr)
            except Exception:
                pass
        # clear hardware BPs from every tracked thread so the detached
        # debuggee runs without surprise faults from leftover Dr0..Dr7.
        if self._hw_bps or self._threads:
            self._hw_bps.clear()
            for tid in list(self._threads):
                try:
                    self._apply_hw_bps_to_thread(tid)
                except Exception:
                    pass
        ok = k32.DebugActiveProcessStop(self.pid)
        self._cleanup_handles()
        return {"detached": bool(ok)}

    def kill(self) -> dict:
        if self.h_process:
            k32.TerminateProcess(self.h_process, 1)
        # Drain final exit event so the OS releases everything cleanly.
        for _ in range(20):
            ev = self.wait(timeout_ms=200)
            if ev.get("event") == "EXIT_PROCESS":
                break
        self._cleanup_handles()
        return {"killed": True, "exit_code": self._exit_code}

    def _cleanup_handles(self):
        for entry in self._threads.values():
            h = entry.get("handle")
            if h:
                try:
                    k32.CloseHandle(h)
                except Exception:
                    pass
        self._threads.clear()
        if self.h_process:
            try:
                k32.CloseHandle(self.h_process)
            except Exception:
                pass
        self.h_process = 0
        self.pid = 0
        self.attached = self.spawned = False
        self._modules.clear()
        self._bps.clear()
        self._hw_bps.clear()
        self._loader_bp_seen = False
        # Keep _exited_threads: history outlives the debuggee so callers can
        # inspect post-mortem after kill().

    # ---------------- event pump ----------------
    def wait(self, timeout_ms: int = 500) -> dict:
        """Pump exactly one debug event (or timeout). DOES NOT auto-continue.

        Maintains module/thread tables and last-event state. Returns a
        JSON-friendly dict. Caller must invoke `cont()`/`step()` to resume.
        """
        ev = DEBUG_EVENT()
        if not k32.WaitForDebugEvent(byref(ev), int(timeout_ms)):
            return {"event": "timeout", "running": True}
        code = ev.dwDebugEventCode
        tid = ev.dwThreadId
        self._cur_tid = tid
        self._cur_event_code = code
        self._event_seq += 1
        seq = self._event_seq
        info: dict = {
            "event": EVENT_NAMES.get(code, str(code)),
            "pid": ev.dwProcessId,
            "tid": tid,
            "seq": seq,
        }

        if code == CREATE_PROCESS_DEBUG_EVENT:
            cp = ev.u.CreateProcessInfo
            self.h_process = cp.hProcess
            start_addr = cp.lpStartAddress or 0
            self._threads[tid] = {
                "tid": tid,
                "handle": cp.hThread,
                "start_address": start_addr,
                "is_main": True,
                "created_at": _now_ms(),
                "created_seq": seq,
                "discovered": False,
            }
            base = cp.lpBaseOfImage or 0
            path = self._image_path(cp.hFile, base) or ""
            self._add_module(base, path, seq, is_image=True)
            if cp.hFile:
                k32.CloseHandle(cp.hFile)
            m = self._modules.get(base, {})
            info.update(
                {
                    "image_base": base,
                    "image_path": path,
                    "entry": start_addr,
                    "image_size": m.get("size"),
                    "image_entry": m.get("entry"),
                }
            )

        elif code == CREATE_THREAD_DEBUG_EVENT:
            ct = ev.u.CreateThread
            start_addr = ct.lpStartAddress or 0
            self._threads[tid] = {
                "tid": tid,
                "handle": ct.hThread,
                "start_address": start_addr,
                "is_main": False,
                "created_at": _now_ms(),
                "created_seq": seq,
                "discovered": False,
            }
            info.update({"start_address": start_addr})
            # Propagate process-global hardware BPs to the new thread.
            if self._hw_bps:
                try:
                    self._apply_hw_bps_to_thread(tid)
                except Exception:
                    pass

        elif code == EXIT_THREAD_DEBUG_EVENT:
            ec = ev.u.ExitThread.dwExitCode
            entry = self._threads.pop(tid, None)
            now = _now_ms()
            self._exited_threads.append(
                {
                    "tid": tid,
                    "start_address": (entry or {}).get("start_address", 0),
                    "is_main": (entry or {}).get("is_main", False),
                    "exit_code": int(ec),
                    "created_at": (entry or {}).get("created_at"),
                    "exited_at": now,
                    "lifetime_ms": (
                        now - entry["created_at"]
                        if entry and entry.get("created_at") is not None
                        else None
                    ),
                    "created_seq": (entry or {}).get("created_seq"),
                    "exited_seq": seq,
                }
            )
            if entry and entry.get("handle"):
                try:
                    k32.CloseHandle(entry["handle"])
                except Exception:
                    pass
            info.update({"exit_code": int(ec)})

        elif code == EXIT_PROCESS_DEBUG_EVENT:
            ec = ev.u.ExitProcess.dwExitCode
            self._exit_code = ec
            info.update({"exit_code": ec, "running": False})
            # MUST continue this event before handles become invalid.
            k32.ContinueDebugEvent(ev.dwProcessId, tid, DBG_CONTINUE)
            self._cleanup_handles()
            self._last_event = info
            return info

        elif code == LOAD_DLL_DEBUG_EVENT:
            ld = ev.u.LoadDll
            base = ld.lpBaseOfDll or 0
            path = self._image_path(ld.hFile, base) or ""
            self._add_module(base, path, seq, is_image=False)
            if ld.hFile:
                k32.CloseHandle(ld.hFile)
            m = self._modules.get(base, {})
            info.update(
                {
                    "base": base,
                    "path": path,
                    "size": m.get("size"),
                    "entry": m.get("entry"),
                }
            )

        elif code == UNLOAD_DLL_DEBUG_EVENT:
            base = ev.u.UnloadDll.lpBaseOfDll or 0
            mod = self._modules.pop(base, None)
            now = _now_ms()
            self._unloaded_modules.append(
                {
                    "base": base,
                    "name": (mod or {}).get("name"),
                    "path": (mod or {}).get("path"),
                    "size": (mod or {}).get("size"),
                    "entry": (mod or {}).get("entry"),
                    "loaded_at": (mod or {}).get("loaded_at"),
                    "loaded_seq": (mod or {}).get("loaded_seq"),
                    "unloaded_at": now,
                    "unloaded_seq": seq,
                    "lifetime_ms": (
                        now - mod["loaded_at"]
                        if mod and mod.get("loaded_at") is not None
                        else None
                    ),
                }
            )
            info.update({"base": base, "name": (mod or {}).get("name")})

        elif code == OUTPUT_DEBUG_STRING_EVENT:
            ods = ev.u.DebugString
            info.update(
                {
                    "string": self._read_debug_string(ods),
                }
            )

        elif code == EXCEPTION_DEBUG_EVENT:
            er = ev.u.Exception.ExceptionRecord
            ec = er.ExceptionCode & 0xFFFFFFFF
            addr = er.ExceptionAddress or 0
            first_chance = bool(ev.u.Exception.dwFirstChance)
            info.update(
                {
                    "exception": EXCEPTION_NAMES.get(ec, hex(ec)),
                    "code": ec,
                    "address": addr,
                    "first_chance": first_chance,
                }
            )
            # User-set software BP hit: restore the original byte, decrement
            # RIP back to the BP address, and remember to re-arm 0xCC after
            # the user resumes (handled in _resume_past_bp_if_needed).
            is_bp_code = ec in (EXCEPTION_BREAKPOINT, STATUS_WX86_BREAKPOINT)
            if is_bp_code and addr in self._bps:
                orig = self._bps[addr]["orig"]
                self._write_bytes(addr, bytes([orig]), flush=True)
                ctx = self._raw_get_context(tid)
                setattr(ctx, self._pc_field(), int(addr))
                self._raw_set_context(tid, ctx)
                self._pending_reArm = addr
                info["hit_bp"] = addr
            elif is_bp_code and not self._loader_bp_seen:
                self._loader_bp_seen = True
                info["loader_bp"] = True

            # Hardware BP probing: a SINGLE_STEP exception with a Bn bit
            # set in Dr6 is a HW BP firing, not a TF single-step. We
            # populate ev["hit_hw_bp"] before _resume_past_bp_if_needed
            # could otherwise consume the event as a synthetic step.
            is_ss = ec in (EXCEPTION_SINGLE_STEP, STATUS_WX86_SINGLE_STEP)
            if is_ss and self._hw_bps:
                try:
                    hw_ctx = self._raw_get_context(tid)
                    dr6 = int(hw_ctx.Dr6)
                    hit_type = None
                    for slot in range(4):
                        if dr6 & (1 << slot) and slot in self._hw_bps:
                            e = self._hw_bps[slot]
                            hit_type = e["type"]
                            info["hit_hw_bp"] = {
                                "slot": slot,
                                "addr": e["addr"],
                                "type": e["type"],
                                "size": e["size"],
                                "name": e.get("name"),
                                "dr6_raw": dr6,
                            }
                            break
                    # Clear Dr6's sticky Bn / BS bits so the next #DB
                    # reflects only fresh state.
                    hw_ctx.Dr6 = 0
                    # An execute breakpoint is a FAULT (reported before the
                    # instruction retires), so resuming re-faults at the same
                    # RIP unless we set the Resume Flag, which suppresses the
                    # instruction breakpoint for exactly one instruction. Data
                    # watchpoints are traps (reported after the access) and
                    # don't need it.
                    if hit_type == "x":
                        hw_ctx.EFlags |= EFLAGS_RF
                    self._raw_set_context(tid, hw_ctx)
                except Exception:
                    pass

        info["running"] = code != EXIT_PROCESS_DEBUG_EVENT
        info["_pending_continue"] = True
        info["_event_code"] = code
        self._last_event = info
        return info

    def _continue_last(self, status: int = DBG_CONTINUE):
        if self._last_event is None:
            return
        if not self._last_event.get("_pending_continue"):
            return
        ev = self._last_event
        k32.ContinueDebugEvent(self.pid, ev["tid"], status)
        ev["_pending_continue"] = False

    def continue_event(self, handled: bool = True) -> dict | None:
        """Ack the last debug event without pumping for the next one. Use
        between paired `wait()` calls when you want full control.

        handled=True   → DBG_CONTINUE             (debugger handled it)
        handled=False  → DBG_EXCEPTION_NOT_HANDLED (let SEH propagate;
                          relevant for first-chance exceptions)

        Returns the event dict that was ack'd, or None if nothing was
        pending. Does NOT touch any pending BP re-arm — call `cont`/`step`
        for that.
        """
        ev = self._last_event
        if not ev or not ev.get("_pending_continue"):
            return None
        status = DBG_CONTINUE if handled else DBG_EXCEPTION_NOT_HANDLED
        k32.ContinueDebugEvent(self.pid, ev["tid"], status)
        ev["_pending_continue"] = False
        return ev

    # ---------------- run / cont / step ----------------
    def _resume_past_bp_if_needed(self) -> dict | None:
        """If the last wait() decremented RIP onto a restored BP, step once
        over the original instruction and re-arm 0xCC. Returns the synthetic
        SINGLE_STEP event consumed (with `_internal_step=True`) or None when
        no BP-resume work was needed. Leaves _last_event ready for the
        caller's next ContinueDebugEvent.
        """
        if not self._pending_reArm:
            return None
        addr = self._pending_reArm
        self._pending_reArm = 0
        ctx = self._raw_get_context(self._cur_tid)
        pc = getattr(ctx, self._pc_field())
        if pc != addr:
            # User redirected the program counter — just re-arm; no synthetic step.
            if addr in self._bps:
                self._write_bytes(addr, b"\xcc", flush=True)
            return None
        # Set TF, ack the BP event, wait for the resulting SINGLE_STEP.
        ctx.EFlags |= EFLAGS_TF
        self._raw_set_context(self._cur_tid, ctx)
        self._continue_last(DBG_CONTINUE)
        while True:
            ev = self.wait(timeout_ms=2000)
            if ev["event"] == "timeout":
                return ev
            if (
                ev["event"] == "EXCEPTION"
                and ev.get("code") in (EXCEPTION_SINGLE_STEP, STATUS_WX86_SINGLE_STEP)
                and "hit_hw_bp" not in ev
            ):
                if addr in self._bps:
                    self._write_bytes(addr, b"\xcc", flush=True)
                ev["_internal_step"] = True
                return ev
            if self._is_internal(ev):
                self._continue_last(DBG_CONTINUE)
                continue
            # Foreign event during the dance: leave RIP-deltas as the OS
            # set them, but re-arm if still set.
            if addr in self._bps:
                self._write_bytes(addr, b"\xcc", flush=True)
            return ev

    def cont(
        self, timeout_ms: int = 2000, handled: bool | None = None, raw: bool = False
    ) -> dict:
        """Resume execution and return the next event.

        timeout_ms : total wall-clock budget for this call.
        handled    : how to ack the last event before resuming.
                     None  = auto (BP/SINGLE_STEP→handled; otherwise unhandled)
                     True  = DBG_CONTINUE (debugger handled the event)
                     False = DBG_EXCEPTION_NOT_HANDLED (let SEH propagate)
        raw        : if True, return the very next debug event without
                     filtering LOAD_DLL/CREATE_THREAD/etc. internally.
                     If False (default), internal events are consumed
                     silently along with the OS loader breakpoint and
                     our own re-arm single-step.
        """
        deadline = _now_ms() + max(0, int(timeout_ms))
        # A foreign event surfaced by the re-arm dance (e.g. another thread
        # hitting a conditional BP while we single-stepped the first thread)
        # is fed back here so it gets the same script evaluation as any
        # other hit, instead of leaking out unconditionally.
        pending_ev: dict | None = None
        # If we returned to the user paused on a user BP, step over now.
        rearm_ev = self._resume_past_bp_if_needed()
        if rearm_ev is not None:
            if rearm_ev.get("event") == "timeout":
                return rearm_ev
            if not rearm_ev.get("_internal_step"):
                # Foreign event arrived during BP-resume — re-process it.
                pending_ev = rearm_ev
            else:
                # Synthetic step succeeded; ack and continue normal pump.
                self._continue_last(DBG_CONTINUE)
        else:
            if handled is None:
                self._continue_last(
                    DBG_CONTINUE if self._is_handled() else DBG_EXCEPTION_NOT_HANDLED
                )
            else:
                self._continue_last(
                    DBG_CONTINUE if handled else DBG_EXCEPTION_NOT_HANDLED
                )
        while True:
            if pending_ev is not None:
                ev, pending_ev = pending_ev, None
            else:
                remaining = deadline - _now_ms()
                if remaining <= 0:
                    return {"event": "timeout", "running": True}
                ev = self.wait(timeout_ms=min(500, remaining))
                if ev["event"] == "timeout":
                    continue
            if raw:
                return ev
            if self._is_internal(ev):
                self._continue_last(DBG_CONTINUE)
                continue
            # Conditional/action BPs: evaluate server-side scripts and, if
            # they say "resume", silently re-arm + step over and keep pumping.
            # Same logic for software (hit_bp) and hardware (hit_hw_bp) BPs;
            # only the resume path differs because HW BPs need no re-arm.
            if "hit_bp" in ev or "hit_hw_bp" in ev:
                decision, meta = self._eval_bp_scripts(ev)
                if meta is not None:
                    ev["bp_script"] = meta
                if decision == "resume":
                    if "hit_bp" in ev:
                        rearm_ev = self._resume_past_bp_if_needed()
                        if rearm_ev is None:
                            # Action redirected the PC; just ack and keep pumping.
                            self._continue_last(DBG_CONTINUE)
                            continue
                        if rearm_ev.get("event") == "timeout":
                            return rearm_ev
                        if not rearm_ev.get("_internal_step"):
                            # Another thread's event surfaced mid-dance —
                            # re-process so its own BP script is evaluated.
                            pending_ev = rearm_ev
                            continue
                        self._continue_last(DBG_CONTINUE)
                        continue
                    else:
                        # HW BP hit: nothing to re-arm. Just ack and pump on.
                        self._continue_last(DBG_CONTINUE)
                        continue
            return ev

    def step(self, n: int = 1) -> dict:
        """Single-step `n` instructions on the current thread.

        If a BP was hit and is awaiting re-arm, the first step performs the
        re-arm dance (steps the original instruction + restores 0xCC) and
        counts as one of the `n` requested steps.
        """
        last: dict | None = None
        n = int(n)
        for i in range(n):
            rearm_ev = self._resume_past_bp_if_needed()
            if rearm_ev is not None:
                if rearm_ev.get("event") == "timeout":
                    return rearm_ev
                last = rearm_ev
                if not rearm_ev.get("_internal_step"):
                    # Foreign event arrived during the dance — return it.
                    return rearm_ev
                # The synthetic step counts. Only ack if more steps remain;
                # otherwise leave the event pending so the process stays
                # paused for the user.
                if i + 1 < n:
                    self._continue_last(DBG_CONTINUE)
                    continue
                else:
                    return last
            # Plain single-step.
            self._set_tf(self._cur_tid, True)
            self._continue_last(DBG_CONTINUE)
            while True:
                ev = self.wait(timeout_ms=2000)
                if ev["event"] == "timeout":
                    return ev
                if (
                    ev["event"] == "EXCEPTION"
                    and ev.get("code")
                    in (EXCEPTION_SINGLE_STEP, STATUS_WX86_SINGLE_STEP)
                    and "hit_hw_bp" not in ev
                ):
                    last = ev
                    break
                if self._is_internal(ev):
                    self._continue_last(DBG_CONTINUE)
                    continue
                return ev
        return last or {"event": "step_done"}

    def step_over(self) -> dict:
        """Step one instruction, treating CALL/REP-prefix insns as 'step over'.

        Decodes the current instruction with capstone; if it's a CALL or has
        a REP/REPE/REPNE prefix, sets a one-shot software BP at RIP+size and
        continues; otherwise falls back to single-step.
        """
        regs = self.get_regs()
        rip = regs.get("Rip", regs.get("Eip"))
        try:
            buf = self.read_mem(rip, 16)
        except Exception:
            return self.step(1)
        bs = bytes.fromhex(buf["hex"])
        ins = next(_md(self._wow64).disasm(bs, rip), None)
        if ins is None:
            return self.step(1)
        mn = ins.mnemonic.lower()
        prefixes = bytes(ins.prefix)  # 4 bytes; non-zero entries are prefixes
        is_rep = any(p in (0xF2, 0xF3) for p in prefixes)
        if mn.startswith("call") or is_rep:
            after = rip + ins.size
            transient = after not in self._bps
            if transient:
                self.set_bp(after)
            try:
                ev = self.cont(timeout_ms=5000)
            finally:
                if transient and after in self._bps:
                    self.clear_bp(after)
            return ev
        return self.step(1)

    # ---------------- breakpoints ----------------
    def _coerce_bp_addr(self, addr_or_symbol) -> int:
        """Accept an int, a hex string, or a `module!name` symbol."""
        if isinstance(addr_or_symbol, str):
            s = addr_or_symbol
            if s.startswith(("0x", "0X")):
                return int(s, 16)
            if "!" in s:
                resolved = self.resolve(s)
                if not resolved:
                    raise ValueError(f"could not resolve symbol: {s}")
                return resolved
            try:
                return int(s, 0)
            except ValueError:
                raise ValueError(f"unrecognised bp target: {s!r}")
        return int(addr_or_symbol)

    def set_bp(
        self,
        addr,
        condition: str | None = None,
        action: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Set a software BP. Optional server-side scripts:

        condition : Python expression (str) evaluated on the worker thread
                    when the BP fires. If it returns falsy the BP is
                    silently skipped (debuggee resumes; no client event).
                    If truthy, the action runs (if any) and the event is
                    surfaced unless the action sets `result = "resume"`.
                    If the expression raises, the BP is treated as
                    triggered (suspend) and the error is recorded on the
                    BP entry / surfaced on the event.
        action    : Python source (str, may be multiple statements) run
                    after a passing condition. Set `result = "resume"` to
                    auto-resume transparently (e.g. patch then continue);
                    leave unset / "suspend" to surface the event.
        name      : optional human-readable label.

        Script namespace: `dbg` (the impl), `regs` (current register
        snapshot, dict), `bp` (the BP entry — `bp["state"]` survives across
        hits), `gstate` (cross-BP scratchpad), `ev` (the event dict).
        """
        addr = self._coerce_bp_addr(addr)
        if addr in self._bps:
            return {"set": False, "reason": "already_set", "addr": addr}
        orig = self._read_byte(addr)
        if orig == 0xCC:
            return {"set": False, "reason": "real_int3", "addr": addr}
        cc, ac, cerr, aerr = self._compile_bp_scripts(condition, action, addr)
        if cerr:
            return {
                "set": False,
                "reason": "condition_syntax_error",
                "addr": addr,
                "error": cerr,
            }
        if aerr:
            return {
                "set": False,
                "reason": "action_syntax_error",
                "addr": addr,
                "error": aerr,
            }
        self._write_bytes(addr, b"\xcc", flush=True)
        entry = {
            "addr": addr,
            "orig": orig,
            "name": name,
            "condition": condition,
            "condition_compiled": cc,
            "action": action,
            "action_compiled": ac,
            "hits": 0,
            "skipped": 0,
            "state": {},
        }
        self._bps[addr] = entry
        sym = self.addr_to_symbol(addr)
        out = {"set": True, "addr": addr, "orig": orig, "name": name}
        if condition:
            out["condition"] = condition
        if action:
            out["action"] = action
        if sym:
            out["symbol"] = sym
        return out

    def clear_bp(self, addr) -> dict:
        addr = self._coerce_bp_addr(addr)
        if addr not in self._bps:
            return {"cleared": False, "reason": "not_set", "addr": addr}
        entry = self._bps.pop(addr)
        self._write_bytes(addr, bytes([entry["orig"]]), flush=True)
        return {
            "cleared": True,
            "addr": addr,
            "orig": entry["orig"],
            "name": entry.get("name"),
            "hits": entry.get("hits", 0),
            "skipped": entry.get("skipped", 0),
        }

    def list_bps(self) -> list:
        out = []
        for addr in sorted(self._bps):
            e = self._bps[addr]
            row = {
                "addr": addr,
                "orig": e["orig"],
                "name": e.get("name"),
                "hits": e.get("hits", 0),
                "skipped": e.get("skipped", 0),
            }
            if e.get("condition"):
                row["condition"] = e["condition"]
            if e.get("action"):
                row["action"] = e["action"]
            if e.get("condition_error"):
                row["condition_error"] = e["condition_error"]
            if e.get("action_error"):
                row["action_error"] = e["action_error"]
            sym = self.addr_to_symbol(addr)
            if sym and "name" in sym:
                row["symbol"] = (
                    f"{sym['module']}!{sym['name']}+{sym.get('offset', 0):#x}"
                )
            out.append(row)
        return out

    # ---------------- hardware breakpoints ----------------
    def set_hw_bp(
        self,
        addr_or_symbol,
        type: str = "x",
        size: int = 1,
        condition: str | None = None,
        action: str | None = None,
        name: str | None = None,
        slot: int | None = None,
        threads: list | None = None,
    ) -> dict:
        """Set a hardware breakpoint via Dr0..Dr3 + Dr7. Up to four slots
        across the whole debuggee.

        type:    "x" (execute, size must be 1), "w" (data write),
                 "rw" (data read or write). "io" requires CR4.DE which
                 user-mode can't toggle, so it's rejected here.
        size:    1, 2, 4 (or 8 — x64 only). Must be 1 when type=="x".
        slot:    None to auto-allocate the first free slot, else 0..3.
        threads: list of tids to restrict the BP to; None for
                 process-global (current + future via CREATE_THREAD).
        condition / action / name: same shape as set_bp; the script
                 namespace is identical (dbg, regs, bp, ev, state, gstate).
        """
        if type not in HW_BP_RW_BITS:
            return {
                "set": False,
                "reason": "bad_type",
                "detail": f"type must be one of {sorted(HW_BP_RW_BITS)}",
            }
        if type == "io":
            return {
                "set": False,
                "reason": "io_unsupported",
                "detail": "I/O breakpoints require CR4.DE; not exposed",
            }
        if size not in HW_BP_LEN_BITS:
            return {
                "set": False,
                "reason": "bad_size",
                "detail": "size must be 1, 2, 4, or 8",
            }
        if type == "x" and size != 1:
            return {
                "set": False,
                "reason": "bad_size_for_execute",
                "detail": "execute breakpoints require size=1",
            }
        if size == 8 and self._wow64:
            return {
                "set": False,
                "reason": "size8_wow64",
                "detail": "size=8 is x64-only",
            }
        try:
            addr = self._coerce_bp_addr(addr_or_symbol)
        except ValueError as e:
            return {"set": False, "reason": "bad_addr", "detail": str(e)}
        if self._wow64 and addr >= (1 << 32):
            return {
                "set": False,
                "reason": "addr_above_4gb",
                "detail": "WOW64 debug registers are 32-bit",
            }
        # Slot allocation
        if slot is None:
            for s in range(4):
                if s not in self._hw_bps:
                    slot = s
                    break
            if slot is None:
                return {
                    "set": False,
                    "reason": "no_slot_available",
                    "detail": "all 4 hardware BP slots are in use",
                }
        else:
            slot = int(slot)
            if not 0 <= slot < 4:
                return {
                    "set": False,
                    "reason": "bad_slot",
                    "detail": "slot must be 0..3",
                }
            if slot in self._hw_bps:
                return {"set": False, "reason": "slot_in_use", "slot": slot}
        cc, ac, cerr, aerr = self._compile_bp_scripts(condition, action, addr)
        if cerr:
            return {
                "set": False,
                "reason": "condition_syntax_error",
                "addr": addr,
                "error": cerr,
            }
        if aerr:
            return {
                "set": False,
                "reason": "action_syntax_error",
                "addr": addr,
                "error": aerr,
            }
        thread_filter = None
        if threads is not None:
            thread_filter = [int(t) for t in threads]
        entry = {
            "slot": slot,
            "addr": addr,
            "type": type,
            "size": size,
            "name": name,
            "condition": condition,
            "condition_compiled": cc,
            "action": action,
            "action_compiled": ac,
            "hits": 0,
            "skipped": 0,
            "state": {},
            "threads": thread_filter,
        }
        self._hw_bps[slot] = entry
        # Apply to all current threads (or the restricted set).
        target_tids = (
            thread_filter if thread_filter is not None else list(self._threads)
        )
        applied = []
        errors = {}
        for tid in target_tids:
            try:
                self._apply_hw_bps_to_thread(tid)
                applied.append(tid)
            except OSError as exc:
                errors[tid] = f"{exc.__class__.__name__}: {exc}"
        sym = self.addr_to_symbol(addr)
        out = {
            "set": True,
            "slot": slot,
            "addr": addr,
            "type": type,
            "size": size,
            "name": name,
            "applied_to": applied,
        }
        if condition:
            out["condition"] = condition
        if action:
            out["action"] = action
        if sym:
            out["symbol"] = sym
        if errors:
            out["apply_errors"] = errors
        return out

    def clear_hw_bp(self, addr_or_slot) -> dict:
        """Remove a hardware BP by slot (int 0..3), address (int), or
        `module!name` symbol. Zeroes Dr_n + Dr7 bits on every thread the
        BP was applied to."""
        target_slot = None
        if (
            isinstance(addr_or_slot, int)
            and 0 <= addr_or_slot < 4
            and addr_or_slot in self._hw_bps
        ):
            target_slot = addr_or_slot
        else:
            try:
                addr = self._coerce_bp_addr(addr_or_slot)
            except ValueError as e:
                return {"cleared": False, "reason": "bad_target", "detail": str(e)}
            for s, e in self._hw_bps.items():
                if e["addr"] == addr:
                    target_slot = s
                    break
        if target_slot is None:
            return {"cleared": False, "reason": "not_set"}
        entry = self._hw_bps.pop(target_slot)
        target_tids = (
            entry.get("threads")
            if entry.get("threads") is not None
            else list(self._threads)
        )
        for tid in target_tids:
            try:
                self._apply_hw_bps_to_thread(tid)
            except Exception:
                pass
        return {
            "cleared": True,
            "slot": target_slot,
            "addr": entry["addr"],
            "type": entry["type"],
            "size": entry["size"],
            "name": entry.get("name"),
            "hits": entry.get("hits", 0),
            "skipped": entry.get("skipped", 0),
        }

    def list_hw_bps(self) -> list:
        out = []
        for slot in sorted(self._hw_bps):
            e = self._hw_bps[slot]
            row = {
                "slot": slot,
                "addr": e["addr"],
                "type": e["type"],
                "size": e["size"],
                "name": e.get("name"),
                "hits": e.get("hits", 0),
                "skipped": e.get("skipped", 0),
            }
            if e.get("condition"):
                row["condition"] = e["condition"]
            if e.get("action"):
                row["action"] = e["action"]
            if e.get("condition_error"):
                row["condition_error"] = e["condition_error"]
            if e.get("action_error"):
                row["action_error"] = e["action_error"]
            if e.get("threads") is not None:
                row["threads"] = list(e["threads"])
            sym = self.addr_to_symbol(e["addr"])
            if sym and "name" in sym:
                row["symbol"] = (
                    f"{sym['module']}!{sym['name']}+{sym.get('offset', 0):#x}"
                )
            out.append(row)
        return out

    def _apply_hw_bps_to_thread(self, tid: int) -> None:
        """Project the current self._hw_bps table onto one thread's
        Dr0..Dr7. Slots not in the table (or restricted to other tids)
        are zeroed."""
        ctx = self._raw_get_context(tid)
        dr7 = 0
        for slot in range(4):
            e = self._hw_bps.get(slot)
            applies = e is not None and (
                e.get("threads") is None or tid in e["threads"]
            )
            if applies:
                setattr(ctx, f"Dr{slot}", int(e["addr"]))
                rw = HW_BP_RW_BITS[e["type"]]
                ln = HW_BP_LEN_BITS[e["size"]]
                dr7 |= 1 << (slot * 2)  # Ln (local enable)
                dr7 |= rw << (16 + slot * 4)
                dr7 |= ln << (18 + slot * 4)
            else:
                setattr(ctx, f"Dr{slot}", 0)
        if dr7:
            dr7 |= DR7_LE | DR7_RESERVED_MUST_BE_1
        ctx.Dr7 = dr7
        self._raw_set_context(tid, ctx)

    def _compile_bp_scripts(self, condition, action, addr):
        cc = ac = None
        cerr = aerr = None
        if condition:
            try:
                cc = compile(condition, f"<bp@{addr:#x}.condition>", "eval")
            except SyntaxError as e:
                cerr = f"{type(e).__name__}: {e}"
        if action:
            try:
                ac = compile(action, f"<bp@{addr:#x}.action>", "exec")
            except SyntaxError as e:
                aerr = f"{type(e).__name__}: {e}"
        return cc, ac, cerr, aerr

    def _bp_script_ns(self, ev: dict, bp: dict) -> dict:
        """Build the namespace for a BP condition/action eval."""
        try:
            regs = self.get_regs()
        except Exception as exc:
            regs = {"_error": f"{type(exc).__name__}: {exc}"}
        return {
            "__builtins__": __builtins__,
            "dbg": self,
            "regs": regs,
            "bp": bp,
            "ev": ev,
            "state": bp.setdefault("state", {}),
            "gstate": self._bp_gstate,
            "addr": bp["addr"],
            "result": None,
        }

    def _eval_bp_scripts(self, ev: dict) -> tuple:
        """Run condition + action for the BP that fired (sw or hw).
        Returns (decision, meta) where decision is 'suspend' | 'resume'."""
        # Software BP: keyed by addr in self._bps. Hardware BP: keyed by
        # slot in self._hw_bps; ev["hit_hw_bp"] carries {slot, addr, ...}.
        sw_addr = ev.get("hit_bp")
        hw_info = ev.get("hit_hw_bp")
        kind = None
        bp = None
        addr = None
        if sw_addr is not None:
            bp = self._bps.get(sw_addr)
            kind = "sw"
            addr = sw_addr
        elif isinstance(hw_info, dict):
            bp = self._hw_bps.get(hw_info.get("slot"))
            kind = "hw"
            addr = hw_info.get("addr")
        if not isinstance(bp, dict):
            return ("suspend", None)
        bp["hits"] = bp.get("hits", 0) + 1
        meta = {"addr": addr, "name": bp.get("name"), "hits": bp["hits"], "kind": kind}
        if kind == "hw":
            meta["slot"] = bp.get("slot")

        if bp.get("condition_compiled") is None and bp.get("action_compiled") is None:
            return ("suspend", None)

        ns = self._bp_script_ns(ev, bp)

        if bp.get("condition_compiled") is not None:
            try:
                cond = bool(eval(bp["condition_compiled"], ns))
                meta["condition"] = cond
            except BaseException as exc:
                msg = f"{type(exc).__name__}: {exc}"
                bp["condition_error"] = msg
                meta["condition_error"] = msg
                cond = True  # fail-stop: surface the BP so the user sees it
                meta["condition"] = True
            if not cond:
                bp["skipped"] = bp.get("skipped", 0) + 1
                meta["skipped_total"] = bp["skipped"]
                bp["last_decision"] = "resume"
                return ("resume", meta)

        if bp.get("action_compiled") is not None:
            try:
                exec(bp["action_compiled"], ns)
                ret = ns.get("result")
                if ret is not None:
                    meta["action_result"] = ret
            except BaseException as exc:
                msg = f"{type(exc).__name__}: {exc}"
                bp["action_error"] = msg
                meta["action_error"] = msg
                ret = None
            if ret in ("resume", True):
                bp["skipped"] = bp.get("skipped", 0) + 1
                meta["skipped_total"] = bp["skipped"]
                bp["last_decision"] = "resume"
                return ("resume", meta)

        bp["last_decision"] = "suspend"
        return ("suspend", meta)

    # ---------------- registers ----------------
    def _int_regs(self) -> tuple:
        return WOW64_INTEGER_REGS if self._wow64 else INTEGER_REGS

    def _pc_field(self) -> str:
        return "Eip" if self._wow64 else "Rip"

    def get_regs(self, tid: int | None = None) -> dict:
        tid = tid or self._cur_tid
        ctx = self._raw_get_context(tid)
        out = {n: getattr(ctx, n) for n in self._int_regs()}
        for n in SEG_REGS:
            out[n] = getattr(ctx, n)
        out["EFlags"] = ctx.EFlags
        return out

    def set_reg(self, name: str, value: int, tid: int | None = None) -> dict:
        tid = tid or self._cur_tid
        ctx = self._raw_get_context(tid)
        # Accept case variants: rip, RIP, Rip / eip, EIP, Eip
        canonical = None
        for n in self._int_regs() + SEG_REGS + ("EFlags",):
            if n.lower() == name.lower():
                canonical = n
                break
        if canonical is None:
            raise ValueError(f"unknown register: {name}")
        mask = 0xFFFFFFFF if self._wow64 else 0xFFFFFFFFFFFFFFFF
        setattr(ctx, canonical, int(value) & mask)
        self._raw_set_context(tid, ctx)
        return {"set": True, "register": canonical, "value": int(value) & mask}

    def _set_tf(self, tid: int, on: bool):
        ctx = self._raw_get_context(tid)
        if on:
            ctx.EFlags |= EFLAGS_TF
        else:
            ctx.EFlags &= ~EFLAGS_TF
        self._raw_set_context(tid, ctx)

    def _raw_get_context(self, tid: int, flags: int | None = None):
        """Return a thread CONTEXT (or WOW64_CONTEXT for 32-bit guests)."""
        h = self._open_thread(tid)
        if self._wow64:
            f = flags if flags is not None else WOW64_CONTEXT_ALL
            if not _HAS_WOW64_CONTEXT:
                raise OSError("WOW64 context APIs not available on this host")
            _hold, ctx = _alloc_wow64_context(f)
            if not k32.Wow64GetThreadContext(h, byref(ctx)):
                raise _winerror("Wow64GetThreadContext")
        else:
            f = flags if flags is not None else CONTEXT_ALL
            _hold, ctx = _alloc_context(f)
            if not k32.GetThreadContext(h, byref(ctx)):
                raise _winerror("GetThreadContext")
        # Keep buffer alive through caller use by stashing on instance.
        self.__dict__.setdefault("_ctx_hold", []).append(_hold)
        if len(self.__dict__["_ctx_hold"]) > 8:
            self.__dict__["_ctx_hold"] = self.__dict__["_ctx_hold"][-4:]
        return ctx

    def _raw_set_context(self, tid: int, ctx):
        h = self._open_thread(tid)
        if self._wow64:
            if not k32.Wow64SetThreadContext(h, byref(ctx)):
                raise _winerror("Wow64SetThreadContext")
        else:
            if not k32.SetThreadContext(h, byref(ctx)):
                raise _winerror("SetThreadContext")

    def _open_thread(self, tid: int) -> int:
        entry = self._threads.get(tid)
        if entry and entry.get("handle"):
            return entry["handle"]
        h = k32.OpenThread(THREAD_ALL_ACCESS, False, tid)
        if not h:
            raise _winerror("OpenThread")
        # We learned about this tid outside the debug-event stream (e.g. user
        # passed it in directly). Record a minimal entry tagged `discovered`.
        self._threads[tid] = {
            "tid": tid,
            "handle": h,
            "start_address": 0,
            "is_main": False,
            "created_at": _now_ms(),
            "created_seq": None,
            "discovered": True,
        }
        return h

    # ---------------- memory ----------------
    def read_mem(self, addr: int, n: int) -> dict:
        buf = (c_ubyte * int(n))()
        got = c_size_t(0)
        if not k32.ReadProcessMemory(
            self.h_process, c_void_p(int(addr)), buf, int(n), byref(got)
        ):
            raise _winerror("ReadProcessMemory")
        data = bytes(buf[: got.value])
        return {"addr": int(addr), "size": got.value, "hex": data.hex()}

    def write_mem(self, addr: int, hexbytes: str | bytes, flush: bool = True) -> dict:
        if isinstance(hexbytes, str):
            data = bytes.fromhex(hexbytes.replace(" ", ""))
        else:
            data = bytes(hexbytes)
        self._invalidate_bps_in_range(int(addr), len(data))
        self._write_bytes(int(addr), data, flush=flush)
        return {"addr": int(addr), "wrote": len(data), "flushed": flush}

    # ---- typed read helpers (little-endian; x64 native) ----
    def read_int(self, addr: int, size: int = 8, signed: bool = False) -> int:
        data = bytes.fromhex(self.read_mem(int(addr), int(size))["hex"])
        return int.from_bytes(data, "little", signed=signed)

    def read_u8(self, addr):
        return self.read_int(addr, 1, False)

    def read_u16(self, addr):
        return self.read_int(addr, 2, False)

    def read_u32(self, addr):
        return self.read_int(addr, 4, False)

    def read_u64(self, addr):
        return self.read_int(addr, 8, False)

    def read_i8(self, addr):
        return self.read_int(addr, 1, True)

    def read_i16(self, addr):
        return self.read_int(addr, 2, True)

    def read_i32(self, addr):
        return self.read_int(addr, 4, True)

    def read_i64(self, addr):
        return self.read_int(addr, 8, True)

    def read_ptr(self, addr):
        return self.read_int(addr, 8, False)

    def read_f32(self, addr: int) -> float:
        data = bytes.fromhex(self.read_mem(int(addr), 4)["hex"])
        return struct.unpack("<f", data)[0]

    def read_f64(self, addr: int) -> float:
        data = bytes.fromhex(self.read_mem(int(addr), 8)["hex"])
        return struct.unpack("<d", data)[0]

    def read_cstr(self, addr: int, max_len: int = 256) -> str:
        """Read NUL-terminated ASCII/Latin-1 up to max_len bytes."""
        data = bytes.fromhex(self.read_mem(int(addr), int(max_len))["hex"])
        end = data.find(b"\x00")
        if end != -1:
            data = data[:end]
        return data.decode("latin-1", errors="replace")

    def read_wstr(self, addr: int, max_chars: int = 256) -> str:
        """Read NUL-terminated UTF-16 LE up to max_chars characters."""
        data = bytes.fromhex(self.read_mem(int(addr), int(max_chars) * 2)["hex"])
        # find double-null at even offset
        end = -1
        for i in range(0, len(data) - 1, 2):
            if data[i] == 0 and data[i + 1] == 0:
                end = i
                break
        if end != -1:
            data = data[:end]
        return data.decode("utf-16-le", errors="replace")

    # ---- typed write helpers (little-endian; flushes icache) ----
    def write_int(
        self, addr: int, value: int, size: int = 8, signed: bool = False
    ) -> dict:
        data = int(value).to_bytes(int(size), "little", signed=signed)
        return self.write_mem(int(addr), data)

    def write_u8(self, addr, v):
        return self.write_int(addr, v, 1, False)

    def write_u16(self, addr, v):
        return self.write_int(addr, v, 2, False)

    def write_u32(self, addr, v):
        return self.write_int(addr, v, 4, False)

    def write_u64(self, addr, v):
        return self.write_int(addr, v, 8, False)

    def write_i8(self, addr, v):
        return self.write_int(addr, v, 1, True)

    def write_i16(self, addr, v):
        return self.write_int(addr, v, 2, True)

    def write_i32(self, addr, v):
        return self.write_int(addr, v, 4, True)

    def write_i64(self, addr, v):
        return self.write_int(addr, v, 8, True)

    def write_ptr(self, addr, v):
        return self.write_int(addr, v, 8, False)

    def write_f32(self, addr: int, value: float) -> dict:
        return self.write_mem(int(addr), struct.pack("<f", float(value)))

    def write_f64(self, addr: int, value: float) -> dict:
        return self.write_mem(int(addr), struct.pack("<d", float(value)))

    def write_cstr(self, addr: int, s: str, nul: bool = True) -> dict:
        data = s.encode("latin-1", errors="replace") + (b"\x00" if nul else b"")
        return self.write_mem(int(addr), data)

    def write_wstr(self, addr: int, s: str, nul: bool = True) -> dict:
        data = s.encode("utf-16-le") + (b"\x00\x00" if nul else b"")
        return self.write_mem(int(addr), data)

    def _read_byte(self, addr: int) -> int:
        h = self.read_mem(addr, 1)["hex"]
        return int(h, 16) if h else 0

    def _write_bytes(self, addr: int, data: bytes, flush: bool = False):
        wrote = c_size_t(0)
        buf = (c_ubyte * len(data))(*data)
        if not k32.WriteProcessMemory(
            self.h_process, c_void_p(int(addr)), buf, len(data), byref(wrote)
        ):
            raise _winerror("WriteProcessMemory")
        if flush:
            k32.FlushInstructionCache(self.h_process, c_void_p(int(addr)), len(data))

    def _invalidate_bps_in_range(self, addr: int, size: int):
        """Drop any BP whose 0xCC address falls inside the patched range
        and cancel a pending re-arm there. Keeps the table consistent with
        what the user just wrote."""
        end = int(addr) + int(size)
        gone = [a for a in self._bps if int(addr) <= a < end]
        for a in gone:
            self._bps.pop(a, None)
        if int(addr) <= self._pending_reArm < end:
            self._pending_reArm = 0

    # ---------------- assembly ----------------
    def assemble(self, asm: str, addr: int = 0) -> dict:
        """Assemble x86/x64 mnemonic source. Multiple instructions may be
        separated by ';' or newlines. Mode follows the debuggee bitness."""
        ks = _ks_engine(self._wow64)
        encoding, count = ks.asm(asm, int(addr))
        data = bytes(encoding) if encoding else b""
        return {"hex": data.hex(), "size": len(data), "count": count}

    def write_asm(self, addr: int, asm: str) -> dict:
        """Assemble and patch in-process. Use to overwrite code with
        mnemonic source instead of raw hex."""
        a = int(addr)
        out = self.assemble(asm, a)
        data = bytes.fromhex(out["hex"])
        self._invalidate_bps_in_range(a, len(data))
        self._write_bytes(a, data, flush=True)
        return {"addr": a, "wrote": out["size"], "count": out["count"]}

    # ---------------- disassembly ----------------
    def disasm(self, addr: int | None = None, count: int = 10) -> list:
        if addr is None:
            regs = self.get_regs()
            addr = regs.get("Rip", regs.get("Eip"))
        addr = int(addr)
        # Read enough bytes for `count` insns (avg 4 b/insn, cap at 15*count)
        n = min(15 * max(1, int(count)), 256)
        data = bytes.fromhex(self.read_mem(addr, n)["hex"])
        # Hide live 0xCC bytes coming from our own user breakpoints so the
        # listing reflects the real instructions.
        if self._bps:
            ba = bytearray(data)
            for bp_addr, bp in self._bps.items():
                if addr <= bp_addr < addr + len(ba):
                    ba[bp_addr - addr] = bp["orig"]
            data = bytes(ba)
        out = []
        for i, ins in enumerate(_md(self._wow64).disasm(data, addr)):
            out.append(
                {
                    "addr": ins.address,
                    "size": ins.size,
                    "bytes": bytes(ins.bytes).hex(),
                    "mnemonic": ins.mnemonic,
                    "op_str": ins.op_str,
                }
            )
            if i + 1 >= count:
                break
        return out

    # ---------------- entry points ----------------
    def entry_points(self) -> list:
        """Return the natural execution-order entry points for the EXE:
        TLS callbacks (per Windows loader semantics — stops at the first
        NULL pointer in AddressOfCallBacks) followed by the PE EntryPoint.

        Static PE info is parsed with `pefile` against the on-disk file
        (path collected from CREATE_PROCESS_DEBUG_EVENT). The TLS callback
        ARRAY ITSELF is read from the live process so that ASLR-relocated
        pointers are returned (not the static file values).
        """
        import pefile

        exe = next(
            (m for m in self._modules.values() if m["name"].lower().endswith(".exe")),
            None,
        )
        if not exe or not exe.get("path"):
            return []
        base = exe["base"]
        pe = pefile.PE(exe["path"], fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_TLS"]]
        )
        static_base = pe.OPTIONAL_HEADER.ImageBase
        # TLS callback pointers are pointer-width: 4 bytes for PE32
        # (Magic 0x10b / WOW64) and 8 for PE32+ (0x20b). Reading a fixed
        # 8 bytes would merge/skip adjacent 32-bit callbacks.
        ptr_size = 4 if pe.OPTIONAL_HEADER.Magic == 0x10B else 8
        out: list = []
        if hasattr(pe, "DIRECTORY_ENTRY_TLS"):
            cb_static_va = pe.DIRECTORY_ENTRY_TLS.struct.AddressOfCallBacks
            if cb_static_va:
                cb_runtime_va = base + (cb_static_va - static_base)
                for i in range(64):
                    p = self.read_int(cb_runtime_va + i * ptr_size, ptr_size)
                    if p == 0:
                        break
                    out.append(
                        {
                            "kind": "tls",
                            "index": i,
                            "addr": p,
                            "source": f"AddressOfCallBacks[{i}]",
                        }
                    )
        out.append(
            {
                "kind": "entry",
                "addr": base + pe.OPTIONAL_HEADER.AddressOfEntryPoint,
                "source": "PE.AddressOfEntryPoint",
            }
        )
        return out

    def break_on_entry_points(self) -> list:
        """Set a software BP on every entry point in execution order."""
        eps = self.entry_points()
        for ep in eps:
            ep["bp"] = self.set_bp(ep["addr"])
        return eps

    # ---------------- modules ----------------
    def _add_module(
        self, base: int, path: str, seq: int, is_image: bool = False
    ) -> dict:
        """Register a module from a CREATE_PROCESS / LOAD_DLL event and run
        the cheap PE-header parse so size/entry are known immediately."""
        entry = {
            "base": int(base),
            "name": _basename(path),
            "path": path,
            "is_image": bool(is_image),
            "loaded_at": _now_ms(),
            "loaded_seq": seq,
        }
        self._modules[int(base)] = entry
        self._parse_pe_headers(entry)
        return entry

    def _parse_pe_headers(self, m: dict) -> None:
        """Cheap header read (fast_load=True) — fills size, entry_rva, entry,
        machine, timestamp. Exports/imports are parsed lazily."""
        path = m.get("path") or ""
        if not path:
            m["pe_error"] = "no path"
            return
        try:
            import pefile

            pe = pefile.PE(path, fast_load=True)
            m["size"] = int(pe.OPTIONAL_HEADER.SizeOfImage)
            m["entry_rva"] = int(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
            m["entry"] = int(m["base"]) + m["entry_rva"]
            m["machine"] = int(pe.FILE_HEADER.Machine)
            m["timestamp"] = int(pe.FILE_HEADER.TimeDateStamp)
            pe.close()
        except Exception as exc:
            m["pe_error"] = f"{type(exc).__name__}: {exc}"

    def _ensure_exports(self, base: int) -> list:
        """Populate (and cache) m['exports'] from the on-disk PE."""
        m = self._modules.get(int(base))
        if not m:
            return []
        if "exports" in m:
            return m["exports"]
        path = m.get("path") or ""
        if not path:
            m["exports"] = []
            m["exports_error"] = "no path"
            return []
        try:
            import pefile

            pe = pefile.PE(path, fast_load=True)
            pe.parse_data_directories(
                directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
            )
            out = []
            if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
                for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                    name = e.name.decode("ascii", "replace") if e.name else None
                    fwd = (
                        e.forwarder.decode("ascii", "replace") if e.forwarder else None
                    )
                    out.append(
                        {
                            "rva": int(e.address) if e.address else 0,
                            "name": name,
                            "ordinal": int(e.ordinal),
                            "forwarder": fwd,
                        }
                    )
            pe.close()
            out.sort(key=lambda e: (e["rva"], e["ordinal"]))
            m["exports"] = out
        except Exception as exc:
            m["exports"] = []
            m["exports_error"] = f"{type(exc).__name__}: {exc}"
        return m["exports"]

    def _ensure_imports(self, base: int) -> list:
        """Populate (and cache) m['imports'] from the on-disk PE."""
        m = self._modules.get(int(base))
        if not m:
            return []
        if "imports" in m:
            return m["imports"]
        path = m.get("path") or ""
        if not path:
            m["imports"] = []
            m["imports_error"] = "no path"
            return []
        try:
            import pefile

            pe = pefile.PE(path, fast_load=True)
            pe.parse_data_directories(
                directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
            )
            # pefile reports imp.address as a VA against the file's
            # PREFERRED ImageBase, not the runtime base. Convert to an RVA
            # first, then re-base onto the module's actual load address so
            # iat_addr is correct under ASLR.
            preferred = int(pe.OPTIONAL_HEADER.ImageBase)
            run_base = int(m["base"])
            out = []
            if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
                for d in pe.DIRECTORY_ENTRY_IMPORT:
                    dll = d.dll.decode("ascii", "replace") if d.dll else ""
                    for imp in d.imports:
                        iat_rva = int(imp.address) - preferred if imp.address else 0
                        out.append(
                            {
                                "module": dll,
                                "name": (
                                    imp.name.decode("ascii", "replace")
                                    if imp.name
                                    else None
                                ),
                                "ordinal": (int(imp.ordinal) if imp.ordinal else None),
                                "iat_rva": iat_rva,
                                "iat_addr": (run_base + iat_rva if imp.address else 0),
                            }
                        )
            pe.close()
            m["imports"] = out
        except Exception as exc:
            m["imports"] = []
            m["imports_error"] = f"{type(exc).__name__}: {exc}"
        return m["imports"]

    def list_modules(
        self, with_exports: bool = False, with_imports: bool = False
    ) -> list:
        """Return the live module table (CREATE_PROCESS + LOAD_DLL events,
        minus UNLOAD_DLL). Default columns: base, name, path, size,
        entry_rva, entry, is_image, machine, timestamp, loaded_at, loaded_seq.

        with_exports=True / with_imports=True trigger the lazy PE parse and
        embed the corresponding lists. They can be heavy (ntdll has ~2500
        exports) — prefer per-module fetch via module_exports/module_imports.
        """
        out = []
        for m in sorted(self._modules.values(), key=lambda x: x["base"]):
            row = {
                k: m[k]
                for k in (
                    "base",
                    "name",
                    "path",
                    "size",
                    "entry_rva",
                    "entry",
                    "is_image",
                    "machine",
                    "timestamp",
                    "loaded_at",
                    "loaded_seq",
                )
                if k in m
            }
            if "pe_error" in m:
                row["pe_error"] = m["pe_error"]
            if with_exports:
                self._ensure_exports(m["base"])
                row["exports"] = self._public_exports(m)
                if "exports_error" in m:
                    row["exports_error"] = m["exports_error"]
            if with_imports:
                self._ensure_imports(m["base"])
                row["imports"] = list(m.get("imports", []))
                if "imports_error" in m:
                    row["imports_error"] = m["imports_error"]
            out.append(row)
        return out

    def module_info(
        self, key, with_exports: bool = False, with_imports: bool = False
    ) -> dict | None:
        """Look up a module by base address or (case-insensitive) name/path."""
        m = self._lookup_module(key)
        if m is None:
            return None
        row = {
            k: m[k]
            for k in (
                "base",
                "name",
                "path",
                "size",
                "entry_rva",
                "entry",
                "is_image",
                "machine",
                "timestamp",
                "loaded_at",
                "loaded_seq",
            )
            if k in m
        }
        if "pe_error" in m:
            row["pe_error"] = m["pe_error"]
        if with_exports:
            self._ensure_exports(m["base"])
            row["exports"] = self._public_exports(m)
        if with_imports:
            self._ensure_imports(m["base"])
            row["imports"] = list(m.get("imports", []))
        return row

    def _lookup_module(self, key) -> dict | None:
        if isinstance(key, int):
            return self._modules.get(int(key))
        if not isinstance(key, str):
            return None
        kl = key.lower()
        # exact basename / path / name-without-extension / hex base
        cand = []
        for m in self._modules.values():
            n = (m.get("name") or "").lower()
            p = (m.get("path") or "").lower()
            if n == kl or p == kl:
                return m
            stem = n.rsplit(".", 1)[0] if "." in n else n
            if stem == kl:
                cand.append(m)
        if cand:
            return cand[0]
        if kl.startswith("0x"):
            try:
                return self._modules.get(int(kl, 16))
            except ValueError:
                pass
        return None

    def _public_exports(self, m: dict) -> list:
        base = int(m["base"])
        return [
            {
                "name": e["name"],
                "ordinal": e["ordinal"],
                "rva": e["rva"],
                "addr": (base + e["rva"]) if e["rva"] else 0,
                "forwarder": e.get("forwarder"),
            }
            for e in m.get("exports", [])
        ]

    def module_exports(self, key) -> list:
        m = self._lookup_module(key)
        if m is None:
            return []
        self._ensure_exports(m["base"])
        return self._public_exports(m)

    def module_imports(self, key) -> list:
        m = self._lookup_module(key)
        if m is None:
            return []
        self._ensure_imports(m["base"])
        return list(m.get("imports", []))

    def module_history(self, limit: int = 64) -> list:
        if limit <= 0:
            return []
        h = list(self._unloaded_modules)
        return h[-int(limit) :]

    def resolve(self, symbol: str, follow_forwarders: bool = True) -> int:
        """Translate `module!name`, `module!#<ordinal>`, or a bare `name`
        (searched across all loaded modules) to a virtual address. Returns
        0 when unresolved."""
        if not isinstance(symbol, str):
            raise TypeError("resolve() needs a string")
        if "!" in symbol:
            modname, sym = symbol.split("!", 1)
            m = self._lookup_module(modname)
            if m is None:
                return 0
            return self._resolve_in(m, sym, follow_forwarders, set())
        for m in sorted(self._modules.values(), key=lambda x: x["loaded_seq"] or 0):
            addr = self._resolve_in(m, symbol, follow_forwarders, set())
            if addr:
                return addr
        return 0

    def _resolve_in(self, m: dict, sym: str, follow_forwarders: bool, seen: set) -> int:
        base = int(m["base"])
        key = (base, sym)
        if key in seen:
            return 0
        seen.add(key)
        self._ensure_exports(base)
        target_ord = None
        if sym.startswith("#"):
            try:
                target_ord = int(sym[1:])
            except ValueError:
                target_ord = None
        for e in m.get("exports", []):
            match = (e.get("name") == sym) or (
                target_ord is not None and e.get("ordinal") == target_ord
            )
            if not match:
                continue
            if e.get("forwarder"):
                if not follow_forwarders:
                    return 0
                tgt = e["forwarder"]
                if "." in tgt:
                    tmod, tname = tgt.split(".", 1)
                    tm = self._lookup_module(tmod) or self._lookup_module(tmod + ".dll")
                    if tm is None:
                        return 0
                    return self._resolve_in(tm, tname, follow_forwarders, seen)
                return 0
            if e["rva"]:
                return base + e["rva"]
        return 0

    def addr_to_symbol(self, addr: int) -> dict | None:
        """Best-effort closest-export resolution for an address."""
        addr = int(addr)
        m = self._module_for_addr(addr)
        if m is None:
            return None
        rva = addr - int(m["base"])
        out = {"module": m["name"], "rva": rva}
        if "size" in m:
            out["in_module"] = rva < int(m["size"])
        self._ensure_exports(m["base"])
        best = None
        for e in m.get("exports", []):
            if e.get("forwarder"):
                continue
            r = e["rva"]
            if r and r <= rva and (best is None or r > best["rva"]):
                best = e
        if best is not None and best.get("name"):
            out.update(
                {
                    "name": best["name"],
                    "ordinal": best.get("ordinal"),
                    "offset": rva - best["rva"],
                }
            )
        return out

    def list_threads(self, enrich: bool = False, reconcile: bool = False) -> list:
        """Return the live thread table built from CREATE_THREAD/EXIT_THREAD
        events.

        Each row has: tid, start_address, is_main, created_at, created_seq,
        discovered, current.

        enrich=True   → also probe Rip + module:offset and a non-destructive
                        suspend_count (SuspendThread/ResumeThread pair). If
                        the debuggee is free-running, the thread is briefly
                        suspended for the read.
        reconcile=True → cross-check the tracked set against a Toolhelp32
                        snapshot. Any tid present in the OS but not in the
                        table is added with discovered=True.
        """
        if reconcile and self.pid:
            self._reconcile_threads()

        out = []
        for tid in sorted(self._threads):
            e = self._threads[tid]
            row = {
                "tid": tid,
                "start_address": e.get("start_address", 0),
                "is_main": bool(e.get("is_main")),
                "created_at": e.get("created_at"),
                "created_seq": e.get("created_seq"),
                "discovered": bool(e.get("discovered")),
                "current": tid == self._cur_tid,
            }
            if e.get("start_address"):
                sym = self.addr_to_symbol(e["start_address"])
                if sym is not None:
                    row["start_module"] = sym.get("module")
                    row["start_offset"] = sym.get("rva")
                    if "name" in sym:
                        row["start_symbol"] = sym["name"]
                        row["start_symbol_offset"] = sym.get("offset")
            if enrich:
                row.update(self._probe_thread(tid))
            out.append(row)
        return out

    def thread_info(self, tid: int, enrich: bool = False) -> dict | None:
        """Return one tracked thread's row, or None if the tid is unknown."""
        if tid not in self._threads:
            return None
        rows = self.list_threads(enrich=enrich)
        for r in rows:
            if r["tid"] == tid:
                return r
        return None

    def thread_history(self, limit: int = 64) -> list:
        """Return up to `limit` most-recent EXIT_THREAD entries (newest last)."""
        if limit <= 0:
            return []
        h = list(self._exited_threads)
        return h[-int(limit) :]

    def _probe_thread(self, tid: int) -> dict:
        """Read PC + suspend_count for a tracked tid. Briefly suspends the
        thread so the snapshot is coherent if the debuggee is running."""
        h = self._open_thread(tid)
        prev = k32.SuspendThread(h)
        try:
            ctx = self._raw_get_context(tid)
            rip = int(getattr(ctx, self._pc_field()))
        finally:
            k32.ResumeThread(h)
        # SuspendThread returns the previous suspend count (0 means it was
        # running before our probe).
        suspend_count = int(prev) if prev != 0xFFFFFFFF else None
        out: dict = {"rip": rip, "suspend_count": suspend_count}
        sym = self.addr_to_symbol(rip)
        if sym is not None:
            out["rip_module"] = sym.get("module")
            out["rip_offset"] = sym.get("rva")
            if "name" in sym:
                out["rip_symbol"] = sym["name"]
                out["rip_symbol_offset"] = sym.get("offset")
        return out

    def _module_for_addr(self, addr: int) -> dict | None:
        """Resolve `addr` to a tracked module. When SizeOfImage is known we
        use [base, base+size); otherwise fall back to the largest base ≤ addr."""
        if not addr or not self._modules:
            return None
        # Prefer an exact range hit (uses size).
        for m in self._modules.values():
            b = int(m.get("base", 0))
            sz = int(m.get("size", 0))
            if b and sz and b <= addr < b + sz:
                return m
        # Fallback: largest base ≤ addr (may overshoot; caller should sanity-
        # check via "in_module" when sizes weren't available).
        best = None
        for m in self._modules.values():
            b = int(m.get("base", 0))
            if b and b <= addr and (best is None or b > best["base"]):
                best = m
        return best

    # ---------------- thread suspend / resume ----------------
    def suspend_thread(self, tid: int) -> dict:
        """SuspendThread(tid). Returns the previous suspend count and the new
        one (prev+1 unless the call failed). Tracks the tid via _open_thread
        so any tid passed in becomes part of the live table."""
        h = self._open_thread(int(tid))
        prev = k32.SuspendThread(h)
        if prev == 0xFFFFFFFF:
            raise _winerror("SuspendThread")
        return {"tid": int(tid), "prev_count": int(prev), "count": int(prev) + 1}

    def resume_thread(self, tid: int) -> dict:
        """ResumeThread(tid). Returns the previous suspend count; the thread
        actually runs again when count drops to 0."""
        h = self._open_thread(int(tid))
        prev = k32.ResumeThread(h)
        if prev == 0xFFFFFFFF:
            raise _winerror("ResumeThread")
        new = max(0, int(prev) - 1)
        return {"tid": int(tid), "prev_count": int(prev), "count": new}

    def suspend_all(self, exclude: list | None = None) -> list:
        """Suspend every tracked thread (skipping any tid in `exclude`).
        Returns one entry per thread with prev_count/count, or an `error`
        string if SuspendThread failed for that tid."""
        skip = set(int(t) for t in (exclude or []))
        out = []
        for tid in sorted(self._threads):
            if tid in skip:
                continue
            try:
                out.append(self.suspend_thread(tid))
            except OSError as e:
                out.append({"tid": tid, "error": str(e)})
        return out

    def resume_all(self, exclude: list | None = None) -> list:
        skip = set(int(t) for t in (exclude or []))
        out = []
        for tid in sorted(self._threads):
            if tid in skip:
                continue
            try:
                out.append(self.resume_thread(tid))
            except OSError as e:
                out.append({"tid": tid, "error": str(e)})
        return out

    def current_thread(self) -> int:
        return self._cur_tid

    def event_info(self) -> dict | None:
        return self._last_event

    def version(self) -> dict:
        """Build identifier for the loaded dbg plugin module. Useful as a
        smoke check after `upy.rrepl reload` to confirm the new code is
        live. The build id is the short git SHA of the package's source
        tree when available, falling back to the package version then to
        ``"unknown"``."""
        return _plugin_build_info()

    # ---------------- helpers ----------------
    def _is_handled(self) -> bool:
        ev = self._last_event or {}
        if ev.get("event") != "EXCEPTION":
            return True
        code = ev.get("code")
        if code in (
            EXCEPTION_BREAKPOINT,
            EXCEPTION_SINGLE_STEP,
            STATUS_WX86_BREAKPOINT,
            STATUS_WX86_SINGLE_STEP,
        ):
            return True
        # User-set BP we already restored is handled too.
        return False

    def _is_internal(self, ev: dict) -> bool:
        if ev.get("event") in (
            "LOAD_DLL",
            "UNLOAD_DLL",
            "CREATE_THREAD",
            "EXIT_THREAD",
            "OUTPUT_DEBUG_STRING",
        ):
            return True
        if ev.get("loader_bp"):
            return True
        if ev.get("_internal_step"):
            return True
        return False

    def _image_path(self, hFile: int, base: int) -> str:
        if not self.h_process or not base:
            return ""
        buf = (c_wchar * 1024)()
        n = psapi.GetModuleFileNameExW(self.h_process, base, buf, 1024)
        if n:
            return buf[:n]
        n = psapi.GetMappedFileNameW(self.h_process, base, buf, 1024)
        if n:
            return _device_to_dos_path(buf[:n])
        return ""

    def _read_debug_string(self, ods: OUTPUT_DEBUG_STRING_INFO) -> str:
        n = ods.nDebugStringLength
        if not n or not ods.lpDebugStringData:
            return ""
        try:
            data = bytes.fromhex(self.read_mem(ods.lpDebugStringData, n)["hex"])
        except Exception:
            return ""
        if ods.fUnicode:
            return data.decode("utf-16-le", errors="replace").rstrip("\x00")
        return data.decode("latin-1", errors="replace").rstrip("\x00")


def _basename(p: str) -> str:
    if not p:
        return ""
    return p.replace("\\", "/").rsplit("/", 1)[-1]


_DEV_TO_DOS: dict[str, str] | None = None


def _device_to_dos_path(p: str) -> str:
    """Translate \\Device\\HarddiskVolumeN\\... to C:\\... using QueryDosDeviceW."""
    global _DEV_TO_DOS
    if _DEV_TO_DOS is None:
        _DEV_TO_DOS = {}
        buf = (c_wchar * 1024)()
        for drive in (chr(c) for c in range(ord("A"), ord("Z") + 1)):
            n = k32.QueryDosDeviceW(f"{drive}:", buf, 1024)
            if n:
                _DEV_TO_DOS[buf.value] = f"{drive}:"
    for dev, dos in _DEV_TO_DOS.items():
        if p.startswith(dev + "\\"):
            return dos + p[len(dev) :]
    return p


def _now_ms() -> int:
    import time

    return int(time.monotonic() * 1000)


# ---------------------------------------------------------------------------
# Thread-pinning wrapper
# ---------------------------------------------------------------------------


def _dbg_worker_loop(q: "queue.Queue", impl: "_DbgImpl"):
    """Worker loop for a Debugger. Deliberately a module-level function
    (not a bound method) so the OS thread does NOT keep the Debugger
    wrapper alive — that lets the wrapper be collected when a session
    drops its `DBG`, which in turn fires Debugger.__del__ -> the None
    sentinel below -> this loop's cleanup. The loop holds `impl` so the
    debuggee stays usable while running, and releases it on exit."""
    try:
        while True:
            item = q.get()
            if item is None:
                return
            fn, args, kw, reply = item
            try:
                reply.put(("ok", fn(*args, **kw)))
            except BaseException as e:
                import traceback

                reply.put(("err", (e, traceback.format_exc())))
    finally:
        # Release the debuggee + handles when the worker stops. Kill a
        # process we spawned; only detach one we attached to.
        try:
            if impl.spawned:
                impl.kill()
            elif impl.attached:
                impl.detach()
        except Exception:
            pass


class Debugger:
    """Public-facing debugger. All operations run on a dedicated worker thread
    so that Win32 Debug API thread-affinity is preserved across rrepl calls."""

    _PROXY_METHODS = (
        "spawn",
        "attach",
        "detach",
        "kill",
        "wait",
        "continue_event",
        "cont",
        "step",
        "step_over",
        "set_bp",
        "clear_bp",
        "list_bps",
        "set_hw_bp",
        "clear_hw_bp",
        "list_hw_bps",
        "get_regs",
        "set_reg",
        "read_mem",
        "write_mem",
        "read_int",
        "read_u8",
        "read_u16",
        "read_u32",
        "read_u64",
        "read_i8",
        "read_i16",
        "read_i32",
        "read_i64",
        "read_ptr",
        "read_f32",
        "read_f64",
        "read_cstr",
        "read_wstr",
        "write_int",
        "write_u8",
        "write_u16",
        "write_u32",
        "write_u64",
        "write_i8",
        "write_i16",
        "write_i32",
        "write_i64",
        "write_ptr",
        "write_f32",
        "write_f64",
        "write_cstr",
        "write_wstr",
        "assemble",
        "write_asm",
        "disasm",
        "entry_points",
        "break_on_entry_points",
        "list_modules",
        "module_info",
        "module_exports",
        "module_imports",
        "module_history",
        "resolve",
        "addr_to_symbol",
        "list_threads",
        "thread_info",
        "thread_history",
        "suspend_thread",
        "resume_thread",
        "suspend_all",
        "resume_all",
        "current_thread",
        "event_info",
        "version",
    )

    def __init__(self):
        self._impl = _DbgImpl()
        self._q: "queue.Queue" = queue.Queue()
        self._closed = False
        # NOTE: target is the module-level _dbg_worker_loop, NOT a bound
        # method — see its docstring. This is what lets a dropped DBG be
        # garbage-collected so __del__ can stop the worker.
        self._t = threading.Thread(
            target=_dbg_worker_loop,
            args=(self._q, self._impl),
            name="dbg-worker",
            daemon=True,
        )
        self._t.start()

    def close(self, join_timeout: float = 5.0):
        """Stop the worker thread and release the debuggee (kill if we
        spawned it, detach if we attached). Idempotent; safe to call from
        __del__ or explicitly."""
        if getattr(self, "_closed", True):
            return
        self._closed = True
        try:
            self._q.put(None)
        except Exception:
            return
        t = getattr(self, "_t", None)
        if t is not None and t.is_alive():
            try:
                t.join(timeout=join_timeout)
            except Exception:
                pass

    def __del__(self):
        # Backstop for the common path (a session dropping DBG). Guarded
        # because interpreter-shutdown ordering can make globals unavailable.
        try:
            self.close(join_timeout=2.0)
        except Exception:
            pass

    def _post(self, fn, *args, **kw):
        reply: "queue.Queue" = queue.Queue()
        self._q.put((fn, args, kw, reply))
        kind, val = reply.get()
        if kind == "err":
            exc, tb = val
            # Re-raise with original traceback string for visibility in stderr.
            raise type(exc)(f"{exc}\n--- worker traceback ---\n{tb}")
        return val

    # convenience pass-through for read-only state inspection
    @property
    def attached(self) -> bool:
        return self._impl.attached or self._impl.spawned

    @property
    def pid(self) -> int:
        return self._impl.pid

    @property
    def _modules(self):
        return self._impl._modules

    @property
    def _bps(self):
        return self._impl._bps

    @property
    def spawned(self) -> bool:
        return self._impl.spawned

    @property
    def wow64(self) -> bool:
        """True iff the debuggee is a 32-bit (WOW64) guest."""
        return self._impl._wow64


def _make_proxy(name: str):
    def _proxy(self, *args, **kw):
        return self._post(getattr(self._impl, name), *args, **kw)

    _proxy.__name__ = name
    _proxy.__qualname__ = f"Debugger.{name}"
    return _proxy


for _n in Debugger._PROXY_METHODS:
    setattr(Debugger, _n, _make_proxy(_n))
del _n
