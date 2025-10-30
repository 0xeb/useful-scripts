"""
Basic Playwright test to verify setup works with qslideshow web server.
"""

import pytest
import tempfile
import threading
import time
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
    """Start web server in background thread."""
    config = ConfigManager()
    port = find_free_port()
    server = WebSlideshow(test_images, config=config, port=port)

    # Start server in daemon thread
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)  # Wait for server to start

    yield {"server": server, "port": port, "url": f"http://localhost:{port}"}
    # Cleanup happens automatically (daemon thread)


def test_playwright_can_load_page(web_server, page):
    """Test that Playwright can load the qslideshow web page."""
    # Navigate to the slideshow
    page.goto(web_server["url"])

    # Check that the page loaded
    assert page.title() != ""

    # Check for key elements
    img = page.locator("#slideshow-image")
    assert img.is_visible()

    status = page.locator("#status-overlay")
    assert status.is_visible()

    # Verify we're showing image 1 of 3
    assert "1 / 3" in status.inner_text()


def test_playwright_can_navigate(web_server, page):
    """Test that Playwright can simulate navigation."""
    page.goto(web_server["url"])

    # Wait for page to load
    img = page.locator("#slideshow-image")
    img.wait_for()

    # Get initial status
    status = page.locator("#status-overlay")
    initial_status = status.inner_text()
    assert "1 / 3" in initial_status

    # Press right arrow to navigate
    page.keyboard.press("ArrowRight")

    # Wait a bit for the action to process
    time.sleep(0.2)

    # Check status updated
    new_status = status.inner_text()
    assert "2 / 3" in new_status
