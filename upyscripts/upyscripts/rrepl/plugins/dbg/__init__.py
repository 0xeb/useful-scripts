"""upy.rrepl ``dbg`` plugin — Windows x64 user-mode debugger.

The server-side debugger module (``.server``) is imported lazily on
first client call; it is Windows-only and not loaded automatically on
plugin import. The ``Dbg`` client class (re-exported here) is
cross-platform — it speaks rrepl HTTP and constructs Python snippets
the server runs.

See ``GUIDE.md`` (alongside this file) for the full client/agent guide.
"""

from __future__ import annotations

import pathlib

from .client import Dbg, fmt_disasm, fmt_modules, fmt_regs

GUIDE_PATH = pathlib.Path(__file__).resolve().parent / "GUIDE.md"

MANIFEST = {
    "name": "dbg",
    "version": "0.1.0",
    "description": "Windows x64 user-mode debugger driven over upy.rrepl.",
    "platform": "win32",
    "server_requires": ["capstone>=5.0", "keystone-engine>=0.9", "pefile>=2023.2.7"],
    "loaded_key": "DBG",
    "guide": str(GUIDE_PATH),
    "client_class": "upyscripts.rrepl.plugins.dbg.client:Dbg",
    "server_module": "upyscripts.rrepl.plugins.dbg.server",
}

__all__ = ["MANIFEST", "GUIDE_PATH", "Dbg", "fmt_regs", "fmt_disasm", "fmt_modules"]
