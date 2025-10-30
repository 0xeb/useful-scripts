"""
Playwright tests for auto-advance timer reset behavior.

Tests verify that the auto-advance timer properly resets when user
actions are performed, ensuring users get the full duration to view
an image after taking an action.
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
        # Create 5 test images so we have room to navigate
        for i in range(5):
            img = Image.new('RGB', (100, 100), color=(i*50, 0, 0))
            img.save(tmpdir / f"test{i}.png")
        yield list(tmpdir.glob("*.png"))


@pytest.fixture
def web_server_with_timer(test_images):
    """Start web server with a short auto-advance timer for testing."""
    config = ConfigManager()
    # Set a short speed for testing (2 seconds)
    config.set('slideshow.speed', 2.0)
    config.set('slideshow.repeat', True)  # Allow repeating

    port = find_free_port()
    server = WebSlideshow(test_images, config=config, port=port)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)

    yield {"server": server, "port": port, "url": f"http://localhost:{port}"}


def get_current_index(page):
    """Helper to extract current image index from status text."""
    status = page.locator("#status-overlay")
    status_text = status.inner_text()
    # Extract "X / Y" format
    parts = status_text.split('/')
    if len(parts) >= 2:
        current = parts[0].strip().split()[-1]  # Get last part before /
        return int(current)
    return None


def test_timer_resets_on_navigation(web_server_with_timer, page):
    """Test that timer resets when navigating with arrow keys."""
    page.goto(web_server_with_timer["url"])

    # Wait for page to load
    page.locator("#slideshow-image").wait_for()
    time.sleep(0.5)  # Ensure page is fully initialized

    # Start at image 1
    assert get_current_index(page) == 1

    # Wait 1 second (half the 2-second timer)
    time.sleep(1.0)

    # Navigate to next image manually
    page.keyboard.press("ArrowRight")
    time.sleep(0.3)  # Wait for action to process

    # Should now be at image 2
    assert get_current_index(page) == 2

    # Record the time we navigated
    action_time = time.time()

    # Wait 1.5 seconds - if timer didn't reset, auto-advance would have
    # happened by now (we'd be at image 3)
    time.sleep(1.5)

    # Should still be at image 2 (timer was reset, so we haven't reached 2 seconds yet)
    assert get_current_index(page) == 2

    # Wait another 1 second (total 2.5 seconds since action)
    # Now the full 2-second timer has elapsed, so we should auto-advance to image 3
    time.sleep(1.0)

    # Should now be at image 3 (auto-advanced)
    current = get_current_index(page)
    assert current == 3, f"Expected image 3 after timer elapsed, got {current}"


def test_timer_resets_on_speed_change(web_server_with_timer, page):
    """Test that timer resets and applies new speed when speed is changed."""
    page.goto(web_server_with_timer["url"])

    page.locator("#slideshow-image").wait_for()
    time.sleep(0.5)

    # Start at image 1
    assert get_current_index(page) == 1

    # Wait 1 second
    time.sleep(1.0)

    # Increase speed (which makes slideshow SLOWER, adding 1 second)
    # This should reset the timer AND apply new 3-second speed
    page.keyboard.press("+")
    time.sleep(0.3)

    # Wait 2 seconds - if timer didn't reset, we'd be at image 2
    # But with reset + new 3-second speed, we should still be at image 1
    time.sleep(2.0)

    # Should still be at image 1
    assert get_current_index(page) == 1

    # Wait another 1.5 seconds (total 3.5 seconds since speed change)
    # Now the new 3-second timer has elapsed
    time.sleep(1.5)

    # Should have auto-advanced to image 2
    current = get_current_index(page)
    assert current == 2, f"Expected image 2 after new timer elapsed, got {current}"


def test_timer_resets_on_shuffle_toggle(web_server_with_timer, page):
    """Test that timer resets when shuffle mode is toggled."""
    page.goto(web_server_with_timer["url"])

    page.locator("#slideshow-image").wait_for()
    time.sleep(0.5)

    # Start at image 1
    initial_index = get_current_index(page)
    assert initial_index == 1

    # Wait 1 second
    time.sleep(1.0)

    # Toggle shuffle
    page.keyboard.press("s")
    time.sleep(0.3)

    # Get current index after shuffle (might have changed due to shuffle)
    current_after_shuffle = get_current_index(page)

    # Wait 1.5 seconds - if timer didn't reset, auto-advance would happen
    time.sleep(1.5)

    # Should still be at same image (timer was reset)
    assert get_current_index(page) == current_after_shuffle

    # Wait another 1 second (total 2.5 seconds)
    # Now the 2-second timer has elapsed
    time.sleep(1.0)

    # Should have auto-advanced to next image
    new_index = get_current_index(page)
    assert new_index != current_after_shuffle, "Image should have auto-advanced after timer elapsed"


def test_timer_resets_on_repeat_toggle(web_server_with_timer, page):
    """Test that timer resets when repeat mode is toggled."""
    page.goto(web_server_with_timer["url"])

    page.locator("#slideshow-image").wait_for()
    time.sleep(0.5)

    # Start at image 1
    assert get_current_index(page) == 1

    # Wait 1 second
    time.sleep(1.0)

    # Toggle repeat mode
    page.keyboard.press("r")
    time.sleep(0.3)

    # Wait 1.5 seconds - if timer didn't reset, auto-advance would happen
    time.sleep(1.5)

    # Should still be at image 1 (timer was reset)
    assert get_current_index(page) == 1

    # Wait another 1 second (total 2.5 seconds)
    time.sleep(1.0)

    # Should have auto-advanced to image 2
    assert get_current_index(page) == 2


def test_auto_advance_works_without_actions(web_server_with_timer, page):
    """Test that auto-advance still works when no actions are taken."""
    page.goto(web_server_with_timer["url"])

    page.locator("#slideshow-image").wait_for()
    time.sleep(0.5)

    # Start at image 1
    assert get_current_index(page) == 1

    # Wait for the 2-second timer to elapse
    time.sleep(2.5)

    # Should have auto-advanced to image 2
    assert get_current_index(page) == 2

    # Wait another 2 seconds
    time.sleep(2.5)

    # Should have auto-advanced to image 3
    assert get_current_index(page) == 3
