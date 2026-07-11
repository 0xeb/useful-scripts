"""Tests for the rrepl plugin scaffold and the upy.rrepl-dbg plugin client.

These tests exercise the **client-side** machinery (lazy bootstrap,
`_call` snippet construction, `__R__` parsing). The Win32-bound
server-side `_DbgImpl` is not exercised here — those need a real
Windows host and a real debuggee.

The Flask test_client is used to run the rrepl server in-process so
no real network is involved.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from upyscripts.rrepl import client as client_module
from upyscripts.rrepl.client import RReplClient
from upyscripts.rrepl.server import ReplManager, create_app
from upyscripts.rrepl.plugins import PluginBase


# --------------------------------------------------------------------------- #
# Test plumbing — same pattern as tests/test_rrepl.py                         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def manager() -> ReplManager:
    return ReplManager()


@pytest.fixture
def flask_client(manager: ReplManager):
    return create_app(manager).test_client()


class _FakeResponse:
    def __init__(self, response):
        self.status_code = response.status_code
        self.text = response.get_data(as_text=True)
        self._json = response.get_json(silent=True)

    def json(self):
        if self._json is None:
            raise ValueError("not JSON")
        return self._json


@pytest.fixture
def rrepl_client(monkeypatch, flask_client) -> RReplClient:
    def fake_request(method, url, timeout=None, **kwargs):
        path = urlsplit(url).path
        response = flask_client.open(path, method=method, json=kwargs.get("json"))
        return _FakeResponse(response)

    monkeypatch.setattr(client_module.requests, "request", fake_request)
    return RReplClient("http://example.test", timeout=3)


# --------------------------------------------------------------------------- #
# A minimal plugin used only to exercise PluginBase                           #
# --------------------------------------------------------------------------- #


_TEST_BOOTSTRAP = """
class _TestSingleton:
    def echo(self, *args, **kw):
        return {"args": list(args), "kw": dict(kw)}
    def add(self, a, b):
        return a + b
SUB = _TestSingleton()
"""


class _TestPlugin(PluginBase):
    _LOADED_KEY = "SUB"
    _BOOTSTRAP = _TEST_BOOTSTRAP


# --------------------------------------------------------------------------- #
# PluginBase tests                                                            #
# --------------------------------------------------------------------------- #


def test_pluginbase_lazy_load_and_call(rrepl_client):
    p = _TestPlugin(client=rrepl_client, session="t1")

    assert p.is_loaded() is False
    p.ensure_loaded()
    assert p.is_loaded() is True
    # Singleton is now in the session — second call sees it instantly.
    assert p.is_loaded() is True


def test_pluginbase_call_round_trip(rrepl_client):
    p = _TestPlugin(client=rrepl_client, session="t2")

    assert p._call("add", 2, 3) == 5
    assert p._call("echo", 1, "x", flag=True) == {
        "args": [1, "x"],
        "kw": {"flag": True},
    }


def test_pluginbase_ensure_loaded_runs_once(monkeypatch, rrepl_client):
    p = _TestPlugin(client=rrepl_client, session="t3")
    calls = []

    real_exec = rrepl_client.exec

    def counting_exec(code, *args, **kw):
        calls.append(code)
        return real_exec(code, *args, **kw)

    monkeypatch.setattr(rrepl_client, "exec", counting_exec)

    p.ensure_loaded()
    p.ensure_loaded()
    p.ensure_loaded()

    bootstrap_calls = [c for c in calls if "_TestSingleton" in c]
    assert len(bootstrap_calls) == 1, calls


def test_pluginbase_reset_clears_session_singleton(rrepl_client):
    p = _TestPlugin(client=rrepl_client, session="t4")
    p.ensure_loaded()
    assert p.is_loaded()

    p.reset_plugin()
    fresh_probe = _TestPlugin(client=rrepl_client, session="t4")
    assert fresh_probe.is_loaded() is False  # singleton is gone server-side


def test_pluginbase_call_parses_complex_json(rrepl_client):
    p = _TestPlugin(client=rrepl_client, session="t5")
    nested = {"a": [1, 2, 3], "b": {"c": "hello"}, "d": None}
    assert p._call("echo", nested) == {"args": [nested], "kw": {}}


def test_pluginbase_subclass_must_set_keys(rrepl_client):
    class Bad(PluginBase):
        pass

    with pytest.raises(RuntimeError, match="_LOADED_KEY"):
        Bad(client=rrepl_client).ensure_loaded()


# --------------------------------------------------------------------------- #
# Dbg client tests — verify the wrapper renders correct snippets without a   #
# real Windows host. We pre-install a stub DBG in the session and mark the    #
# wrapper as loaded so the bootstrap is skipped.                              #
# --------------------------------------------------------------------------- #


_DBG_STUB = """
class _StubDbg:
    def __init__(self):
        self.calls = []
    def spawn(self, path, args=""):
        self.calls.append(("spawn", path, args))
        return {"pid": 1234, "tid": 5678,
                "image_base": 0x140000000,
                "first_event": {"event": "CREATE_PROCESS", "image_base": 0x140000000}}
    def set_bp(self, addr, condition=None, action=None, name=None):
        self.calls.append(("set_bp", addr, condition, action, name))
        return {"set": True, "addr": addr, "orig": 0x48}
    def set_hw_bp(self, addr, type="x", size=1, condition=None,
                  action=None, name=None, slot=None, threads=None):
        self.calls.append(("set_hw_bp", addr, type, size, condition,
                           action, name, slot, threads))
        return {"set": True, "slot": slot or 0, "addr": addr,
                "type": type, "size": size, "name": name}
    def clear_hw_bp(self, addr_or_slot):
        self.calls.append(("clear_hw_bp", addr_or_slot))
        return {"cleared": True, "slot": 0, "addr": 0,
                "type": "x", "size": 1, "name": None,
                "hits": 0, "skipped": 0}
    def list_hw_bps(self):
        self.calls.append(("list_hw_bps",))
        return []
    def get_regs(self, tid=None):
        self.calls.append(("get_regs", tid))
        return {"Rip": 0x1400649a0, "Rax": 0, "Rsp": 0x1000}
    def write_u32(self, addr, v):
        self.calls.append(("write_u32", addr, v))
        return {"addr": addr, "wrote": 4, "flushed": True}
    def kill(self):
        self.calls.append(("kill",))
        return {"killed": True, "exit_code": None}
DBG = _StubDbg()
"""


@pytest.fixture
def dbg_session(rrepl_client) -> RReplClient:
    """rrepl client whose 'dbg' session has a stub DBG installed already."""
    rrepl_client.exec(_DBG_STUB, session="dbg", raise_on_error=True)
    return rrepl_client


def test_dbg_uses_stub_singleton(dbg_session):
    from upyscripts.rrepl.plugins.dbg.client import Dbg

    d = Dbg(client=dbg_session, session="dbg")
    d._loaded = True  # skip bootstrap (the real one would import the win-only server)

    sp = d.spawn(r"C:\Path\To\target.exe")
    assert sp["pid"] == 1234
    assert sp["first_event"]["event"] == "CREATE_PROCESS"


def test_dbg_hex_string_addresses_are_converted(dbg_session):
    from upyscripts.rrepl.plugins.dbg.client import Dbg

    d = Dbg(client=dbg_session, session="dbg")
    d._loaded = True

    res = d.set_bp("0x1400649a0")
    assert res["addr"] == 0x1400649a0


def test_dbg_typed_write_round_trip(dbg_session):
    from upyscripts.rrepl.plugins.dbg.client import Dbg

    d = Dbg(client=dbg_session, session="dbg")
    d._loaded = True

    res = d.write_u32(0x10000, 0xDEADC0DE)
    assert res == {"addr": 0x10000, "wrote": 4, "flushed": True}


def test_dbg_get_regs_returns_dict(dbg_session):
    from upyscripts.rrepl.plugins.dbg.client import Dbg

    d = Dbg(client=dbg_session, session="dbg")
    d._loaded = True

    r = d.get_regs()
    assert r["Rip"] == 0x1400649a0


# --------------------------------------------------------------------------- #
# Plugin manifest + GUIDE                                                     #
# --------------------------------------------------------------------------- #


def test_dbg_plugin_manifest_shape():
    from upyscripts.rrepl.plugins.dbg import MANIFEST, GUIDE_PATH

    assert MANIFEST["name"] == "dbg"
    assert MANIFEST["platform"] == "win32"
    assert MANIFEST["loaded_key"] == "DBG"
    assert MANIFEST["server_module"] == "upyscripts.rrepl.plugins.dbg.server"
    assert "capstone" in " ".join(MANIFEST["server_requires"])
    assert "keystone" in " ".join(MANIFEST["server_requires"])
    assert GUIDE_PATH.exists()
    assert GUIDE_PATH.suffix == ".md"


def test_dbg_guide_text_contains_required_sections():
    from upyscripts.rrepl.plugins.dbg import GUIDE_PATH

    text = GUIDE_PATH.read_text(encoding="utf-8")
    for marker in (
        "TL;DR",
        "Architecture",
        "lazy plugin-load",
        "Full API reference",
        "Event dictionary",
        "Recipes",
        "Troubleshooting",
        "For AI agents",
    ):
        assert marker in text, marker
