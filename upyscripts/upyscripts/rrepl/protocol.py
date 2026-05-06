"""Shared constants and validation helpers for rrepl."""

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765
DEFAULT_SESSION = "default"
API_PREFIX = "/api/v1"


def normalize_session_name(value):
    """Return a usable session name, defaulting empty names to DEFAULT_SESSION."""
    if value is None:
        return DEFAULT_SESSION
    if not isinstance(value, str):
        raise TypeError("session must be a string")
    name = value.strip()
    return name or DEFAULT_SESSION


def validation_error(message, session=None):
    try:
        session_name = normalize_session_name(session)
    except TypeError:
        session_name = DEFAULT_SESSION

    payload = {
        "ok": False,
        "session": session_name,
        "stdout": "",
        "stderr": "",
        "error": {
            "type": "BadRequest",
            "message": message,
            "traceback": None,
        },
    }
    return payload
