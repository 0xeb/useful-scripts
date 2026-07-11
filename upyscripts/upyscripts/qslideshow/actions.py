#!/usr/bin/env python3
"""
Action system for qslideshow.
Provides a unified way to define and execute actions across GUI and Web interfaces.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional, List, Callable
from enum import Enum
from pathlib import Path
import os
import subprocess
import platform
import shutil
import json
import random
from datetime import datetime

from .repeat_modes import RepeatMode

if TYPE_CHECKING:
    from .core import SlideshowContext


class ActionContext(Enum):
    """Where an action can be executed."""
    GUI = "gui"
    WEB = "web"
    BOTH = "both"


class Action(ABC):
    """Base class for all actions."""
    
    def __init__(self, name: str, description: str, context: ActionContext = ActionContext.BOTH):
        self.name = name
        self.description = description
        self.context = context
    
    @abstractmethod
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        """Execute the action. Returns result dictionary."""
        pass
    
    def can_execute(self, context_type: str) -> bool:
        """Check if action can execute in given context."""
        return (self.context == ActionContext.BOTH or 
                self.context.value == context_type)


class ActionRegistry:
    """Registry for all available actions."""
    
    def __init__(self):
        self._actions: Dict[str, Action] = {}
    
    def register(self, action: Action) -> None:
        """Register an action."""
        self._actions[action.name] = action
    
    def get(self, name: str) -> Optional[Action]:
        """Get action by name."""
        return self._actions.get(name)
    
    def list_actions(self, context: Optional[str] = None) -> List[Action]:
        """List all actions, optionally filtered by context."""
        if context:
            return [a for a in self._actions.values() if a.can_execute(context)]
        return list(self._actions.values())


# Global registry
action_registry = ActionRegistry()


def _get_total_images(slideshow_context: SlideshowContext) -> int:
    """Get total image count, using image_order in web mode."""
    return (len(slideshow_context.image_order)
            if hasattr(slideshow_context, 'image_order')
            else len(slideshow_context.image_paths))


def _skip_filtered(slideshow_context: SlideshowContext, direction: int) -> None:
    """Advance past images rejected by the filter script (if any).

    Loop protection: stops after checking all images to prevent infinite loop.
    """
    filter_runner = getattr(slideshow_context, 'filter_runner', None)
    if not filter_runner:
        return

    total = _get_total_images(slideshow_context)
    if total == 0:
        return

    for _ in range(total):
        if filter_runner.should_display(slideshow_context):
            return  # current image passes filter
        # Skip: advance in the given direction
        slideshow_context.current_index += direction
        if slideshow_context.current_index >= total:
            if slideshow_context.repeat:
                slideshow_context.current_index = 0
                slideshow_context.repeat_count += 1
            else:
                slideshow_context.current_index = total - 1
                return  # hit end, stop
        elif slideshow_context.current_index < 0:
            if slideshow_context.repeat:
                slideshow_context.current_index = total - 1
            else:
                slideshow_context.current_index = 0
                return  # hit start, stop
    # All images filtered — show current one anyway (loop protection)


# Navigation Actions
class NavigateNextAction(Action):
    """Navigate to the next image in the slideshow."""

    def __init__(self):
        super().__init__("navigate_next", "Go to next image", ActionContext.BOTH)

    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        slideshow_context.current_index += 1

        total_images = _get_total_images(slideshow_context)

        if slideshow_context.current_index >= total_images:
            if slideshow_context.repeat:
                if slideshow_context.repeat_mode.should_shuffle_on_cycle():
                    order = (slideshow_context.image_order
                             if hasattr(slideshow_context, 'image_order')
                             else slideshow_context.image_paths)
                    random.shuffle(order)
                slideshow_context.current_index = 0
                slideshow_context.repeat_count += 1
            else:
                slideshow_context.current_index = total_images - 1

        _skip_filtered(slideshow_context, direction=1)
        return {"current_index": slideshow_context.current_index}


class NavigatePreviousAction(Action):
    """Navigate to the previous image in the slideshow."""

    def __init__(self):
        super().__init__("navigate_previous", "Go to previous image", ActionContext.BOTH)

    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        slideshow_context.current_index -= 1

        total_images = _get_total_images(slideshow_context)

        if slideshow_context.current_index < 0:
            if slideshow_context.repeat:
                slideshow_context.current_index = total_images - 1
            else:
                slideshow_context.current_index = 0

        _skip_filtered(slideshow_context, direction=-1)
        return {"current_index": slideshow_context.current_index}


# Control Actions
class TogglePauseAction(Action):
    """Toggle pause/resume of the slideshow."""
    
    def __init__(self):
        super().__init__("toggle_pause", "Pause/resume slideshow", ActionContext.BOTH)
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        slideshow_context.is_paused = not slideshow_context.is_paused
        return {"is_paused": slideshow_context.is_paused}


class ToggleFullscreenAction(Action):
    """Toggle fullscreen mode."""
    
    def __init__(self):
        super().__init__("toggle_fullscreen", "Enter/exit fullscreen", ActionContext.BOTH)
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        # GUI implementations will handle the actual fullscreen toggle
        # This just tracks the state
        is_fullscreen = kwargs.get('is_fullscreen', False)
        new_state = not is_fullscreen
        return {"is_fullscreen": new_state, "action": "toggle_fullscreen"}


class ToggleRepeatAction(Action):
    """Toggle repeat mode for the slideshow."""
    
    def __init__(self):
        super().__init__("toggle_repeat", "Toggle loop mode", ActionContext.BOTH)
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        modes = list(RepeatMode)
        current = modes.index(slideshow_context.repeat_mode)
        slideshow_context.repeat_mode = modes[(current + 1) % len(modes)]

        if slideshow_context.repeat_mode.should_shuffle_on_start():
            order = (slideshow_context.image_order
                     if hasattr(slideshow_context, 'image_order')
                     else slideshow_context.image_paths)
            current_item = order[slideshow_context.current_index] if order else None
            random.shuffle(order)
            if current_item is not None:
                slideshow_context.current_index = order.index(current_item)

        return {
            "repeat": slideshow_context.repeat,
            "repeat_mode": slideshow_context.repeat_mode.value,
        }


class ToggleShuffleAction(Action):
    """Toggle shuffle mode for the slideshow."""

    def __init__(self):
        super().__init__("toggle_shuffle", "Toggle shuffle mode", ActionContext.BOTH)

    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        import random
        slideshow_context.shuffle = not slideshow_context.shuffle

        # Check if we're in web mode (has image_order attribute)
        if hasattr(slideshow_context, 'image_order'):
            # Web mode: work with image_order, not image_paths
            if slideshow_context.shuffle:
                # Remember current image by getting its actual index
                if slideshow_context.current_index < len(slideshow_context.image_order):
                    current_real_idx = slideshow_context.image_order[slideshow_context.current_index]
                else:
                    current_real_idx = None

                # Shuffle the order using global random state
                random.shuffle(slideshow_context.image_order)

                # Find where the current image ended up
                if current_real_idx is not None:
                    try:
                        slideshow_context.current_index = slideshow_context.image_order.index(current_real_idx)
                    except ValueError:
                        slideshow_context.current_index = 0
                else:
                    slideshow_context.current_index = 0
            else:
                # Turn off shuffle: reset to sequential order
                if slideshow_context.current_index < len(slideshow_context.image_order):
                    current_real_idx = slideshow_context.image_order[slideshow_context.current_index]
                else:
                    current_real_idx = 0

                # Reset to sequential
                slideshow_context.image_order = list(range(len(slideshow_context.image_paths)))

                # Current index is now the real index
                slideshow_context.current_index = current_real_idx

            return {
                "shuffle": slideshow_context.shuffle,
                "current_index": slideshow_context.current_index
            }
        else:
            # GUI mode: work with image_paths directly
            if slideshow_context.shuffle:
                random.shuffle(slideshow_context.image_paths)
            else:
                slideshow_context.image_paths = slideshow_context.original_image_paths.copy()
            return {"shuffle": slideshow_context.shuffle}


class ToggleAlwaysOnTopAction(Action):
    """Toggle always-on-top window mode."""

    def __init__(self):
        super().__init__("toggle_always_on_top", "Toggle window always on top", ActionContext.GUI)

    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        slideshow_context.always_on_top = not slideshow_context.always_on_top
        return {"always_on_top": slideshow_context.always_on_top}


class ToggleGalleryModeAction(Action):
    """Toggle between gallery and slideshow views (web mode only)."""

    def __init__(self):
        super().__init__("toggle_gallery_mode", "Toggle gallery/slideshow view", ActionContext.WEB)

    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        # Check if gallery is enabled for this session
        if not getattr(slideshow_context, 'gallery_enabled', False):
            return {
                "success": False,
                "error": "Gallery mode not enabled",
                "gallery_mode_active": False
            }

        # Toggle gallery_mode_active
        slideshow_context.gallery_mode_active = not getattr(slideshow_context, 'gallery_mode_active', False)

        return {
            "gallery_mode_active": slideshow_context.gallery_mode_active,
            "success": True
        }


# Speed Control Actions
class IncreaseSpeedAction(Action):
    """Increase the slideshow speed (slower transitions)."""
    
    def __init__(self):
        super().__init__("increase_speed", "Slower transitions (add 1s)", ActionContext.BOTH)
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        slideshow_context.speed_seconds = min(60.0, slideshow_context.speed_seconds + 1.0)
        return {"speed": slideshow_context.speed_seconds}


class DecreaseSpeedAction(Action):
    """Decrease the slideshow speed (faster transitions)."""
    
    def __init__(self):
        super().__init__("decrease_speed", "Faster transitions (subtract 1s)", ActionContext.BOTH)
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        slideshow_context.speed_seconds = max(0.5, slideshow_context.speed_seconds - 1.0)
        return {"speed": slideshow_context.speed_seconds}


# File Manager Actions
class OpenFolderAction(Action):
    """Open the parent folder of current image in system file manager."""
    
    def __init__(self):
        super().__init__(
            "open_folder",
            "Open parent folder in file manager",
            ActionContext.GUI
        )
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        if not slideshow_context.image_paths:
            return {"error": "No images in slideshow"}
        
        current_path = slideshow_context.image_paths[slideshow_context.current_index]
        parent_folder = current_path.parent
        
        try:
            system = platform.system()
            
            if system == "Windows":
                subprocess.run(["explorer", str(parent_folder)])
            elif system == "Darwin":  # macOS
                subprocess.run(["open", str(parent_folder)])
            elif system == "Linux":
                # Try common file managers in order
                for cmd in ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm"]:
                    try:
                        subprocess.run([cmd, str(parent_folder)])
                        break
                    except FileNotFoundError:
                        continue
                else:
                    return {"error": "No file manager found"}
            else:
                return {"error": f"Unsupported platform: {system}"}
                
            return {"opened": str(parent_folder), "platform": system}
            
        except Exception as e:
            return {"error": f"Failed to open folder: {e}"}


class RevealFileAction(Action):
    """Reveal/select the current image in system file manager."""
    
    def __init__(self):
        super().__init__(
            "reveal_file",
            "Reveal current file in file manager",
            ActionContext.GUI
        )
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        if not slideshow_context.image_paths:
            return {"error": "No images in slideshow"}
        
        file_path = slideshow_context.image_paths[slideshow_context.current_index]
        
        try:
            system = platform.system()
            
            if system == "Windows":
                # Windows: use explorer with /select flag to highlight the file
                subprocess.run(["explorer", "/select,", str(file_path)])
            elif system == "Darwin":  # macOS
                # macOS: use open -R to reveal in Finder
                subprocess.run(["open", "-R", str(file_path)])
            elif system == "Linux":
                # Linux: most file managers don't have a standard "reveal" option
                parent_folder = file_path.parent
                for cmd in ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm"]:
                    try:
                        # Some file managers support selecting
                        if cmd == "nautilus":
                            subprocess.run([cmd, "--select", str(file_path)])
                        else:
                            subprocess.run([cmd, str(parent_folder)])
                        break
                    except FileNotFoundError:
                        continue
                else:
                    return {"error": "No file manager found"}
            else:
                return {"error": f"Unsupported platform: {system}"}
                
            return {"revealed": str(file_path), "platform": system}
            
        except Exception as e:
            return {"error": f"Failed to reveal file: {e}"}


# Memory Actions
class RememberAction(Action):
    """Remember/note the current image by appending to a file."""
    
    def __init__(self, remember_file: Path = None):
        super().__init__(
            "remember",
            "Save current image path to remember file",
            ActionContext.BOTH
        )
        self.remember_file = remember_file or Path("remember.txt")
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        if not slideshow_context.image_paths:
            return {"error": "No images in slideshow"}
        
        try:
            # Create remember file if it doesn't exist
            self.remember_file.touch(exist_ok=True)
            
            # Append current image info with timestamp
            with open(self.remember_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                image_path = slideshow_context.image_paths[slideshow_context.current_index]
                
                # Write detailed info
                f.write(f"[{timestamp}] {image_path}\n")
                
                # Optionally add more context
                f.write(f"  Index: {slideshow_context.current_index + 1}/{len(slideshow_context.image_paths)}\n")
                if hasattr(slideshow_context, 'repeat_count') and slideshow_context.repeat_count > 0:
                    f.write(f"  Repeat: {slideshow_context.repeat_count}\n")
                
                # Add a blank line for readability
                f.write("\n")
            
            return {
                "remembered": str(image_path),
                "file": str(self.remember_file),
                "timestamp": timestamp
            }
            
        except Exception as e:
            return {"error": f"Failed to save to remember file: {e}"}


class NoteAction(Action):
    """Add a custom note about the current image."""
    
    def __init__(self, notes_file: Path = None):
        super().__init__(
            "note",
            "Add custom note about current image",
            ActionContext.BOTH
        )
        self.notes_file = notes_file or Path("slideshow_notes.txt")
    
    def execute(self, slideshow_context: SlideshowContext, note_text: str = "", **kwargs) -> Dict[str, Any]:
        if not slideshow_context.image_paths:
            return {"error": "No images in slideshow"}
        
        try:
            self.notes_file.touch(exist_ok=True)
            
            with open(self.notes_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                image_path = slideshow_context.image_paths[slideshow_context.current_index]
                
                f.write(f"[{timestamp}] {image_path}\n")
                if note_text:
                    f.write(f"  Note: {note_text}\n")
                f.write("\n")
            
            return {
                "noted": str(image_path),
                "note": note_text,
                "file": str(self.notes_file)
            }
            
        except Exception as e:
            return {"error": f"Failed to save note: {e}"}


# Undoable Actions Base
class UndoableAction(Action):
    """Base class for actions that support undo."""
    
    @abstractmethod
    def get_undo_action(self) -> Optional['UndoableAction']:
        """Return the action that undoes this action."""
        pass


# Script Hook Runners
class ScriptRunner:
    """Base class for running external hook scripts with QSS_* environment variables."""

    def __init__(self, script_path: Path):
        self.script_path = Path(script_path)
        if not self.script_path.exists():
            print(f"Warning: script not found: {self.script_path}")

    def _run(self, env_vars: Dict[str, str]) -> subprocess.CompletedProcess:
        """Run the script with the given environment variables merged into os.environ."""
        env = os.environ.copy()
        env.update(env_vars)
        return subprocess.run(
            [str(self.script_path)],
            env=env,
            capture_output=True,
            text=True
        )


class FilterScriptRunner(ScriptRunner):
    """Pre-display filter: runs before each image, rc 0=show, non-zero=skip."""

    def should_display(self, slideshow_context: SlideshowContext) -> bool:
        """Return True if the current image should be displayed."""
        if not self.script_path.exists():
            return True
        try:
            result = self._run(slideshow_context.get_environment_variables())
            return result.returncode == 0
        except Exception as e:
            print(f"Filter script error: {e}")
            return True  # show on error


class PostScriptRunner(ScriptRunner):
    """Post-tool hook: runs after any external tool (0-9) completes."""

    def run_post_hook(self, slideshow_context: SlideshowContext,
                      tool_id: str, tool_rc: int,
                      tool_stdout: str, tool_stderr: str,
                      prev_full_path: str, prev_img_name: str,
                      img_removed: bool) -> None:
        """Run the post-tool hook script. Fire-and-forget (errors are logged, never raised)."""
        if not self.script_path.exists():
            return
        try:
            env_vars = slideshow_context.get_environment_variables()
            env_vars['QSS_TOOL_ID'] = str(tool_id)
            env_vars['QSS_TOOL_RC'] = str(tool_rc)
            env_vars['QSS_TOOL_STDOUT'] = tool_stdout or ''
            env_vars['QSS_TOOL_STDERR'] = tool_stderr or ''
            env_vars['QSS_PREV_FULL_PATH'] = prev_full_path
            env_vars['QSS_PREV_IMG_NAME'] = prev_img_name
            env_vars['QSS_IMG_REMOVED'] = '1' if img_removed else ''
            self._run(env_vars)
        except Exception as e:
            print(f"Post script error: {e}")


# External Tool Support
class ExternalToolAction(Action):
    """Execute an external tool/script with environment variables."""
    
    def __init__(self, tool_id: str, tool_path: Optional[Path] = None):
        """
        Initialize external tool action.
        
        Args:
            tool_id: Tool identifier (e.g., "0", "1", "10", "26", "a", "b")
            tool_path: Path to the tool script
        """
        super().__init__(
            f"external_tool_{tool_id}", 
            f"Execute external tool {tool_id}",
            ActionContext.BOTH
        )
        self.tool_id = tool_id
        self.tool_path = tool_path
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        if not self.tool_path or not self.tool_path.exists():
            return {"error": f"Tool {self.tool_id} not found"}

        if not slideshow_context.image_paths:
            return {"error": "No images in slideshow"}

        # Snapshot state before tool runs (for post script)
        prev_path = slideshow_context.current_path
        prev_full_path = str(prev_path.resolve()) if prev_path else ''
        prev_img_name = prev_path.name if prev_path else ''

        # Build environment variables dynamically from template variables
        env = os.environ.copy()

        # Get all template variables as environment variables with QSS_ prefix
        env.update(slideshow_context.get_environment_variables())

        # Add tool-specific variables that aren't in template variables
        env['QSS_TOOL_ID'] = str(self.tool_id)

        # Add alternative name for index for backward compatibility
        env['QSS_IMG_INDEX'] = env.get('QSS_IMG_IDX', '1')

        try:
            result = subprocess.run(
                [str(self.tool_path)],
                env=env,
                capture_output=True,
                text=True
            )

            # Handle return codes
            img_removed = False
            if result.returncode == 1:
                # Tool requests image removal
                img_removed = True
                if slideshow_context.image_paths:
                    removed_path = slideshow_context.image_paths[slideshow_context.current_index]
                    slideshow_context.image_paths.pop(slideshow_context.current_index)
                    # Adjust index if necessary
                    if slideshow_context.current_index >= len(slideshow_context.image_paths):
                        slideshow_context.current_index = max(0, len(slideshow_context.image_paths) - 1)
                    ret = {"action": "removed", "tool": self.tool_id, "removed_path": str(removed_path)}
                else:
                    ret = {"action": "removed", "tool": self.tool_id}
            elif result.returncode == 0:
                ret = {"success": True, "tool": self.tool_id, "output": result.stdout}
            else:
                ret = {"error": f"Tool {self.tool_id} returned code {result.returncode}", "stderr": result.stderr}

            # Run post script hook if configured
            post_runner = getattr(slideshow_context, 'post_runner', None)
            if post_runner:
                post_runner.run_post_hook(
                    slideshow_context,
                    tool_id=self.tool_id,
                    tool_rc=result.returncode,
                    tool_stdout=result.stdout,
                    tool_stderr=result.stderr,
                    prev_full_path=prev_full_path,
                    prev_img_name=prev_img_name,
                    img_removed=img_removed
                )

            return ret

        except Exception as e:
            return {"error": str(e)}


class ExternalToolManager:
    """Discovers and manages external tool scripts."""
    
    def __init__(self, base_name: str = "tool", search_dir: Path = None):
        """
        Initialize tool manager.
        
        Args:
            base_name: Base name for tool scripts (e.g., "tool", "rename_tool")
            search_dir: Directory to search for tools (default: current directory)
        """
        self.base_name = base_name
        self.search_dir = search_dir or Path.cwd()
        self.tools: Dict[str, Path] = {}
        self.discover_tools()
    
    def discover_tools(self) -> Dict[str, Path]:
        """
        Discover external tool scripts in the search directory.
        
        Looks for scripts matching patterns:
        - {base_name}0 through {base_name}99
        - {base_name}_0 through {base_name}_99
        - {base_name}a through {base_name}z
        - {base_name}_a through {base_name}_z
        
        With extensions: .sh, .py, .bat, .cmd, .exe, .ps1, or executable
        """
        import re
        
        if not self.search_dir.exists():
            return self.tools
        
        # Patterns to match
        patterns = [
            # Numeric tools (0-99)
            (re.compile(f'^{re.escape(self.base_name)}_?(\\d{{1,2}})(\\..*)?$'), 
             lambda m: m.group(1)),
            # Alphabetic tools (a-z, A-Z)
            (re.compile(f'^{re.escape(self.base_name)}_?([a-zA-Z])(\\..*)?$'), 
             lambda m: m.group(1).lower()),
        ]
        
        for file_path in self.search_dir.iterdir():
            if not file_path.is_file():
                continue
                
            for pattern, id_extractor in patterns:
                match = pattern.match(file_path.name)
                if match:
                    tool_id = id_extractor(match)
                    # Check if executable or has script extension
                    is_executable = os.access(file_path, os.X_OK)
                    has_script_ext = file_path.suffix.lower() in [
                        '.sh', '.py', '.bat', '.cmd', '.exe', '.ps1', '.rb', '.pl'
                    ]
                    
                    if is_executable or has_script_ext:
                        self.tools[tool_id] = file_path
                        break
        
        return self.tools
    
    def get_tool(self, tool_id: str) -> Optional[Path]:
        """Get tool path by ID."""
        return self.tools.get(tool_id)
    
    def list_tools(self) -> List[tuple[str, Path]]:
        """List all discovered tools sorted by ID."""
        # Sort with natural ordering (0-9, then 10-99, then a-z)
        def sort_key(item):
            tool_id = item[0]
            if tool_id.isdigit():
                return (0, int(tool_id))
            else:
                return (1, tool_id)
        
        return sorted(self.tools.items(), key=sort_key)
    
    def register_tool_actions(self, registry: 'ActionRegistry'):
        """Register all discovered tools as actions."""
        for tool_id, tool_path in self.tools.items():
            action = ExternalToolAction(tool_id, tool_path)
            registry.register(action)


# Quit Action
class QuitAction(Action):
    """Exit the application."""
    
    def __init__(self):
        super().__init__("quit", "Exit application", ActionContext.GUI)
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        return {"action": "quit"}


# Register default actions
def register_default_actions():
    """Register all default actions."""
    # Navigation
    action_registry.register(NavigateNextAction())
    action_registry.register(NavigatePreviousAction())
    
    # Controls
    action_registry.register(TogglePauseAction())
    action_registry.register(ToggleFullscreenAction())
    action_registry.register(ToggleRepeatAction())
    action_registry.register(ToggleShuffleAction())
    action_registry.register(ToggleAlwaysOnTopAction())
    action_registry.register(ToggleGalleryModeAction())

    # Speed
    action_registry.register(IncreaseSpeedAction())
    action_registry.register(DecreaseSpeedAction())
    
    # File Manager
    action_registry.register(OpenFolderAction())
    action_registry.register(RevealFileAction())
    
    # Memory
    action_registry.register(RememberAction())
    action_registry.register(NoteAction())
    
    # Quit
    action_registry.register(QuitAction())


# Initialize default actions on module load
register_default_actions()
