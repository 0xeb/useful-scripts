#!/usr/bin/env python3
"""
Hotkey management for qslideshow.
Maps keyboard inputs to action names.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List, Optional, Callable, Any
from .config import ConfigManager
from .actions import action_registry

if TYPE_CHECKING:
    from .core import SlideshowContext


class HotkeyManager:
    """Manages hotkey to action mappings."""
    
    def __init__(self, config: ConfigManager, context: str):
        """
        Initialize hotkey manager.
        
        Args:
            config: Configuration manager instance
            context: 'gui' or 'web'
        """
        self.config = config
        self.context = context
        self.hotkey_map: Dict[str, str] = {}  # key -> action_name
        self._build_hotkey_map()
    
    def _build_hotkey_map(self):
        """Build the hotkey to action mapping from config."""
        # Load common hotkeys
        common_hotkeys = self.config.get('hotkeys.common', {})
        for action_name, keys in common_hotkeys.items():
            if isinstance(keys, str):
                keys = [keys]
            elif not isinstance(keys, list):
                continue
            for key in keys:
                self.hotkey_map[self._normalize_key(key)] = action_name
        
        # Load context-specific hotkeys
        context_hotkeys = self.config.get(f'hotkeys.{self.context}', {})
        for action_name, keys in context_hotkeys.items():
            if isinstance(keys, str):
                keys = [keys]
            elif not isinstance(keys, list):
                continue
            for key in keys:
                self.hotkey_map[self._normalize_key(key)] = action_name
    
    def _normalize_key(self, key: str) -> str:
        """Normalize key string for consistent mapping."""
        # Handle special cases
        key_map = {
            'space': ' ',
            'Return': 'Enter',
            'plus': '+',
            'minus': '-',
            'equal': '=',
            'Left': 'ArrowLeft',
            'Right': 'ArrowRight',
            'Up': 'ArrowUp',
            'Down': 'ArrowDown',
            'PageUp': 'Page_Up',
            'PageDown': 'Page_Down',
            'Escape': 'Esc'
        }
        
        # First check if it's a special key
        normalized = key_map.get(key, key)
        
        # Convert to lowercase for case-insensitive matching
        # unless it's a single uppercase letter (like 'O' for reveal file)
        if len(normalized) > 1:
            normalized = normalized.lower()
        
        return normalized
    
    def get_action_for_key(self, key: str, modifiers: Optional[List[str]] = None) -> Optional[str]:
        """
        Get action name for a given key.
        
        Args:
            key: The key pressed
            modifiers: List of modifier keys held (ctrl, alt, shift, meta)
        """
        # Build the full key string with modifiers
        if modifiers:
            # Sort modifiers for consistent ordering
            sorted_modifiers = sorted(m.lower() for m in modifiers if m)
            if sorted_modifiers:
                key_with_mods = '+'.join(sorted_modifiers + [key])
                normalized = self._normalize_key(key_with_mods)
                if normalized in self.hotkey_map:
                    return self.hotkey_map[normalized]
        
        # Try without modifiers
        normalized = self._normalize_key(key)
        return self.hotkey_map.get(normalized)
    
    def get_keys_for_action(self, action_name: str) -> List[str]:
        """Get all keys mapped to an action."""
        return [key for key, action in self.hotkey_map.items() if action == action_name]
    
    def update_mapping(self, key: str, action_name: str):
        """Update or add a hotkey mapping."""
        normalized = self._normalize_key(key)
        self.hotkey_map[normalized] = action_name
    
    def remove_mapping(self, key: str):
        """Remove a hotkey mapping."""
        normalized = self._normalize_key(key)
        if normalized in self.hotkey_map:
            del self.hotkey_map[normalized]
    
    def get_all_mappings(self) -> Dict[str, str]:
        """Get all current hotkey mappings."""
        return self.hotkey_map.copy()
    
    def handle_key_event(self, key: str, modifiers: Optional[List[str]] = None, 
                         slideshow_context: Optional[SlideshowContext] = None) -> Optional[Dict]:
        """
        Handle a key event and execute the associated action.
        
        Args:
            key: The key pressed
            modifiers: List of modifier keys held
            slideshow_context: The slideshow context to pass to actions
            
        Returns:
            Result dictionary from action execution, or None if no action
        """
        action_name = self.get_action_for_key(key, modifiers)
        if not action_name:
            return None
        
        action = action_registry.get(action_name)
        if not action:
            return None
        
        if not action.can_execute(self.context):
            return None
        
        if slideshow_context:
            return action.execute(slideshow_context)
        return None
    
    def get_help_text(self) -> str:
        """Generate help text showing all hotkey mappings."""
        # Group actions by category
        categories = {
            'Navigation': ['navigate_next', 'navigate_previous'],
            'Playback': ['toggle_pause', 'toggle_repeat', 'toggle_shuffle'],
            'Display': ['toggle_fullscreen', 'toggle_always_on_top'],
            'Speed': ['increase_speed', 'decrease_speed'],
            'File Operations': ['open_folder', 'reveal_file', 'remember', 'note'],
            'Tools': [],
            'Other': []
        }
        
        # Collect tool actions
        for action_name in self.hotkey_map.values():
            if action_name.startswith('external_tool_'):
                categories['Tools'].append(action_name)
            elif action_name not in sum(categories.values(), []):
                categories['Other'].append(action_name)
        
        help_lines = []
        for category, action_names in categories.items():
            if not action_names:
                continue
            
            help_lines.append(f"\n{category}:")
            for action_name in action_names:
                keys = self.get_keys_for_action(action_name)
                if keys:
                    action = action_registry.get(action_name)
                    if action:
                        key_str = ', '.join(keys)
                        help_lines.append(f"  {key_str:<20} {action.description}")
        
        return '\n'.join(help_lines)


class TkinterHotkeyAdapter:
    """Adapter for tkinter keyboard events."""
    
    @staticmethod
    def parse_tkinter_event(event) -> tuple[str, List[str]]:
        """
        Parse a tkinter keyboard event.
        
        Returns:
            Tuple of (key, modifiers)
        """
        key = event.keysym
        
        # Extract modifiers
        modifiers = []
        if event.state & 0x0004:  # Control
            modifiers.append('ctrl')
        if event.state & 0x0008 or event.state & 0x0080:  # Alt
            modifiers.append('alt')
        if event.state & 0x0001:  # Shift
            modifiers.append('shift')
        if event.state & 0x0040000:  # Meta/Command (Mac)
            modifiers.append('meta')
        
        return key, modifiers


class WebHotkeyAdapter:
    """Adapter for web JavaScript keyboard events."""
    
    @staticmethod
    def parse_web_event(event_data: Dict) -> tuple[str, List[str]]:
        """
        Parse a web keyboard event data.
        
        Args:
            event_data: Dictionary with keys 'key', 'ctrlKey', 'altKey', 'shiftKey', 'metaKey'
            
        Returns:
            Tuple of (key, modifiers)
        """
        key = event_data.get('key', '')
        
        # Extract modifiers
        modifiers = []
        if event_data.get('ctrlKey'):
            modifiers.append('ctrl')
        if event_data.get('altKey'):
            modifiers.append('alt')
        if event_data.get('shiftKey'):
            modifiers.append('shift')
        if event_data.get('metaKey'):
            modifiers.append('meta')
        
        return key, modifiers