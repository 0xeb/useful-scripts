import json
from urllib.parse import urlsplit

import pytest

from upyscripts.rrepl import client as client_module
from upyscripts.rrepl.client import (
    RReplClient,
    RReplError,
    RReplExecutionError,
    RReplHTTPError,
)
from upyscripts.rrepl.server import ReplManager, create_app


def test_default_session_persists_state():
    manager = ReplManager()

    assert manager.execute("x = 41")["ok"] is True
    result = manager.execute("print(x + 1)")

    assert result["ok"] is True
    assert result["stdout"] == "42\n"


def test_named_sessions_are_isolated_and_reused():
    manager = ReplManager()

    manager.execute("x = 'alpha'", session="one")
    missing = manager.execute("print(globals().get('x', 'missing'))", session="two")
    reused = manager.execute("print(x)", session="one")

    assert missing["stdout"] == "missing\n"
    assert reused["stdout"] == "alpha\n"


def test_reset_replaces_named_session_state():
    manager = ReplManager()

    manager.execute("x = 1", session="demo")
    manager.reset("demo")
    result = manager.execute("print(globals().get('x', 'missing'))", session="demo")

    assert result["stdout"] == "missing\n"


def test_delete_removes_named_session():
    manager = ReplManager()

    manager.execute("x = 1", session="demo")
    assert "demo" in manager.list_sessions()

    assert manager.delete("demo") is True
    assert "demo" not in manager.list_sessions()
    assert manager.delete("demo") is False


def test_execute_captures_stdout_stderr_and_errors():
    manager = ReplManager()

    result = manager.execute("import sys\nprint('out')\nprint('err', file=sys.stderr)")
    failure = manager.execute("1 / 0")

    assert result["ok"] is True
    assert result["stdout"] == "out\n"
    assert result["stderr"] == "err\n"
    assert failure["ok"] is False
    assert failure["error"]["type"] == "ZeroDivisionError"
    assert "Traceback" in failure["error"]["traceback"]


@pytest.fixture
def flask_client():
    app = create_app(ReplManager())
    return app.test_client()


def post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def test_flask_exec_endpoint_uses_named_sessions(flask_client):
    first = post_json(
        flask_client,
        "/api/v1/exec",
        {"session": "demo", "code": "x = 7"},
    )
    second = post_json(
        flask_client,
        "/api/v1/exec",
        {"session": "demo", "code": "print(x)"},
    )
    sessions = flask_client.get("/api/v1/sessions")

    assert first.status_code == 200
    assert second.get_json()["stdout"] == "7\n"
    assert {"name": "demo"} in sessions.get_json()["sessions"]


def test_flask_reset_and_delete_endpoints(flask_client):
    post_json(flask_client, "/api/v1/exec", {"session": "demo", "code": "x = 7"})

    reset = post_json(flask_client, "/api/v1/reset", {"session": "demo"})
    after_reset = post_json(
        flask_client,
        "/api/v1/exec",
        {"session": "demo", "code": "print(globals().get('x', 'missing'))"},
    )
    deleted = flask_client.delete("/api/v1/sessions/demo")

    assert reset.get_json() == {"ok": True, "session": "demo"}
    assert after_reset.get_json()["stdout"] == "missing\n"
    assert deleted.get_json() == {"deleted": True, "ok": True, "session": "demo"}


def test_flask_exec_rejects_invalid_json_and_fields(flask_client):
    invalid_json = flask_client.post(
        "/api/v1/exec",
        data="not json",
        content_type="text/plain",
    )
    invalid_code = post_json(flask_client, "/api/v1/exec", {"session": "demo", "code": 123})
    invalid_session = post_json(
        flask_client,
        "/api/v1/exec",
        {"session": ["demo"], "code": "print('x')"},
    )

    assert invalid_json.status_code == 400
    assert invalid_json.get_json()["error"]["message"] == "request body must be a JSON object"
    assert invalid_code.status_code == 400
    assert invalid_code.get_json()["error"]["message"] == "code must be a string"
    assert invalid_session.status_code == 400
    assert invalid_session.get_json()["error"]["message"] == "session must be a string"


class FakeResponse:
    def __init__(self, response):
        self.status_code = response.status_code
        self.text = response.get_data(as_text=True)
        self._json = response.get_json(silent=True)

    def json(self):
        if self._json is None:
            raise ValueError("not JSON")
        return self._json


@pytest.fixture
def rrepl_client(monkeypatch, flask_client):
    def fake_request(method, url, timeout=None, **kwargs):
        path = urlsplit(url).path
        response = flask_client.open(path, method=method, json=kwargs.get("json"))
        return FakeResponse(response)

    monkeypatch.setattr(client_module.requests, "request", fake_request)
    return RReplClient("http://example.test", timeout=3)


def test_python_client_exec_sessions_reset_and_list(rrepl_client):
    rrepl_client.exec("x = 99", session="demo")
    result = rrepl_client.exec("print(x)", session="demo")

    assert result["stdout"] == "99\n"
    assert "demo" in rrepl_client.sessions()

    rrepl_client.reset("demo")
    after_reset = rrepl_client.exec(
        "print(globals().get('x', 'missing'))",
        session="demo",
    )
    assert after_reset["stdout"] == "missing\n"

    delete = rrepl_client.delete_session("demo")
    assert delete["deleted"] is True


def test_python_client_can_raise_for_execution_error(rrepl_client):
    with pytest.raises(RReplExecutionError):
        rrepl_client.exec("1 / 0", raise_on_error=True)


def test_python_client_raises_for_http_error(monkeypatch):
    class ErrorResponse:
        status_code = 400
        text = '{"error": "bad"}'

        def json(self):
            return {"error": "bad"}

    monkeypatch.setattr(
        client_module.requests,
        "request",
        lambda *args, **kwargs: ErrorResponse(),
    )

    with pytest.raises(RReplHTTPError):
        RReplClient("http://example.test").health()


def test_python_client_wraps_connection_errors(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise client_module.requests.ConnectionError("connection refused")

    monkeypatch.setattr(client_module.requests, "request", raise_connection_error)

    with pytest.raises(RReplError, match="connection refused"):
        RReplClient("http://example.test").health()
