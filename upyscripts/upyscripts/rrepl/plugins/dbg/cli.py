"""Tiny gdb-flavour REPL for the upy.rrepl ``dbg`` plugin.

Run as a console script:  ``upy.rrepl-dbg``
Or as a module:           ``python -m upyscripts.rrepl.plugins.dbg.cli``

Commands (one-letter forms in parens):
  health                          health-check rrepl
  spawn <path>                    launch <path> under debug
  attach <pid>                    attach to a running pid
  detach                          detach (leave alive)
  kill                            terminate the debuggee
  g [ms]            (cont)        continue, default 5000 ms budget
  s [n]             (step)        single-step n times
  p [n]             (over)        step over n times
  bp <addr>                       set software breakpoint
  bc <addr>                       clear software breakpoint
  bl                              list breakpoints
  r                 (regs)        dump regs
  set <reg> <val>                 set a register (e.g. 'set rip 0x140...')
  u [addr] [n]      (disasm)      disassemble n insns at addr or RIP
  db <addr> [n]                   read+hex-dump n bytes
  eb <addr> <hex...>              write hex bytes (live patch)
  ea <addr> "<asm>"               assemble mnemonics + write
  asm "<asm>" [addr]              assemble only (no write)
  lm                              list modules
  mi <name|base>                  module info
  t                               list threads
  e                               last event info
  ep                              entry points (TLS callbacks + EXE entry)
  guide                           print the canonical client/agent guide
  q                               quit (debuggee continues unless killed)

Options:
  --url URL        rrepl server URL (default http://127.0.0.1:8765)
  --session NAME   session name (default 'dbg')
  --print-guide    print the GUIDE.md path and exit
"""
from __future__ import annotations

import argparse
import shlex
import sys

from .client import Dbg, fmt_disasm, fmt_modules, fmt_regs


HELP = __doc__


def _hex(s: str) -> int:
    return int(s, 0)


def _hexdump(data: bytes, base: int) -> None:
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"{base + off:#018x}  {hexs:<48}  {text}")


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="upy.rrepl-dbg",
        description="Interactive gdb-flavour REPL for the upy.rrepl dbg plugin.",
    )
    p.add_argument("--url", default="http://127.0.0.1:8765",
                   help="rrepl server URL (default: %(default)s)")
    p.add_argument("--session", default="dbg",
                   help="rrepl session name (default: %(default)s)")
    p.add_argument("--print-guide", action="store_true",
                   help="print the path of GUIDE.md and exit")
    return p


def main(argv=None) -> int:
    args = _build_argparser().parse_args(argv)

    if args.print_guide:
        from . import GUIDE_PATH
        print(GUIDE_PATH)
        return 0

    d = Dbg(url=args.url, session=args.session)
    try:
        print("rrepl:", d.cli.health())
    except Exception as e:
        print(f"could not reach rrepl at {args.url}: {e}", file=sys.stderr)
        return 2
    print("type 'help' for commands, 'q' to quit.")

    while True:
        try:
            line = input("dbg> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        try:
            parts = shlex.split(line)
        except ValueError as e:
            print("parse error:", e)
            continue
        cmd, *cargs = parts

        try:
            if cmd in ("q", "quit", "exit"):
                return 0
            elif cmd in ("help", "?"):
                print(HELP)
            elif cmd == "health":
                print(d.cli.health())
            elif cmd == "guide":
                print(d.guide())
            elif cmd == "spawn":
                print(d.spawn(cargs[0]))
            elif cmd == "attach":
                print(d.attach(int(cargs[0])))
            elif cmd == "detach":
                print(d.detach())
            elif cmd == "kill":
                print(d.kill())
            elif cmd in ("g", "cont"):
                ms = int(cargs[0]) if cargs else 5000
                print(d.cont(timeout_ms=ms))
            elif cmd in ("s", "step"):
                n = int(cargs[0]) if cargs else 1
                print(d.step(n))
                print(fmt_disasm(d.disasm(count=1)))
            elif cmd in ("p", "over"):
                n = int(cargs[0]) if cargs else 1
                last = None
                for _ in range(n):
                    last = d.step_over()
                print(last)
                print(fmt_disasm(d.disasm(count=1)))
            elif cmd == "bp":
                print(d.set_bp(_hex(cargs[0])))
            elif cmd == "bc":
                print(d.clear_bp(_hex(cargs[0])))
            elif cmd == "bl":
                for bp in d.list_bps():
                    print(f"  {bp['addr']:#018x}  orig=0x{bp['orig']:02x}")
            elif cmd in ("r", "regs"):
                print(fmt_regs(d.get_regs()))
            elif cmd == "set":
                print(d.set_reg(cargs[0], _hex(cargs[1])))
            elif cmd in ("u", "disasm"):
                addr = _hex(cargs[0]) if cargs else None
                n = int(cargs[1]) if len(cargs) > 1 else 12
                print(fmt_disasm(d.disasm(addr=addr, count=n)))
            elif cmd == "db":
                addr = _hex(cargs[0])
                n = int(cargs[1]) if len(cargs) > 1 else 64
                data = bytes.fromhex(d.read_mem(addr, n)["hex"])
                _hexdump(data, addr)
            elif cmd == "eb":
                addr = _hex(cargs[0])
                hexs = "".join(cargs[1:]).replace(",", "").replace("0x", "")
                print(d.write_mem(addr, hexs))
            elif cmd == "ea":
                addr = _hex(cargs[0])
                print(d.write_asm(addr, cargs[1]))
            elif cmd == "asm":
                addr = _hex(cargs[1]) if len(cargs) > 1 else 0
                print(d.assemble(cargs[0], addr))
            elif cmd == "lm":
                print(fmt_modules(d.list_modules()))
            elif cmd == "mi":
                key = cargs[0]
                if key.startswith("0x"):
                    key = int(key, 16)
                print(d.module_info(key))
            elif cmd == "t":
                for t in d.list_threads():
                    cur = " *" if t["current"] else "  "
                    print(f"{cur} tid {t['tid']}")
            elif cmd == "e":
                print(d.event_info())
            elif cmd == "ep":
                for e in d.entry_points():
                    print(f"  [{e.get('index', '-')}] {e['kind']:5} "
                          f"{e['addr']:#018x}   {e['source']}")
            else:
                print(f"unknown command: {cmd!r}  (try 'help')")
        except Exception as e:
            print("error:", e)


if __name__ == "__main__":
    raise SystemExit(main())
