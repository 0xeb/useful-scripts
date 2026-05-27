"""HTTP JSON Python REPL server."""

import contextlib
import io
import threading
import traceback

from flask import Flask, jsonify, request

from .protocol import (
    API_PREFIX,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SESSION,
    normalize_session_name,
    validation_error,
)

_STDIO_LOCK = threading.RLock()


class ReplSession:
    """A persistent Python execution namespace guarded by a lock."""

    def __init__(self, name):
        self.name = normalize_session_name(name)
        self.lock = threading.RLock()
        self.globals = {
            "__name__": "rrepl_session_{}".format(self.name.replace(" ", "_")),
            "__package__": None,
        }

    def execute(self, code):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with self.lock:
            try:
                compiled = compile(code, "<rrepl:{}>".format(self.name), "exec")
                # stdout/stderr redirection is process-global, so serialize it.
                with _STDIO_LOCK:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        exec(compiled, self.globals, self.globals)
                return {
                    "ok": True,
                    "session": self.name,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                    "error": None,
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "session": self.name,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                }


class ReplManager:
    """Owns named REPL sessions."""

    def __init__(self):
        self._lock = threading.RLock()
        self._sessions = {DEFAULT_SESSION: ReplSession(DEFAULT_SESSION)}

    def get_session(self, name=None):
        session_name = normalize_session_name(name)
        with self._lock:
            session = self._sessions.get(session_name)
            if session is None:
                session = ReplSession(session_name)
                self._sessions[session_name] = session
            return session

    def list_sessions(self):
        with self._lock:
            return sorted(self._sessions)

    def execute(self, code, session=None):
        if not isinstance(code, str):
            raise TypeError("code must be a string")
        return self.get_session(session).execute(code)

    def reset(self, name=None):
        session_name = normalize_session_name(name)
        with self._lock:
            self._sessions[session_name] = ReplSession(session_name)
        return session_name

    def delete(self, name):
        session_name = normalize_session_name(name)
        with self._lock:
            existed = session_name in self._sessions
            if existed:
                del self._sessions[session_name]
            if not self._sessions:
                self._sessions[DEFAULT_SESSION] = ReplSession(DEFAULT_SESSION)
        return existed


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, validation_error("request body must be a JSON object")
    return data, None


def _session_from_data(data):
    raw_session = data.get("session", DEFAULT_SESSION)
    try:
        return normalize_session_name(raw_session), None
    except TypeError as exc:
        return DEFAULT_SESSION, validation_error(str(exc))


def create_app(manager=None):
    """Create a Flask app for the rrepl HTTP API."""
    app = Flask(__name__)
    repl_manager = manager or ReplManager()
    app.config["rrepl_manager"] = repl_manager

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"ok": True, "service": "rrepl"})

    @app.route(API_PREFIX + "/sessions", methods=["GET"])
    def sessions():
        names = repl_manager.list_sessions()
        return jsonify(
            {
                "ok": True,
                "count": len(names),
                "sessions": [{"name": name} for name in names],
            }
        )

    @app.route(API_PREFIX + "/exec", methods=["POST"])
    def execute():
        data, error = _json_body()
        if error:
            return jsonify(error), 400

        code = data.get("code")
        if not isinstance(code, str):
            return jsonify(
                validation_error("code must be a string", data.get("session"))
            ), 400

        session, error = _session_from_data(data)
        if error:
            return jsonify(error), 400

        return jsonify(repl_manager.execute(code, session))

    @app.route(API_PREFIX + "/reset", methods=["POST"])
    def reset():
        data, error = _json_body()
        if error:
            return jsonify(error), 400

        session, error = _session_from_data(data)
        if error:
            return jsonify(error), 400

        repl_manager.reset(session)
        return jsonify({"ok": True, "session": session})

    @app.route(API_PREFIX + "/sessions/<path:name>", methods=["DELETE"])
    def delete_session(name):
        session = normalize_session_name(name)
        existed = repl_manager.delete(session)
        return jsonify({"ok": True, "session": session, "deleted": existed})

    @app.route(API_PREFIX + "/reload", methods=["POST"])
    def reload_modules():
        """Drop a set of import-name prefixes from sys.modules, re-run any
        editable-install finders, invalidate import caches, and (by default)
        reset all rrepl sessions so any cached references to old classes
        are dropped. The running rrepl server module itself is preserved.

        Body (all optional):
            {"prefixes": ["upyscripts.rrepl.plugins"],   # default
             "reset_sessions": true,                      # default
             "reinstall_finders": true}                   # default

        This is the deploy-loop entry point: run `git pull` (or rsync)
        against the source repo, then POST /api/v1/reload to pick up the
        new code without restarting the rrepl process.
        """
        # A truly absent body (no bytes) means "default reload". ANY bytes
        # present — including whitespace-only, which is not valid JSON —
        # must parse to a JSON object, else 400. We must NOT silently
        # coerce [] / false / "" / "   " / malformed JSON to {} and then
        # perform a default reload (which drops modules + resets sessions)
        # on a bad request.
        if request.data:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify(validation_error("request body must be a JSON object")), 400
        else:
            data = {}

        prefixes = data.get("prefixes", ["upyscripts.rrepl.plugins"])
        if not isinstance(prefixes, list) or not all(isinstance(p, str) for p in prefixes):
            return jsonify(validation_error("prefixes must be a list of strings")), 400
        reset_sessions = bool(data.get("reset_sessions", True))
        reinstall_finders = bool(data.get("reinstall_finders", True))

        result = _do_reload(repl_manager, prefixes, reset_sessions, reinstall_finders)
        return jsonify(result)

    return app


def _do_reload(repl_manager, prefixes, reset_sessions, reinstall_finders):
    import importlib
    import sys

    # Never drop the rrepl server itself — we are running inside it.
    PROTECTED = {
        "upyscripts.rrepl",
        "upyscripts.rrepl.server",
        "upyscripts.rrepl.protocol",
        "upyscripts.rrepl.cli",
        "upyscripts.rrepl.client",
        "upyscripts",  # parent — re-imports cheap
    }
    targets = []
    for name in list(sys.modules):
        if name in PROTECTED:
            continue
        for p in prefixes:
            if name == p or name.startswith(p + "."):
                targets.append(name)
                break
    for name in targets:
        del sys.modules[name]

    finders_installed = []
    if reinstall_finders:
        # Drop any currently-loaded editable finders so the next import
        # re-resolves through the freshly-evaluated .pth-installed finders.
        for name in list(sys.modules):
            if name.startswith("__editable__") and name.endswith("_finder"):
                del sys.modules[name]
        for finder_mod in _discover_editable_finders():
            try:
                m = importlib.import_module(finder_mod)
                if hasattr(m, "install"):
                    m.install()
                    finders_installed.append(finder_mod)
            except ImportError:
                pass

    importlib.invalidate_caches()

    sessions_reset = 0
    if reset_sessions and repl_manager is not None:
        for name in list(repl_manager.list_sessions()):
            repl_manager.reset(name)
            sessions_reset += 1

    return {
        "ok": True,
        "dropped": sorted(targets),
        "finders_installed": finders_installed,
        "sessions_reset": sessions_reset,
    }


def _discover_editable_finders():
    """Walk every directory pip might install into and yield any
    ``__editable___*_finder`` module names found there. Each match is the
    importable module name (no .py suffix). Survives package version bumps
    because we're matching the file pattern, not a hardcoded version."""
    import glob
    import os
    import site

    seen = set()
    candidates = []
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        user = site.getusersitepackages()
        if user:
            candidates.append(user)
    except Exception:
        pass
    # Also honour anything explicitly on sys.path that looks like a
    # site-packages dir; covers virtualenv layouts where getsitepackages
    # may not include all relevant directories on every platform.
    import sys as _sys
    for p in _sys.path:
        if p and "site-packages" in p:
            candidates.append(p)

    for d in candidates:
        if not d or not os.path.isdir(d):
            continue
        for hit in glob.glob(os.path.join(d, "__editable___*_finder.py")):
            mod_name = os.path.splitext(os.path.basename(hit))[0]
            if mod_name not in seen:
                seen.add(mod_name)
                yield mod_name


def run_server(host=DEFAULT_HOST, port=DEFAULT_PORT, debug=False):
    """Run the development REPL server."""
    app = create_app()
    print("rrepl executes arbitrary Python code. Use only on trusted networks.")
    print("Serving on http://{}:{}".format(host, port))
    app.run(host=host, port=port, debug=debug)
