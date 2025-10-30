"""
Comprehensive tests for qslideshow hotkey system.

Tests cover:
- HotkeyManager initialization and configuration loading
- Key normalization (special keys, modifiers, case handling)
- Action lookup with and without modifiers
- Hotkey mapping updates and removal
- Help text generation
- Tkinter adapter event parsing
- Web adapter event parsing
- Context-specific hotkey handling
"""

import pytest
from unittest.mock import Mock

from upyscripts.qslideshow.hotkeys import (
    HotkeyManager,
    TkinterHotkeyAdapter,
    WebHotkeyAdapter,
)
from upyscripts.qslideshow.config import ConfigManager
from upyscripts.qslideshow.core import SlideshowContext
from pathlib import Path


@pytest.fixture
def basic_config():
    """Create a basic config with common hotkeys."""
    config = ConfigManager()
    config.config = {
        'hotkeys': {
            'common': {
                'navigate_next': ['Right', 'ArrowRight', 'space'],
                'navigate_previous': ['Left', 'ArrowLeft'],
                'toggle_pause': ['p', 'P', 'Return'],
                'toggle_fullscreen': ['f', 'F', 'F11'],
                'quit': ['q', 'Q', 'Escape'],
            },
            'gui': {
                'toggle_always_on_top': 't',
                'open_folder': 'o',
            },
            'web': {
                'toggle_shuffle': 's',
                'toggle_repeat': 'r',
            }
        }
    }
    return config


@pytest.fixture
def config_with_modifiers():
    """Create config with modifier key combinations."""
    config = ConfigManager()
    config.config = {
        'hotkeys': {
            'common': {
                'navigate_next': 'ctrl+n',
                'save': 'ctrl+s',
                'save_as': 'ctrl+shift+s',
                'quit': 'ctrl+q',
            }
        }
    }
    return config


@pytest.fixture
def slideshow_context():
    """Create a minimal slideshow context for testing."""
    return SlideshowContext(
        image_paths=[Path("/tmp/test1.jpg"), Path("/tmp/test2.jpg")],
        speed=3.0
    )


class TestHotkeyManagerInitialization:
    """Test hotkey manager initialization and config loading."""

    def test_basic_initialization(self, basic_config):
        """Test basic initialization."""
        manager = HotkeyManager(basic_config, 'gui')
        assert manager.config == basic_config
        assert manager.context == 'gui'
        assert isinstance(manager.hotkey_map, dict)

    def test_loads_common_hotkeys(self, basic_config):
        """Test common hotkeys are loaded."""
        manager = HotkeyManager(basic_config, 'gui')

        # Common hotkeys should be present
        assert manager.get_action_for_key('Right') == 'navigate_next'
        assert manager.get_action_for_key('Left') == 'navigate_previous'
        assert manager.get_action_for_key('p') == 'toggle_pause'

    def test_loads_context_specific_hotkeys_gui(self, basic_config):
        """Test GUI-specific hotkeys are loaded."""
        manager = HotkeyManager(basic_config, 'gui')

        # GUI-specific hotkeys
        assert manager.get_action_for_key('t') == 'toggle_always_on_top'
        assert manager.get_action_for_key('o') == 'open_folder'

        # Web-specific should NOT be present
        assert manager.get_action_for_key('s') is None
        assert manager.get_action_for_key('r') is None

    def test_loads_context_specific_hotkeys_web(self, basic_config):
        """Test web-specific hotkeys are loaded."""
        manager = HotkeyManager(basic_config, 'web')

        # Web-specific hotkeys
        assert manager.get_action_for_key('s') == 'toggle_shuffle'
        assert manager.get_action_for_key('r') == 'toggle_repeat'

        # GUI-specific should NOT be present
        assert manager.get_action_for_key('t') is None
        assert manager.get_action_for_key('o') is None


class TestKeyNormalization:
    """Test key normalization logic."""

    def test_normalize_special_keys(self, basic_config):
        """Test special key normalization."""
        manager = HotkeyManager(basic_config, 'gui')

        # These should be normalized
        assert manager._normalize_key('space') == ' '
        assert manager._normalize_key('Return') == 'enter'
        assert manager._normalize_key('plus') == '+'
        assert manager._normalize_key('minus') == '-'
        assert manager._normalize_key('equal') == '='

    def test_normalize_arrow_keys(self, basic_config):
        """Test arrow key normalization."""
        manager = HotkeyManager(basic_config, 'gui')

        assert manager._normalize_key('Left') == 'arrowleft'
        assert manager._normalize_key('Right') == 'arrowright'
        assert manager._normalize_key('Up') == 'arrowup'
        assert manager._normalize_key('Down') == 'arrowdown'

    def test_normalize_page_keys(self, basic_config):
        """Test page key normalization."""
        manager = HotkeyManager(basic_config, 'gui')

        assert manager._normalize_key('PageUp') == 'page_up'
        assert manager._normalize_key('PageDown') == 'page_down'

    def test_normalize_escape(self, basic_config):
        """Test escape key normalization."""
        manager = HotkeyManager(basic_config, 'gui')

        assert manager._normalize_key('Escape') == 'esc'

    def test_normalize_case_sensitivity(self, basic_config):
        """Test case handling in normalization."""
        manager = HotkeyManager(basic_config, 'gui')

        # Multi-character keys are lowercased
        assert manager._normalize_key('ARROWLEFT') == 'arrowleft'
        assert manager._normalize_key('F11') == 'f11'

        # Single character keys preserve case
        # (though the lookup might still be case-insensitive)
        assert manager._normalize_key('Q') == 'Q'
        assert manager._normalize_key('q') == 'q'


class TestActionLookup:
    """Test action lookup with various key combinations."""

    def test_lookup_basic_keys(self, basic_config):
        """Test looking up actions for basic keys."""
        manager = HotkeyManager(basic_config, 'gui')

        assert manager.get_action_for_key('p') == 'toggle_pause'
        assert manager.get_action_for_key('P') == 'toggle_pause'
        assert manager.get_action_for_key('f') == 'toggle_fullscreen'
        assert manager.get_action_for_key('q') == 'quit'

    def test_lookup_arrow_keys(self, basic_config):
        """Test looking up arrow key actions."""
        manager = HotkeyManager(basic_config, 'gui')

        # Both 'Left' and 'ArrowLeft' should map to previous
        assert manager.get_action_for_key('Left') == 'navigate_previous'
        assert manager.get_action_for_key('ArrowLeft') == 'navigate_previous'

    def test_lookup_with_modifiers(self, config_with_modifiers):
        """Test looking up actions with modifier keys."""
        manager = HotkeyManager(config_with_modifiers, 'gui')

        # Simple modifier
        assert manager.get_action_for_key('n', ['ctrl']) == 'navigate_next'
        assert manager.get_action_for_key('s', ['ctrl']) == 'save'
        assert manager.get_action_for_key('q', ['ctrl']) == 'quit'

        # Multiple modifiers
        assert manager.get_action_for_key('s', ['ctrl', 'shift']) == 'save_as'

    def test_lookup_modifier_order_independence(self, config_with_modifiers):
        """Test that modifier order doesn't matter."""
        manager = HotkeyManager(config_with_modifiers, 'gui')

        # Both orders should work
        assert manager.get_action_for_key('s', ['ctrl', 'shift']) == 'save_as'
        assert manager.get_action_for_key('s', ['shift', 'ctrl']) == 'save_as'

    def test_lookup_nonexistent_key(self, basic_config):
        """Test looking up a key that doesn't exist."""
        manager = HotkeyManager(basic_config, 'gui')

        assert manager.get_action_for_key('z') is None
        assert manager.get_action_for_key('x', ['ctrl']) is None

    def test_get_keys_for_action(self, basic_config):
        """Test reverse lookup: get keys for an action."""
        manager = HotkeyManager(basic_config, 'gui')

        # navigate_next has multiple keys
        keys = manager.get_keys_for_action('navigate_next')
        assert len(keys) >= 2  # At least 'right' and 'space'

        # Check normalized forms
        key_set = set(keys)
        assert 'arrowright' in key_set or ' ' in key_set


class TestHotkeyMappingUpdates:
    """Test updating and removing hotkey mappings."""

    def test_update_existing_mapping(self, basic_config):
        """Test updating an existing hotkey."""
        manager = HotkeyManager(basic_config, 'gui')

        # Change 'p' from pause to quit
        manager.update_mapping('p', 'quit')
        assert manager.get_action_for_key('p') == 'quit'

    def test_add_new_mapping(self, basic_config):
        """Test adding a completely new mapping."""
        manager = HotkeyManager(basic_config, 'gui')

        # 'x' doesn't exist
        assert manager.get_action_for_key('x') is None

        # Add it
        manager.update_mapping('x', 'quit')
        assert manager.get_action_for_key('x') == 'quit'

    def test_remove_mapping(self, basic_config):
        """Test removing a hotkey mapping."""
        manager = HotkeyManager(basic_config, 'gui')

        # 'p' exists
        assert manager.get_action_for_key('p') == 'toggle_pause'

        # Remove it
        manager.remove_mapping('p')
        assert manager.get_action_for_key('p') is None

    def test_remove_nonexistent_mapping(self, basic_config):
        """Test removing a mapping that doesn't exist (should not error)."""
        manager = HotkeyManager(basic_config, 'gui')

        # Should not raise
        manager.remove_mapping('nonexistent_key')

    def test_get_all_mappings(self, basic_config):
        """Test getting all current mappings."""
        manager = HotkeyManager(basic_config, 'gui')

        mappings = manager.get_all_mappings()
        assert isinstance(mappings, dict)
        assert len(mappings) > 0

        # Should be a copy, not the original
        mappings['test'] = 'test_action'
        assert 'test' not in manager.hotkey_map


class TestHotkeyHandleKeyEvent:
    """Test handle_key_event which executes actions."""

    def test_handle_key_executes_action(self, basic_config, slideshow_context):
        """Test that key event triggers action execution."""
        manager = HotkeyManager(basic_config, 'gui')

        # Press 'p' to toggle pause
        result = manager.handle_key_event('p', slideshow_context=slideshow_context)

        assert result is not None
        assert 'is_paused' in result
        assert slideshow_context.is_paused == True

    def test_handle_key_with_modifiers(self, config_with_modifiers, slideshow_context):
        """Test key event with modifiers."""
        manager = HotkeyManager(config_with_modifiers, 'gui')

        # Ctrl+N for next
        result = manager.handle_key_event('n', ['ctrl'], slideshow_context)

        assert result is not None
        assert 'current_index' in result

    def test_handle_nonexistent_key(self, basic_config, slideshow_context):
        """Test handling a key that has no mapping."""
        manager = HotkeyManager(basic_config, 'gui')

        result = manager.handle_key_event('z', slideshow_context=slideshow_context)
        assert result is None

    def test_handle_key_no_context(self, basic_config):
        """Test handling key without slideshow context."""
        manager = HotkeyManager(basic_config, 'gui')

        # Should not error, just return None
        result = manager.handle_key_event('p')
        assert result is None


class TestHelpTextGeneration:
    """Test help text generation."""

    def test_generate_help_text(self, basic_config):
        """Test help text generation."""
        manager = HotkeyManager(basic_config, 'gui')

        help_text = manager.get_help_text()

        assert isinstance(help_text, str)
        assert len(help_text) > 0

        # Should contain category headings
        assert 'Navigation:' in help_text or 'Playback:' in help_text

        # Should contain action descriptions (not action names)
        assert 'next image' in help_text.lower() or 'pause' in help_text.lower()


class TestTkinterAdapter:
    """Test Tkinter keyboard event adapter."""

    def test_parse_simple_key(self):
        """Test parsing simple key press."""
        event = Mock()
        event.keysym = 'p'
        event.state = 0  # No modifiers

        key, modifiers = TkinterHotkeyAdapter.parse_tkinter_event(event)

        assert key == 'p'
        assert modifiers == []

    def test_parse_key_with_control(self):
        """Test parsing key with Control modifier."""
        event = Mock()
        event.keysym = 's'
        event.state = 0x0004  # Control

        key, modifiers = TkinterHotkeyAdapter.parse_tkinter_event(event)

        assert key == 's'
        assert 'ctrl' in modifiers

    def test_parse_key_with_alt(self):
        """Test parsing key with Alt modifier."""
        event = Mock()
        event.keysym = 'f'
        event.state = 0x0008  # Alt

        key, modifiers = TkinterHotkeyAdapter.parse_tkinter_event(event)

        assert key == 'f'
        assert 'alt' in modifiers

    def test_parse_key_with_shift(self):
        """Test parsing key with Shift modifier."""
        event = Mock()
        event.keysym = 's'
        event.state = 0x0001  # Shift

        key, modifiers = TkinterHotkeyAdapter.parse_tkinter_event(event)

        assert key == 's'
        assert 'shift' in modifiers

    def test_parse_key_with_meta(self):
        """Test parsing key with Meta/Command modifier."""
        event = Mock()
        event.keysym = 'q'
        event.state = 0x0040000  # Meta

        key, modifiers = TkinterHotkeyAdapter.parse_tkinter_event(event)

        assert key == 'q'
        assert 'meta' in modifiers

    def test_parse_key_with_multiple_modifiers(self):
        """Test parsing key with multiple modifiers."""
        event = Mock()
        event.keysym = 's'
        event.state = 0x0004 | 0x0001  # Control + Shift

        key, modifiers = TkinterHotkeyAdapter.parse_tkinter_event(event)

        assert key == 's'
        assert 'ctrl' in modifiers
        assert 'shift' in modifiers
        assert len(modifiers) == 2


class TestWebAdapter:
    """Test Web keyboard event adapter."""

    def test_parse_simple_key(self):
        """Test parsing simple key press."""
        event_data = {
            'key': 'p',
            'ctrlKey': False,
            'altKey': False,
            'shiftKey': False,
            'metaKey': False
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == 'p'
        assert modifiers == []

    def test_parse_key_with_control(self):
        """Test parsing key with Ctrl."""
        event_data = {
            'key': 's',
            'ctrlKey': True,
            'altKey': False,
            'shiftKey': False,
            'metaKey': False
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == 's'
        assert 'ctrl' in modifiers

    def test_parse_key_with_alt(self):
        """Test parsing key with Alt."""
        event_data = {
            'key': 'f',
            'ctrlKey': False,
            'altKey': True,
            'shiftKey': False,
            'metaKey': False
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == 'f'
        assert 'alt' in modifiers

    def test_parse_key_with_shift(self):
        """Test parsing key with Shift."""
        event_data = {
            'key': 's',
            'ctrlKey': False,
            'altKey': False,
            'shiftKey': True,
            'metaKey': False
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == 's'
        assert 'shift' in modifiers

    def test_parse_key_with_meta(self):
        """Test parsing key with Meta/Command."""
        event_data = {
            'key': 'q',
            'ctrlKey': False,
            'altKey': False,
            'shiftKey': False,
            'metaKey': True
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == 'q'
        assert 'meta' in modifiers

    def test_parse_key_with_multiple_modifiers(self):
        """Test parsing key with multiple modifiers."""
        event_data = {
            'key': 's',
            'ctrlKey': True,
            'altKey': False,
            'shiftKey': True,
            'metaKey': False
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == 's'
        assert 'ctrl' in modifiers
        assert 'shift' in modifiers
        assert len(modifiers) == 2

    def test_parse_arrow_key(self):
        """Test parsing arrow keys from web."""
        event_data = {
            'key': 'ArrowRight',
            'ctrlKey': False,
            'altKey': False,
            'shiftKey': False,
            'metaKey': False
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == 'ArrowRight'
        assert modifiers == []

    def test_parse_missing_key(self):
        """Test parsing event with missing key field."""
        event_data = {
            'ctrlKey': True
        }

        key, modifiers = WebHotkeyAdapter.parse_web_event(event_data)

        assert key == ''
        assert 'ctrl' in modifiers
