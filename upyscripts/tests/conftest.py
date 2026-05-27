"""Shared test fixtures.

`rrepl_url` resolves the URL of a running rrepl server in this order:

  1. ``RREPL_URL`` environment variable
  2. ``.claude/rrepl.json`` (walked upward from cwd; gitignored, local-only)
  3. otherwise: tests that depend on the fixture are skipped

`rrepl_client` returns a connected ``RReplClient`` against that URL or
skips. Tests that touch the dbg plugin should also depend on
``rrepl_dbg_available`` which additionally verifies the host is Windows.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest


def _find_claude_config() -> dict | None:
    """Walk up from cwd looking for .claude/rrepl.json. Returns parsed
    contents, or None if none found / unreadable."""
    cur = pathlib.Path(os.getcwd()).resolve()
    for d in [cur, *cur.parents]:
        candidate = d / ".claude" / "rrepl.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
    return None


@pytest.fixture(scope="session")
def rrepl_url() -> str:
    """URL of a reachable rrepl server. Skips the test if unconfigured."""
    url = os.environ.get("RREPL_URL")
    if not url:
        cfg = _find_claude_config()
        if cfg:
            url = cfg.get("url")
    if not url:
        pytest.skip(
            "rrepl URL not configured (set RREPL_URL or create "
            ".claude/rrepl.json with a 'url' key)"
        )
    return url.rstrip("/")


@pytest.fixture(scope="session")
def rrepl_client(rrepl_url):
    """RReplClient against ``rrepl_url``. Skips if the server isn't reachable."""
    from upyscripts.rrepl.client import RReplClient, RReplError

    # Debugger operations legitimately run multi-second server-side loops
    # (cont() pumps with its own timeout budget), so give the HTTP client
    # generous headroom above any single exec's worst-case wall time.
    client = RReplClient(rrepl_url, timeout=60)
    try:
        client.health()
    except RReplError as exc:  # network / timeout / non-2xx
        pytest.skip(f"rrepl server at {rrepl_url} not reachable: {exc}")
    return client


@pytest.fixture(scope="session")
def rrepl_dbg_available(rrepl_client) -> bool:
    """True if the remote rrepl host is Windows (the dbg plugin is
    Windows-only). Otherwise skips.

    Also performs one POST /api/v1/reload at the start of the pytest
    session so accumulated daemon worker threads / cached imports from
    prior runs don't bleed into the new run. Best-effort: a 404 (older
    server without the endpoint) is swallowed."""
    payload = rrepl_client.exec("import sys; print(sys.platform)")
    if not payload.get("ok"):
        pytest.skip("rrepl host unable to report sys.platform")
    plat = payload.get("stdout", "").strip()
    if plat != "win32":
        pytest.skip(f"rrepl host is {plat!r}, dbg plugin requires win32")
    # Reset prior-run sessions. With deterministic worker shutdown, this
    # also tears down any Debugger a previous run left behind (killing
    # spawned debuggees, detaching attached ones). We deliberately do NOT
    # `taskkill /IM notepad.exe` — that would kill unrelated Notepad
    # windows on a shared host. Each test cleans up its own debuggee by
    # PID in the dbg_session teardown.
    try:
        rrepl_client.reload()
    except Exception:
        pass
    return True
