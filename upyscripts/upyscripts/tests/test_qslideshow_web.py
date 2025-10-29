"""
Tests for qslideshow web server mode.

Tests cover:
- Server startup and configuration
- Session independence (each browser tab has own state)
- Password authentication
- API endpoints
- Authentication sharing across sessions
"""

import pytest
import tempfile
import time
import requests
import threading
import socket
from pathlib import Path
from PIL import Image

from upyscripts.qslideshow.webserver import WebSlideshow
from upyscripts.qslideshow.config import ConfigManager


def find_free_port():
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def test_images():
    """Create temporary test images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # Create 3 test images with different colors
        for i in range(3):
            img = Image.new('RGB', (100, 100), color=(i*80, 0, 0))
            img.save(tmpdir / f"test{i}.png")
        yield list(tmpdir.glob("*.png"))


@pytest.fixture
def web_server(test_images):
    """Start web server without password in background thread."""
    config = ConfigManager()
    port = find_free_port()
    server = WebSlideshow(test_images, config=config, port=port)

    # Start server in daemon thread
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)  # Wait for server to start

    yield server
    # Cleanup happens automatically (daemon thread)


@pytest.fixture
def web_server_with_password(test_images):
    """Start web server WITH password protection."""
    config = ConfigManager()
    port = find_free_port()
    server = WebSlideshow(test_images, config=config, port=port, password="test123")

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)

    yield server


class TestServerStartup:
    """Test server initialization and startup."""

    def test_server_starts_successfully(self, web_server):
        """Test that server starts and has correct configuration."""
        assert web_server.port > 0
        assert len(web_server.image_paths) == 3
        assert web_server.password is None

    def test_server_with_password_starts(self, web_server_with_password):
        """Test that server with password protection starts."""
        assert web_server_with_password.port > 0
        assert web_server_with_password.password == "test123"
        assert len(web_server_with_password.authenticated_sessions) == 0


class TestSessionIndependence:
    """Test that different browser tabs have independent slideshow state."""

    def test_different_sessions_have_different_state(self, web_server):
        """Test that two sessions maintain independent current_index."""
        base_url = f"http://localhost:{web_server.port}"

        # Session 1: Navigate to next image
        r = requests.post(
            f"{base_url}/api/execute",
            json={"action": "navigate_next"},
            headers={"X-Session-ID": "session-1"}
        )
        assert r.status_code == 200
        assert r.json()["current_index"] == 1

        # Session 2: Should still be at index 0 (independent)
        r = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "session-2"}
        )
        assert r.status_code == 200
        assert r.json()["current_index"] == 0

        # Session 1: Should still be at index 1
        r = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "session-1"}
        )
        assert r.status_code == 200
        assert r.json()["current_index"] == 1

    def test_sessions_can_navigate_independently(self, web_server):
        """Test that multiple sessions can navigate independently."""
        base_url = f"http://localhost:{web_server.port}"

        # Session 1: Go to index 2
        requests.post(
            f"{base_url}/api/execute",
            json={"action": "navigate_next"},
            headers={"X-Session-ID": "s1"}
        )
        requests.post(
            f"{base_url}/api/execute",
            json={"action": "navigate_next"},
            headers={"X-Session-ID": "s1"}
        )

        # Session 2: Go to index 1
        requests.post(
            f"{base_url}/api/execute",
            json={"action": "navigate_next"},
            headers={"X-Session-ID": "s2"}
        )

        # Session 3: Stay at index 0
        requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "s3"}
        )

        # Verify each session is at different index
        r1 = requests.get(f"{base_url}/api/status", headers={"X-Session-ID": "s1"})
        r2 = requests.get(f"{base_url}/api/status", headers={"X-Session-ID": "s2"})
        r3 = requests.get(f"{base_url}/api/status", headers={"X-Session-ID": "s3"})

        assert r1.json()["current_index"] == 2
        assert r2.json()["current_index"] == 1
        assert r3.json()["current_index"] == 0

    def test_sessions_can_have_different_pause_state(self, web_server):
        """Test that pause state is per-session."""
        base_url = f"http://localhost:{web_server.port}"

        # Session 1: Pause
        requests.post(
            f"{base_url}/api/execute",
            json={"action": "toggle_pause"},
            headers={"X-Session-ID": "s1"}
        )

        # Check states
        r1 = requests.get(f"{base_url}/api/status", headers={"X-Session-ID": "s1"})
        r2 = requests.get(f"{base_url}/api/status", headers={"X-Session-ID": "s2"})

        assert r1.json()["is_paused"] == True
        assert r2.json()["is_paused"] == False


class TestPasswordAuthentication:
    """Test password authentication functionality."""

    def test_unauthenticated_access_blocked(self, web_server_with_password):
        """Test that API access is blocked without authentication."""
        base_url = f"http://localhost:{web_server_with_password.port}"

        # Try to access API without auth
        r = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 401

    def test_wrong_password_rejected(self, web_server_with_password):
        """Test that wrong password is rejected."""
        base_url = f"http://localhost:{web_server_with_password.port}"

        r = requests.post(
            f"{base_url}/api/authenticate",
            json={"password": "wrong_password"}
        )
        assert r.status_code == 401
        assert r.json()["success"] == False
        assert "error" in r.json()

    def test_correct_password_accepted(self, web_server_with_password):
        """Test that correct password grants access."""
        base_url = f"http://localhost:{web_server_with_password.port}"

        # Authenticate with correct password
        r = requests.post(
            f"{base_url}/api/authenticate",
            json={"password": "test123"}
        )
        assert r.status_code == 200
        assert r.json()["success"] == True
        assert "auth_session" in r.cookies

    def test_authenticated_api_access_works(self, web_server_with_password):
        """Test that API works after authentication."""
        base_url = f"http://localhost:{web_server_with_password.port}"

        # Authenticate
        r_auth = requests.post(
            f"{base_url}/api/authenticate",
            json={"password": "test123"}
        )
        cookies = r_auth.cookies

        # Access API with auth cookie
        r = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "test"},
            cookies=cookies
        )
        assert r.status_code == 200
        assert "current_index" in r.json()

    def test_authentication_shared_across_sessions(self, web_server_with_password):
        """Test that one authentication works for multiple session IDs."""
        base_url = f"http://localhost:{web_server_with_password.port}"

        # Authenticate once
        r_auth = requests.post(
            f"{base_url}/api/authenticate",
            json={"password": "test123"}
        )
        cookies = r_auth.cookies

        # Use same auth cookie with different session IDs
        r1 = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "session-1"},
            cookies=cookies
        )
        r2 = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "session-2"},
            cookies=cookies
        )

        # Both should work
        assert r1.status_code == 200
        assert r2.status_code == 200

        # But sessions should still be independent
        requests.post(
            f"{base_url}/api/execute",
            json={"action": "navigate_next"},
            headers={"X-Session-ID": "session-1"},
            cookies=cookies
        )

        r1_after = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "session-1"},
            cookies=cookies
        )
        r2_after = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "session-2"},
            cookies=cookies
        )

        assert r1_after.json()["current_index"] == 1
        assert r2_after.json()["current_index"] == 0


class TestAPIEndpoints:
    """Test all API endpoints."""

    def test_api_images(self, web_server):
        """Test /api/images endpoint."""
        base_url = f"http://localhost:{web_server.port}"

        r = requests.get(
            f"{base_url}/api/images",
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        data = r.json()
        assert "images" in data
        assert len(data["images"]) == 3
        assert all("index" in img for img in data["images"])
        assert all("name" in img for img in data["images"])

    def test_api_status(self, web_server):
        """Test /api/status endpoint."""
        base_url = f"http://localhost:{web_server.port}"

        r = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        data = r.json()
        assert "current_index" in data
        assert "total_images" in data
        assert "is_paused" in data
        assert "speed" in data
        assert data["total_images"] == 3

    def test_api_config(self, web_server):
        """Test /api/config endpoint."""
        base_url = f"http://localhost:{web_server.port}"

        r = requests.get(
            f"{base_url}/api/config",
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        data = r.json()
        assert "speed" in data
        assert "repeat" in data
        assert "shuffle" in data

    def test_api_actions(self, web_server):
        """Test /api/actions endpoint."""
        base_url = f"http://localhost:{web_server.port}"

        r = requests.get(
            f"{base_url}/api/actions",
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        data = r.json()
        assert "actions" in data
        assert len(data["actions"]) > 0

        # Check that navigate actions exist
        action_names = [a["name"] for a in data["actions"]]
        assert "navigate_next" in action_names
        assert "navigate_previous" in action_names

    def test_api_execute_navigate_next(self, web_server):
        """Test /api/execute endpoint with navigate_next."""
        base_url = f"http://localhost:{web_server.port}"

        # Execute navigate_next
        r = requests.post(
            f"{base_url}/api/execute",
            json={"action": "navigate_next"},
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] == True
        assert data["current_index"] == 1

    def test_api_execute_toggle_pause(self, web_server):
        """Test /api/execute endpoint with toggle_pause."""
        base_url = f"http://localhost:{web_server.port}"

        # Toggle pause
        r = requests.post(
            f"{base_url}/api/execute",
            json={"action": "toggle_pause"},
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] == True
        assert data["is_paused"] == True


class TestHTMLPages:
    """Test HTML page serving."""

    def test_main_page_serves(self, web_server):
        """Test that main page serves without error."""
        base_url = f"http://localhost:{web_server.port}"

        r = requests.get(f"{base_url}/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")

    def test_main_page_redirects_when_password_required(self, web_server_with_password):
        """Test that main page redirects to login when password is set."""
        base_url = f"http://localhost:{web_server_with_password.port}"

        r = requests.get(f"{base_url}/", allow_redirects=False)
        assert r.status_code == 302
        assert r.headers["Location"] == "/login.html"

    def test_login_page_serves(self, web_server_with_password):
        """Test that login page serves."""
        base_url = f"http://localhost:{web_server_with_password.port}"

        r = requests.get(f"{base_url}/login.html")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")
