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


class TestShuffleMode:
    """Test shuffle functionality."""

    @pytest.fixture
    def web_server_shuffle(self, test_images):
        """Start web server with shuffle enabled."""
        config = ConfigManager()
        config.set('slideshow.shuffle', True)
        port = find_free_port()
        server = WebSlideshow(test_images, config=config, port=port)

        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        time.sleep(0.5)

        yield server

    def test_shuffle_enabled_on_startup(self, web_server_shuffle):
        """Test that shuffle is enabled when configured."""
        base_url = f"http://localhost:{web_server_shuffle.port}"

        # Create a session and check shuffle status
        r = requests.get(
            f"{base_url}/api/status",
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        assert r.json()["shuffle"] == True

    def test_different_sessions_get_different_shuffle_orders(self, web_server_shuffle):
        """Test that each session gets its own shuffle order."""
        base_url = f"http://localhost:{web_server_shuffle.port}"

        # Get image lists for three different sessions
        r1 = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "s1"})
        r2 = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "s2"})
        r3 = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "s3"})

        images1 = [img["name"] for img in r1.json()["images"]]
        images2 = [img["name"] for img in r2.json()["images"]]
        images3 = [img["name"] for img in r3.json()["images"]]

        # All should have same images (just different order)
        assert set(images1) == set(images2) == set(images3)

        # At least one should have a different order (highly likely with shuffle)
        # Note: there's a small chance all three get the same random order
        orders_match = (images1 == images2 and images2 == images3)
        assert not orders_match, "All three sessions got identical shuffle order (very unlikely)"

    def test_toggle_shuffle_on(self, web_server):
        """Test toggling shuffle on from off state."""
        base_url = f"http://localhost:{web_server.port}"

        # Get initial image order (sequential)
        r = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "test"})
        initial_images = [img["name"] for img in r.json()["images"]]

        # Toggle shuffle on
        r = requests.post(
            f"{base_url}/api/execute",
            json={"action": "toggle_shuffle"},
            headers={"X-Session-ID": "test"}
        )
        assert r.status_code == 200
        assert r.json()["shuffle"] == True

        # Get new image order
        r = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "test"})
        shuffled_images = [img["name"] for img in r.json()["images"]]

        # Should have same images, likely different order
        assert set(initial_images) == set(shuffled_images)

    def test_toggle_shuffle_off_uses_server_order(self, web_server_shuffle):
        """Test toggling shuffle off gives sequential indices into server's image list."""
        base_url = f"http://localhost:{web_server_shuffle.port}"

        # Session 1: Get shuffled order
        r1 = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "s1"})
        s1_shuffled = [img["name"] for img in r1.json()["images"]]

        # Session 2: Get its own different shuffled order
        r2 = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "s2"})
        s2_shuffled = [img["name"] for img in r2.json()["images"]]

        # They should be different (with high probability)
        assert s1_shuffled != s2_shuffled, "Sessions should have different shuffle orders"

        # Toggle shuffle off in session 1
        r = requests.post(
            f"{base_url}/api/execute",
            json={"action": "toggle_shuffle"},
            headers={"X-Session-ID": "s1"}
        )
        assert r.status_code == 200
        assert r.json()["shuffle"] == False

        # Toggle shuffle off in session 2
        r = requests.post(
            f"{base_url}/api/execute",
            json={"action": "toggle_shuffle"},
            headers={"X-Session-ID": "s2"}
        )
        assert r.status_code == 200
        assert r.json()["shuffle"] == False

        # Now both should have the same order (sequential indices into server's list)
        r1 = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "s1"})
        r2 = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "s2"})

        s1_sequential = [img["name"] for img in r1.json()["images"]]
        s2_sequential = [img["name"] for img in r2.json()["images"]]

        # Both should now have identical order
        assert s1_sequential == s2_sequential

    def test_shuffle_preserves_current_image(self, web_server):
        """Test that toggling shuffle keeps you on the current image."""
        base_url = f"http://localhost:{web_server.port}"

        # Navigate to image 1
        requests.post(
            f"{base_url}/api/execute",
            json={"action": "navigate_next"},
            headers={"X-Session-ID": "test"}
        )

        # Get current image name
        r = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "test"})
        images = r.json()["images"]
        r = requests.get(f"{base_url}/api/status", headers={"X-Session-ID": "test"})
        current_idx = r.json()["current_index"]
        current_image_name = images[current_idx]["name"]

        # Toggle shuffle on
        requests.post(
            f"{base_url}/api/execute",
            json={"action": "toggle_shuffle"},
            headers={"X-Session-ID": "test"}
        )

        # Check we're still viewing the same image
        r = requests.get(f"{base_url}/api/images", headers={"X-Session-ID": "test"})
        new_images = r.json()["images"]
        r = requests.get(f"{base_url}/api/status", headers={"X-Session-ID": "test"})
        new_current_idx = r.json()["current_index"]
        new_current_image_name = new_images[new_current_idx]["name"]

        assert current_image_name == new_current_image_name
