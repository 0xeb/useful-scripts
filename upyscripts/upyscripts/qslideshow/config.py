#!/usr/bin/env python3
"""
Configuration management for qslideshow.
Handles loading and merging configuration from multiple sources.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
import os


class ConfigManager:
    """Manages configuration loading and merging."""
    
    DEFAULT_CONFIG_NAMES = ['qslideshow.yaml', 'qslideshow.yml']
    
    # Single source of truth: Default configuration as YAML string
    DEFAULT_CONFIG_YAML = """# qslideshow configuration file
# This is the default configuration that demonstrates all available options.
# Place this file in your project directory or use --config to specify location.

# General slideshow settings
slideshow:
  speed: 3.0  # seconds between slides
  repeat: false  # loop back to first image after last
  repeat_mode: "fixed"  # Repeat modes: fixed | shuffle | shuffle-each
  # - fixed: repeat with same order
  # - shuffle: shuffle once at start, repeat that order
  # - shuffle-each: reshuffle on each repeat cycle
  shuffle: false  # Initial shuffle on start
  fit_mode: shrink  # How images fit: shrink | original
  always_on_top: false  # Keep window above all others
  paused_on_start: false  # Start slideshow paused
  status_format: null  # Custom status format, e.g., "{img_idx}/{img_total} - {img_name}"
  remember_file: "remember.txt"  # File to save remembered images
  notes_file: "slideshow_notes.txt"  # File for custom notes

# Image discovery settings
images:
  recursive: false  # Search subdirectories for images
  exclude_patterns: []  # Patterns to exclude, e.g., ["*.tmp", "thumbnail_*"]
  extensions: []  # Additional extensions beyond defaults (.jpg, .png, etc.)
  # Example: [".webp", ".avif", ".heic"]

# GUI-specific settings
gui:
  initial_size: "800x600"  # Initial window size
  background_color: "#000000"  # Background color (hex)

# Web server settings
web:
  port: 8000  # Server port
  host: "0.0.0.0"  # Server host (0.0.0.0 for all interfaces)
  enable_wake_lock: true  # Prevent screen sleep in browser
  enable_pwa: true  # Enable Progressive Web App features
  dev_mode: false  # Disable caching for development

# Gallery mode settings (web mode only)
gallery:
  enabled: false  # Enable gallery view mode
  grid: null  # Grid size as [rows, cols] tuple, or null for auto/responsive
  # Examples: [4, 5] for 4 rows and 5 columns, null for automatic sizing
  thumbnail_size: [200, 200]  # Thumbnail dimensions [width, height] in pixels

# External tools configuration
external_tools:
  base_name: "tool"  # Base name for tool scripts
  search_dir: "."  # Directory to search for tools (default: current dir)
  
  # Tool discovery looks for scripts matching these patterns:
  # Numeric IDs (0-99): tool0, tool1, ..., tool99
  # Alphabetic IDs (a-z): toola, toolb, ..., toolz
  # With extensions: .sh, .py, .bat, .cmd, .exe, .ps1, .rb, .pl
  #
  # Environment variables passed to all tools (QSS_ prefix):
  # QSS_IMG_PATH - Full path to current image
  # QSS_IMG_INDEX - Current index (1-based)
  # QSS_IMG_NAME - Image filename
  # QSS_IMG_TOTAL - Total number of images
  # QSS_TOOL_ID - The ID of the tool being executed
  # ... and all other template variables

# File operation settings
file_operations:
  enable_trash: true  # Use trash instead of permanent delete
  trash_dir: ".trash"  # Trash directory (relative to image directory)
  enable_undo: true  # Enable undo/redo functionality
  max_undo_history: 50  # Maximum undo history size
  confirm_delete: false  # Ask confirmation before delete (false since we have trash)
  auto_cleanup_days: 30  # Auto-remove trash items older than N days

# Hotkey mappings - keyboard shortcuts
hotkeys:
  # Common hotkeys (both GUI and Web)
  common:
    navigate_next: 
      - "Right"  # Right arrow key
      - "PageDown"  # Page Down key
    navigate_previous:
      - "Left"  # Left arrow key
      - "PageUp"  # Page Up key
    toggle_pause:
      - "space"  # Spacebar
      - "Return"  # Enter key
    toggle_fullscreen:
      - "f"  # F key
      - "F11"  # F11 key
    toggle_repeat: "r"  # R key
    toggle_shuffle: "s"  # S key
    increase_speed: 
      - "plus"  # Plus key
      - "equal"  # Equal key (for keyboards without numpad)
    decrease_speed: "minus"  # Minus key
    
  # GUI-specific hotkeys
  gui:
    quit:
      - "Escape"  # Escape key
      - "q"  # Q key
    toggle_always_on_top: "t"  # T key
    open_folder: "o"  # O key - open parent folder in file manager
    reveal_file: "O"  # Shift+O - reveal/highlight file in file manager
    remember: "m"  # M key - mark/remember current image
    note: "n"  # N key - add note about current image
    
    # Default mappings for external tools 0-9 (on number keys)
    external_tool_0: "0"
    external_tool_1: "1"
    external_tool_2: "2"
    external_tool_3: "3"
    external_tool_4: "4"
    external_tool_5: "5"
    external_tool_6: "6"
    external_tool_7: "7"
    external_tool_8: "8"
    external_tool_9: "9"
    
    # Extended tool mappings (examples - uncomment to use)
    # external_tool_10: "F1"  # Map tool 10 to F1
    # external_tool_11: "F2"  # Map tool 11 to F2
    # external_tool_20: "ctrl+0"  # Map tool 20 to Ctrl+0
    # external_tool_a: "shift+a"  # Map alphabetic tool 'a' to Shift+A
    # undo: "ctrl+z"  # Undo last action
    # redo: "ctrl+y"  # Redo last undone action
    
  # Web-specific hotkeys
  web:
    toggle_help: "h"  # H key - show help modal
    toggle_picture_in_picture: "t"  # T key - toggle PiP mode
    toggle_gallery_mode: "g"  # G key - toggle between gallery and slideshow views
    close_modal:
      - "Escape"  # Escape key
      - "q"  # Q key

# Touch gesture mappings (web interface)
# Gestures can trigger ANY action, not just navigation
gestures:
  # Common gestures (all contexts)
  common:
    swipe_left: "navigate_next"  # Swipe left to go to next image
    swipe_right: "navigate_previous"  # Swipe right to go to previous
    double_tap: "toggle_pause"  # Double tap to pause/resume
    long_press: "show_menu"  # Long press to show context menu
    swipe_up: "increase_speed"  # Swipe up for slower transitions
    swipe_down: "decrease_speed"  # Swipe down for faster transitions
    
  # Web-specific gestures
  web:
    pinch_out: "zoom_in"  # Pinch out to zoom in
    pinch_in: "zoom_out"  # Pinch in to zoom out
    two_finger_swipe_left: "external_tool_0"  # Two-finger swipe runs tool 0
    two_finger_swipe_right: "external_tool_1"  # Two-finger swipe runs tool 1
    three_finger_tap: "toggle_fullscreen"  # Three-finger tap for fullscreen
    
    # Extended gesture mappings (examples - uncomment to use)
    # two_finger_swipe_up: "external_tool_2"
    # two_finger_swipe_down: "external_tool_3"
    # rotate_clockwise: "rotate_90"  # Rotate gesture to rotate image
    # rotate_counter_clockwise: "rotate_270"
    # shake: "shuffle"  # Shake device to shuffle images

# Template variables available for status format and external tools:
# {img_idx} - Current image index (1-based)
# {img_total} - Total number of images
# {img_name} - Image filename with extension
# {base_name} - Image filename without extension
# {extension} - Image file extension (with dot)
# {img_path} - Full image file path
# {full_path} - Full absolute image file path
# {img_size} - Image dimensions (WxH)
# {file_size} - File size in bytes
# {img_size_mb} - File size in MB
# {speed} - Current slide speed
# {paused} - Pause state (True/False)
# {repeat} - Repeat mode (True/False)
# {repeat_count} - Number of times repeated
# {always_on_top} - Always on top setting (True/False)
# {shuffle} - Shuffle mode (True/False)
# {progress_percent} - Progress through slideshow as percentage
"""
    
    def __init__(self):
        self.config: Dict[str, Any] = self._get_default_config()
        self.config_path: Optional[Path] = None
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Parse default configuration from YAML string."""
        try:
            return yaml.safe_load(self.DEFAULT_CONFIG_YAML) or {}
        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse default config: {e}")
            # Fallback to minimal config if YAML parsing fails
            return {
                "slideshow": {"speed": 3.0, "repeat": False},
                "images": {"recursive": False},
                "gui": {},
                "web": {"port": 8000, "host": "0.0.0.0"},
                "hotkeys": {"common": {}, "gui": {}, "web": {}},
                "gestures": {"common": {}, "web": {}}
            }
    
    def find_config_file(self, explicit_path: Optional[str] = None) -> Optional[Path]:
        """Find configuration file in order of precedence."""
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                return path
            else:
                raise FileNotFoundError(f"Config file not found: {explicit_path}")
        
        # Check current directory
        for name in self.DEFAULT_CONFIG_NAMES:
            path = Path.cwd() / name
            if path.exists():
                return path
        
        # Check user config directory
        config_dir = Path.home() / '.useful_scripts' / 'qslideshow'
        for name in self.DEFAULT_CONFIG_NAMES:
            path = config_dir / name
            if path.exists():
                return path
        
        # Check system config directory (Unix-like systems)
        if os.name != 'nt':  # Not Windows
            system_config_dir = Path('/etc/useful_scripts/qslideshow')
            for name in self.DEFAULT_CONFIG_NAMES:
                path = system_config_dir / name
                if path.exists():
                    return path
        
        return None
    
    def load_config(self, config_path: Optional[str] = None) -> None:
        """Load configuration from file."""
        path = self.find_config_file(config_path)
        if not path:
            return  # Use defaults
        
        self.config_path = path
        
        try:
            with open(path, 'r') as f:
                if path.suffix in ['.yaml', '.yml']:
                    user_config = yaml.safe_load(f) or {}
                else:
                    raise ValueError(f"Unsupported config format: {path.suffix}")
        except Exception as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            return
        
        # Deep merge user config with defaults
        self.config = self._deep_merge(self.config, user_config)
    
    def _deep_merge(self, base: Dict, overlay: Dict) -> Dict:
        """Deep merge overlay dict into base dict."""
        result = base.copy()
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get config value by dot-notation path (e.g., 'slideshow.speed')."""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def set(self, key_path: str, value: Any) -> None:
        """Set config value by dot-notation path."""
        keys = key_path.split('.')
        target = self.config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
    
    def update_from_args(self, args: Any) -> None:
        """Update configuration from command-line arguments."""
        # Map CLI arguments to config paths
        arg_mapping = {
            'speed': 'slideshow.speed',
            'repeat': 'slideshow.repeat',
            'fit_mode': 'slideshow.fit_mode',
            'status': 'slideshow.status_format',
            'always_on_top': 'slideshow.always_on_top',
            'shuffle': 'slideshow.shuffle',
            'paused': 'slideshow.paused_on_start',
            'recursive': 'images.recursive',
            'exclude': 'images.exclude_patterns',
            'port': 'web.port',
            'host': 'web.host',
            'external_tools': 'external_tools.base_name',
            'dev_mode': 'web.dev_mode'
        }

        for arg_name, config_path in arg_mapping.items():
            if hasattr(args, arg_name):
                value = getattr(args, arg_name)
                if value is not None:
                    self.set(config_path, value)

        # Handle gallery-specific arguments
        if hasattr(args, 'web_gallery'):
            web_gallery = getattr(args, 'web_gallery')
            if web_gallery is not None:
                # If --web-gallery is provided, enable gallery mode
                self.set('gallery.enabled', True)
                # If --web-gallery has a value (grid size), use it
                if web_gallery is not True:  # Not just a flag
                    self.set('gallery.grid', web_gallery)

        # Override grid if --web-gallery-grid is explicitly provided
        if hasattr(args, 'web_gallery_grid'):
            web_gallery_grid = getattr(args, 'web_gallery_grid')
            if web_gallery_grid is not None:
                self.set('gallery.grid', web_gallery_grid)

        # Handle thumbnail size
        if hasattr(args, 'web_gallery_thumbnail_size'):
            thumb_size = getattr(args, 'web_gallery_thumbnail_size')
            if thumb_size is not None:
                self.set('gallery.thumbnail_size', thumb_size)
    
    def get_hotkeys(self, context: str = 'common') -> Dict[str, Any]:
        """Get hotkey configuration for a specific context."""
        common = self.get('hotkeys.common', {})
        specific = self.get(f'hotkeys.{context}', {})
        # Merge common and context-specific hotkeys
        return {**common, **specific}
    
    def get_gestures(self, context: str = 'common') -> Dict[str, str]:
        """Get gesture configuration for a specific context."""
        common = self.get('gestures.common', {})
        specific = self.get(f'gestures.{context}', {})
        # Merge common and context-specific gestures
        return {**common, **specific}
    
    def save_config(self, path: Optional[Path] = None) -> None:
        """Save current configuration to file."""
        save_path = path or self.config_path
        if not save_path:
            save_path = Path.cwd() / self.DEFAULT_CONFIG_NAMES[0]
        
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(save_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
    
    def generate_default_config_file(self, path: Path = None) -> Path:
        """Generate a default configuration file with comments."""
        if not path:
            path = Path.cwd() / "qslideshow.yaml"
        
        # Write the default YAML content to file
        with open(path, 'w') as f:
            f.write(self.DEFAULT_CONFIG_YAML)
        
        return path