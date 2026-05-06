"""Small Python client for the rrepl HTTP API."""

from urllib.parse import quote

import requests

from .protocol import API_PREFIX, DEFAULT_SESSION


class RReplError(RuntimeError):
    """Base rrepl client error."""


class RReplHTTPError(RReplError):
    """Raised when the server returns a non-success HTTP status."""

    def __init__(self, status_code, payload):
        super().__init__("rrepl HTTP error {}: {}".format(status_code, payload))
        self.status_code = status_code
        self.payload = payload


class RReplExecutionError(RReplError):
    """Raised when executed Python code returns ok=false."""

    def __init__(self, payload):
        error = payload.get("error") or {}
        super().__init__(
            "{}: {}".format(
                error.get("type", "ExecutionError"),
                error.get("message", ""),
            )
        )
        self.payload = payload


class RReplClient:
    """HTTP JSON client for an rrepl server."""

    def __init__(self, base_url="http://127.0.0.1:8765", timeout=30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(
                method,
                self.base_url + path,
                timeout=self.timeout,
                **kwargs
            )
        except requests.RequestException as exc:
            raise RReplError(str(exc)) from exc
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        if response.status_code >= 400:
            raise RReplHTTPError(response.status_code, payload)
        return payload

    def health(self):
        return self._request("GET", "/health")

    def exec(self, code, session=DEFAULT_SESSION, raise_on_error=False):
        payload = self._request(
            "POST",
            API_PREFIX + "/exec",
            json={"code": code, "session": session},
        )
        if raise_on_error and not payload.get("ok"):
            raise RReplExecutionError(payload)
        return payload

    def reset(self, session=DEFAULT_SESSION):
        return self._request("POST", API_PREFIX + "/reset", json={"session": session})

    def sessions(self):
        payload = self._request("GET", API_PREFIX + "/sessions")
        return [item["name"] for item in payload.get("sessions", [])]

    def delete_session(self, session):
        return self._request(
            "DELETE",
            API_PREFIX + "/sessions/" + quote(session, safe=""),
        )
