"""Unit tests for the /api/v1/reload endpoint and helper.

These run in-process — no remote rrepl needed. They cover:

  * the dropped/protected/sessions_reset bookkeeping
  * default vs. explicit prefixes
  * malformed bodies
"""

from __future__ import annotations

import sys
import types

import pytest

from upyscripts.rrepl.server import (
    ReplManager,
    _discover_editable_finders,
    _do_reload,
    create_app,
)


def _make_fake_pkg(name: str) -> None:
    """Inject a fake module into sys.modules so the reload path has
    something to drop. Removed via _do_reload's drop logic, not by us."""
    mod = types.ModuleType(name)
    mod.__file__ = f"<test:{name}>"
    sys.modules[name] = mod


def test_do_reload_drops_only_matching_prefixes_and_keeps_protected():
    _make_fake_pkg("upyscripts.rrepl.plugins.fake_a")
    _make_fake_pkg("upyscripts.rrepl.plugins.fake_a.sub")
    _make_fake_pkg("upyscripts.rrepl.plugins.fake_b")
    # Sentinels we expect to NOT be dropped:
    sys.modules.setdefault("upyscripts.rrepl.server", sys.modules[__name__])
    untouched_count = sum(
        1 for n in ("upyscripts.rrepl", "upyscripts.rrepl.server")
        if n in sys.modules
    )

    result = _do_reload(
        repl_manager=None,
        prefixes=["upyscripts.rrepl.plugins"],
        reset_sessions=False,
        reinstall_finders=False,
    )

    assert result["ok"] is True
    dropped = set(result["dropped"])
    assert "upyscripts.rrepl.plugins.fake_a" in dropped
    assert "upyscripts.rrepl.plugins.fake_a.sub" in dropped
    assert "upyscripts.rrepl.plugins.fake_b" in dropped
    # Protected modules survive even when their parent prefix would match.
    assert "upyscripts.rrepl.server" in sys.modules
    assert sum(
        1 for n in ("upyscripts.rrepl", "upyscripts.rrepl.server")
        if n in sys.modules
    ) == untouched_count


def test_do_reload_resets_sessions():
    manager = ReplManager()
    manager.execute("x = 1", session="alpha")
    manager.execute("y = 2", session="beta")
    # State present before reload.
    assert manager.execute("print(x)", session="alpha")["stdout"] == "1\n"

    result = _do_reload(
        repl_manager=manager,
        prefixes=[],  # nothing to drop, just exercise session reset
        reset_sessions=True,
        reinstall_finders=False,
    )

    assert result["sessions_reset"] >= 2
    # After reset, x is gone in alpha.
    out = manager.execute("print(globals().get('x', 'gone'))", session="alpha")
    assert out["stdout"] == "gone\n"


def test_reload_endpoint_validates_body_shape():
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/v1/reload", json={"prefixes": "not-a-list"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False


def test_reload_endpoint_default_prefixes_path():
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/v1/reload", json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "dropped" in body
    assert "sessions_reset" in body
    assert "finders_installed" in body


def test_reload_endpoint_empty_body_is_default_reload():
    """No body at all must be treated as a default reload (200), not a
    400 — the deploy loop posts `curl ... /reload` with no payload."""
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/v1/reload")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_reload_endpoint_rejects_falsy_non_object_bodies():
    """A present body that doesn't parse to a JSON object must be a 400,
    never silently coerced to {} (which would perform a default reload —
    dropping modules + resetting sessions — on a bad request)."""
    app = create_app()
    client = app.test_client()
    for raw in ("[]", "false", "0", '""', "123"):
        resp = client.post(
            "/api/v1/reload", data=raw,
            content_type="application/json",
        )
        assert resp.status_code == 400, f"body {raw!r} should be rejected"
        assert resp.get_json()["ok"] is False


def test_reload_endpoint_rejects_malformed_json():
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/api/v1/reload", data="{not valid json",
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_reload_endpoint_rejects_whitespace_only_body():
    """A present-but-whitespace body is not valid JSON; it must 400, not
    be coerced to a default reload."""
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/api/v1/reload", data="   ",
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_discover_editable_finders_picks_up_local_install(tmp_path, monkeypatch):
    """When upyscripts is editable-installed in this venv, the finder
    pattern matches; otherwise discovery just returns nothing. Either
    way the function must yield strings without raising."""
    found = list(_discover_editable_finders())
    # All hits look like importable module names, no path separators.
    for name in found:
        assert isinstance(name, str)
        assert "/" not in name and "\\" not in name
        assert name.startswith("__editable___")
        assert name.endswith("_finder")


def test_discover_editable_finders_handles_missing_dirs(tmp_path, monkeypatch):
    """Inject a bogus sys.path entry; discovery must not crash."""
    monkeypatch.syspath_prepend(str(tmp_path / "does-not-exist" / "site-packages"))
    list(_discover_editable_finders())  # no exception
