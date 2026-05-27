"""Plugin scaffold for upy.rrepl.

A plugin is a regular Python sub-package under ``upyscripts.rrepl.plugins``
whose ``__init__.py`` exposes a ``MANIFEST`` dict and (typically) a
client-side wrapper class deriving from :class:`PluginBase`.

Loading is **client-driven and lazy**: the plugin's server-side classes
live as a normal Python module on the rrepl host (installed alongside
``upyscripts``), but they are not imported into any rrepl session at
server startup. The client sends an ``import`` line into its rrepl
session on first use; the singleton (e.g. ``DBG``) is created in that
session's globals and persists until the session is reset or deleted.

This keeps the rrepl HTTP surface unchanged — every plugin operation is
just one or more ``POST /api/v1/exec`` calls.
"""

from __future__ import annotations

import json
from importlib import import_module
from typing import Any, Optional

try:
    from importlib.metadata import entry_points  # py3.10+
except ImportError:  # pragma: no cover - py3.7-3.9 fallback
    from importlib_metadata import entry_points  # type: ignore

from ..client import RReplClient
from ..protocol import DEFAULT_SESSION


_RESULT_MARKER = "__R__"

ENTRY_POINT_GROUP = "upy.rrepl.plugins"


class PluginBase:
    """Lazy, session-bound base class for rrepl plugin clients.

    Subclasses must set:
      * ``_LOADED_KEY`` — the global name to probe in the rrepl session
        (e.g. ``"DBG"``); presence indicates the plugin is already loaded.
      * ``_BOOTSTRAP`` — the snippet that loads the plugin into the
        session globals (e.g. an ``import`` line plus singleton
        creation).

    Each public method on a subclass typically calls :meth:`_call` to
    invoke a method on the in-session singleton and parse the result.
    """

    _LOADED_KEY: str = ""
    _BOOTSTRAP: str = ""

    def __init__(
        self,
        url: str = "http://127.0.0.1:8765",
        session: str = DEFAULT_SESSION,
        timeout: float = 30.0,
        client: Optional[RReplClient] = None,
    ):
        self.session = session
        self.cli = client if client is not None else RReplClient(url, timeout=timeout)
        self._loaded = False

    # ------------- bootstrap ------------- #
    def is_loaded(self) -> bool:
        """Return True if the plugin's loaded-key is already in the session."""
        if self._loaded:
            return True
        probe = (
            "import json as _j\n"
            f"print({_RESULT_MARKER!r} + _j.dumps({self._LOADED_KEY!r} in globals() "
            f"and globals().get({self._LOADED_KEY!r}) is not None))"
        )
        present = self._exec_marker(probe)
        if present:
            self._loaded = True
        return self._loaded

    def ensure_loaded(self) -> None:
        """Run the plugin bootstrap if it hasn't already loaded into the session."""
        if not self._LOADED_KEY or not self._BOOTSTRAP:
            raise RuntimeError(
                f"{type(self).__name__} subclass must set _LOADED_KEY and _BOOTSTRAP"
            )
        if self.is_loaded():
            return
        self.cli.exec(self._BOOTSTRAP, session=self.session, raise_on_error=True)
        self._loaded = True

    def reset_plugin(self) -> None:
        """Forget the in-session singleton so the next call re-bootstraps."""
        if not self._LOADED_KEY:
            return
        code = (
            "try:\n"
            f"    del {self._LOADED_KEY}\n"
            "except NameError:\n"
            "    pass\n"
        )
        self.cli.exec(code, session=self.session)
        self._loaded = False

    # ------------- exec helpers ------------- #
    def _exec_marker(self, code: str) -> Any:
        """Run code that prints ``__R__<json>`` and return the parsed value."""
        result = self.cli.exec(code, session=self.session, raise_on_error=True)
        stdout = result.get("stdout", "") or ""
        for line in reversed(stdout.splitlines()):
            if line.startswith(_RESULT_MARKER):
                return json.loads(line[len(_RESULT_MARKER):])
        raise RuntimeError(
            "no '" + _RESULT_MARKER + "' marker in stdout; "
            "got stdout=" + repr(stdout) + " stderr=" + repr(result.get("stderr", ""))
        )

    def _call(self, method: str, *args, **kwargs) -> Any:
        """Invoke ``<LOADED_KEY>.<method>(*args, **kwargs)`` in the session."""
        self.ensure_loaded()
        code = (
            "import json as _j\n"
            f"_args = _j.loads({json.dumps(json.dumps(list(args)))})\n"
            f"_kw   = _j.loads({json.dumps(json.dumps(kwargs))})\n"
            f"_r = {self._LOADED_KEY}.{method}(*_args, **_kw)\n"
            f"print({_RESULT_MARKER!r} + _j.dumps(_r, default=str))"
        )
        return self._exec_marker(code)

    def exec_inline(self, code: str) -> dict:
        """Pass-through to ``RReplClient.exec`` on this plugin's session.

        Useful when you need to run ad-hoc Python in the same session as
        the plugin without going through a `_call` proxy.
        """
        return self.cli.exec(code, session=self.session)


# ----------------- discovery ----------------- #

def list_plugins() -> list:
    """Return ``[{name, manifest, module}]`` for installed rrepl plugins.

    Discovery uses the ``upy.rrepl.plugins`` entry-points group, populated
    by plugin packages via ``[project.entry-points."upy.rrepl.plugins"]``
    in ``pyproject.toml``.
    """
    found = []
    eps = entry_points()
    if hasattr(eps, "select"):  # py3.10+
        eps = eps.select(group=ENTRY_POINT_GROUP)
    else:  # py3.7-3.9
        eps = eps.get(ENTRY_POINT_GROUP, [])
    for ep in eps:
        try:
            mod = import_module(ep.value)
        except Exception as exc:  # pragma: no cover - defensive
            found.append({"name": ep.name, "error": str(exc), "module": ep.value})
            continue
        manifest = getattr(mod, "MANIFEST", {})
        found.append({"name": ep.name, "manifest": manifest, "module": ep.value})
    return found


def load_manifest(name: str) -> Optional[dict]:
    """Return the MANIFEST dict for an installed plugin by name (or None)."""
    for entry in list_plugins():
        if entry.get("name") == name:
            return entry.get("manifest")
    return None


__all__ = ["PluginBase", "list_plugins", "load_manifest", "ENTRY_POINT_GROUP"]
