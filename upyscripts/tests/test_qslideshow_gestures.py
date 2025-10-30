"""
Comprehensive tests for qslideshow gesture system.

Tests cover:
- Swipe detection (4 directions)
- Tap detection (single, double)
- Long press detection
- Pinch gestures (in, out)
- Multi-finger gestures (2-finger, 3-finger)
- Threshold configurations
- Mouse event simulation
- GestureManager action execution
"""

import pytest
import time
from unittest.mock import Mock, patch

from upyscripts.qslideshow.gestures import GestureDetector, GestureManager
from upyscripts.qslideshow.config import ConfigManager
from upyscripts.qslideshow.core import SlideshowContext
from pathlib import Path


@pytest.fixture
def detector():
    """Create a basic gesture detector."""
    return GestureDetector()


@pytest.fixture
def gesture_config():
    """Create config with gesture mappings."""
    config = ConfigManager()
    config.config = {
        'gestures': {
            'common': {
                'swipe_left': 'navigate_next',
                'swipe_right': 'navigate_previous',
                'double_tap': 'toggle_pause',
            },
            'web': {
                'swipe_up': 'increase_speed',
                'swipe_down': 'decrease_speed',
                'long_press': 'toggle_fullscreen',
                'pinch_out': 'increase_speed',
                'pinch_in': 'decrease_speed',
            }
        }
    }
    return config


@pytest.fixture
def slideshow_context():
    """Create a minimal slideshow context."""
    return SlideshowContext(
        image_paths=[Path("/tmp/test1.jpg"), Path("/tmp/test2.jpg")],
        speed=3.0
    )


class TestSwipeDetection:
    """Test swipe gesture detection."""

    def test_swipe_left(self, detector):
        """Test left swipe detection."""
        # Touch start at (200, 200)
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        # Touch end at (100, 200) - moved left 100px
        detector.touch_points = [{'x': 100, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture == 'swipe_left'

    def test_swipe_right(self, detector):
        """Test right swipe detection."""
        detector.process_touch_event('touchstart', [{'x': 100, 'y': 200, 'id': 0}])

        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture == 'swipe_right'

    def test_swipe_up(self, detector):
        """Test upward swipe detection."""
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 300, 'id': 0}])

        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture == 'swipe_up'

    def test_swipe_down(self, detector):
        """Test downward swipe detection."""
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        detector.touch_points = [{'x': 200, 'y': 300, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture == 'swipe_down'

    def test_swipe_threshold_not_met(self, detector):
        """Test that small movements don't trigger swipe."""
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        # Move only 30px (threshold is 50px)
        detector.touch_points = [{'x': 230, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        # Should not be a swipe (might be tap)
        assert gesture != 'swipe_right' and gesture != 'swipe_left'

    def test_horizontal_swipe_preferred_over_vertical(self, detector):
        """Test that larger horizontal movement is detected as horizontal swipe."""
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        # Move 100px right and 30px down
        detector.touch_points = [{'x': 300, 'y': 230, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture == 'swipe_right'


class TestTapDetection:
    """Test tap gesture detection."""

    def test_single_tap_not_returned_immediately(self, detector):
        """Test that single tap is not returned immediately (allows double tap)."""
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        # Quick touch end (no movement)
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        # Single tap should not be returned (waiting for potential double tap)
        assert gesture is None

    def test_double_tap(self, detector):
        """Test double tap detection."""
        # First tap
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        detector.process_touch_event('touchend', [])

        # Second tap quickly after
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture == 'double_tap'

    def test_double_tap_resets_after_detection(self, detector):
        """Test that tap count resets after double tap."""
        # First double tap
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        detector.process_touch_event('touchend', [])

        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])
        assert gesture == 'double_tap'

        # Tap count should be reset
        assert detector.tap_count == 0

    @patch('time.time')
    def test_slow_taps_not_double_tap(self, mock_time, detector):
        """Test that slow taps don't trigger double tap."""
        mock_time.return_value = 1.0

        # First tap
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        detector.process_touch_event('touchend', [])

        # Wait too long (> double_tap_interval)
        mock_time.return_value = 1.5

        # Second tap
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        # Should not be double tap
        assert gesture != 'double_tap'


class TestLongPress:
    """Test long press detection."""

    @patch('time.time')
    def test_long_press_detection(self, mock_time, detector):
        """Test long press detection."""
        mock_time.return_value = 1.0
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        # Hold for long enough
        mock_time.return_value = 1.6  # 0.6 seconds (> 0.5 threshold)
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture == 'long_press'

    @patch('time.time')
    def test_short_press_not_long_press(self, mock_time, detector):
        """Test that short press is not detected as long press."""
        mock_time.return_value = 1.0
        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        # Release quickly
        mock_time.return_value = 1.2  # 0.2 seconds (< 0.5 threshold)
        detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        assert gesture != 'long_press'


class TestPinchGestures:
    """Test pinch gesture detection."""

    def test_pinch_out(self, detector):
        """Test pinch out (zoom in) detection."""
        # Start with two fingers close together
        touches_start = [
            {'x': 200, 'y': 200, 'id': 0},
            {'x': 210, 'y': 200, 'id': 1}
        ]
        detector.process_touch_event('touchstart', touches_start)

        # Move fingers apart (50px apart)
        touches_move = [
            {'x': 175, 'y': 200, 'id': 0},
            {'x': 235, 'y': 200, 'id': 1}
        ]
        gesture = detector.process_touch_event('touchmove', touches_move)

        assert gesture == 'pinch_out'

    def test_pinch_in(self, detector):
        """Test pinch in (zoom out) detection."""
        # Start with two fingers far apart
        touches_start = [
            {'x': 150, 'y': 200, 'id': 0},
            {'x': 250, 'y': 200, 'id': 1}
        ]
        detector.process_touch_event('touchstart', touches_start)

        # Move fingers together
        touches_move = [
            {'x': 190, 'y': 200, 'id': 0},
            {'x': 210, 'y': 200, 'id': 1}
        ]
        gesture = detector.process_touch_event('touchmove', touches_move)

        assert gesture == 'pinch_in'

    def test_pinch_threshold_not_met(self, detector):
        """Test that small pinch movements don't trigger gesture."""
        touches_start = [
            {'x': 200, 'y': 200, 'id': 0},
            {'x': 220, 'y': 200, 'id': 1}
        ]
        detector.process_touch_event('touchstart', touches_start)

        # Move slightly (less than 30px threshold)
        touches_move = [
            {'x': 195, 'y': 200, 'id': 0},
            {'x': 225, 'y': 200, 'id': 1}
        ]
        gesture = detector.process_touch_event('touchmove', touches_move)

        assert gesture is None


class TestTwoFingerGestures:
    """Test two-finger swipe gestures."""

    def test_two_finger_swipe_left(self, detector):
        """Test two-finger swipe left."""
        touches_start = [
            {'x': 200, 'y': 200, 'id': 0},
            {'x': 200, 'y': 250, 'id': 1}
        ]
        detector.process_touch_event('touchstart', touches_start)

        # Swipe left with both fingers
        touches_move = [
            {'x': 100, 'y': 200, 'id': 0},
            {'x': 100, 'y': 250, 'id': 1}
        ]
        gesture = detector.process_touch_event('touchmove', touches_move)

        assert gesture == 'two_finger_swipe_left'

    def test_two_finger_swipe_right(self, detector):
        """Test two-finger swipe right."""
        touches_start = [
            {'x': 100, 'y': 200, 'id': 0},
            {'x': 100, 'y': 250, 'id': 1}
        ]
        detector.process_touch_event('touchstart', touches_start)

        touches_move = [
            {'x': 200, 'y': 200, 'id': 0},
            {'x': 200, 'y': 250, 'id': 1}
        ]
        gesture = detector.process_touch_event('touchmove', touches_move)

        assert gesture == 'two_finger_swipe_right'

    def test_two_finger_swipe_up(self, detector):
        """Test two-finger swipe up."""
        touches_start = [
            {'x': 200, 'y': 300, 'id': 0},
            {'x': 250, 'y': 300, 'id': 1}
        ]
        detector.process_touch_event('touchstart', touches_start)

        touches_move = [
            {'x': 200, 'y': 200, 'id': 0},
            {'x': 250, 'y': 200, 'id': 1}
        ]
        gesture = detector.process_touch_event('touchmove', touches_move)

        assert gesture == 'two_finger_swipe_up'

    def test_two_finger_swipe_down(self, detector):
        """Test two-finger swipe down."""
        touches_start = [
            {'x': 200, 'y': 200, 'id': 0},
            {'x': 250, 'y': 200, 'id': 1}
        ]
        detector.process_touch_event('touchstart', touches_start)

        touches_move = [
            {'x': 200, 'y': 300, 'id': 0},
            {'x': 250, 'y': 300, 'id': 1}
        ]
        gesture = detector.process_touch_event('touchmove', touches_move)

        assert gesture == 'two_finger_swipe_down'


class TestMultiFingerTap:
    """Test multi-finger tap detection."""

    def test_three_finger_tap(self, detector):
        """Test three-finger tap detection."""
        touches = [
            {'x': 200, 'y': 200, 'id': 0},
            {'x': 250, 'y': 200, 'id': 1},
            {'x': 300, 'y': 200, 'id': 2}
        ]
        gesture = detector.process_touch_event('touchstart', touches)

        assert gesture == 'three_finger_tap'


class TestMouseEventSimulation:
    """Test mouse events simulated as touch gestures."""

    def test_mouse_drag_left_as_swipe(self, detector):
        """Test mouse drag simulated as swipe gesture."""
        # Mouse down at (200, 200)
        detector.process_mouse_event('mousedown', 200, 200)

        # Mouse move to (100, 200) - simulates drag
        detector.process_mouse_event('mousemove', 100, 200)

        # Update touch_points to reflect final position
        detector.touch_points = [{'x': 100, 'y': 200, 'id': 0}]

        # Mouse up
        gesture = detector.process_mouse_event('mouseup', 100, 200)

        assert gesture == 'swipe_left'

    def test_mouse_click_as_tap(self, detector):
        """Test mouse click simulated as tap."""
        detector.process_mouse_event('mousedown', 200, 200)
        gesture = detector.process_mouse_event('mouseup', 200, 200)

        # Single tap doesn't return immediately
        assert gesture is None


class TestGestureManager:
    """Test gesture manager integration."""

    def test_manager_initialization(self, gesture_config):
        """Test gesture manager initialization."""
        manager = GestureManager(gesture_config, 'web')

        assert manager.config == gesture_config
        assert manager.context == 'web'
        assert isinstance(manager.gesture_map, dict)
        assert isinstance(manager.detector, GestureDetector)

    def test_manager_loads_gesture_mappings(self, gesture_config):
        """Test that gesture mappings are loaded from config."""
        manager = GestureManager(gesture_config, 'web')

        # Common gestures
        assert manager.gesture_map['swipe_left'] == 'navigate_next'
        assert manager.gesture_map['swipe_right'] == 'navigate_previous'

        # Context-specific gestures
        assert manager.gesture_map['swipe_up'] == 'increase_speed'
        assert manager.gesture_map['long_press'] == 'toggle_fullscreen'

    def test_handle_touch_event_executes_action(self, gesture_config, slideshow_context):
        """Test that touch event triggers action execution."""
        manager = GestureManager(gesture_config, 'web')

        # Simulate swipe left gesture
        manager.handle_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}], slideshow_context)

        manager.detector.touch_points = [{'x': 100, 'y': 200, 'id': 0}]
        result = manager.handle_touch_event('touchend', [], slideshow_context)

        # Should execute navigate_next action
        assert result is not None
        assert 'current_index' in result

    def test_get_action_for_gesture(self, gesture_config):
        """Test getting action name for gesture."""
        manager = GestureManager(gesture_config, 'web')

        assert manager.get_action_for_gesture('swipe_left') == 'navigate_next'
        assert manager.get_action_for_gesture('double_tap') == 'toggle_pause'
        assert manager.get_action_for_gesture('nonexistent') is None

    def test_handle_mouse_event(self, gesture_config, slideshow_context):
        """Test mouse event handling."""
        manager = GestureManager(gesture_config, 'web')

        # Simulate mouse swipe left
        manager.handle_mouse_event('mousedown', 200, 200, 1, slideshow_context)
        manager.handle_mouse_event('mousemove', 100, 200, 1, slideshow_context)

        # Update touch_points manually for test
        manager.detector.touch_points = [{'x': 100, 'y': 200, 'id': 0}]

        result = manager.handle_mouse_event('mouseup', 100, 200, 1, slideshow_context)

        # Should execute navigate_next (mapped to swipe_left)
        assert result is not None
        assert 'current_index' in result


class TestThresholdConfiguration:
    """Test gesture threshold customization."""

    def test_custom_swipe_threshold(self):
        """Test setting custom swipe threshold."""
        detector = GestureDetector()
        detector.swipe_threshold = 100  # Require larger swipe

        detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

        # Move 70px (would normally trigger swipe)
        detector.touch_points = [{'x': 270, 'y': 200, 'id': 0}]
        gesture = detector.process_touch_event('touchend', [])

        # Should not trigger with higher threshold
        assert gesture != 'swipe_right'

    def test_custom_long_press_duration(self):
        """Test setting custom long press duration."""
        detector = GestureDetector()
        detector.long_press_duration = 2.0  # Require longer press

        with patch('time.time') as mock_time:
            mock_time.return_value = 1.0
            detector.process_touch_event('touchstart', [{'x': 200, 'y': 200, 'id': 0}])

            # Hold for 1 second (would normally be long press)
            mock_time.return_value = 2.0
            detector.touch_points = [{'x': 200, 'y': 200, 'id': 0}]
            gesture = detector.process_touch_event('touchend', [])

            # Should not trigger with higher threshold
            assert gesture != 'long_press'
