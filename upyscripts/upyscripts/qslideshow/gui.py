#!/usr/bin/env python3
"""
GUI implementation for qslideshow using tkinter.
"""

import sys
import os
import random
import subprocess
from pathlib import Path
from typing import List, Optional, Dict

from .core import SlideshowContext
from .config import ConfigManager
from .actions import action_registry, ExternalToolManager
from .hotkeys import HotkeyManager, TkinterHotkeyAdapter
from .gestures import GestureManager
from .history import ActionHistory, UndoAction, RedoAction
from .trash import TrashManager

# Conditional imports - only import heavy dependencies when needed
tk = None
ttk = None
Image = None
ImageTk = None


def import_dependencies():
    """Import tkinter and PIL when actually needed."""
    global tk, ttk, Image, ImageTk

    try:
        import tkinter as tk_module
        from tkinter import ttk as ttk_module
        tk = tk_module
        ttk = ttk_module
    except ImportError:
        print("Error: tkinter is not available. Please install it first")
        sys.exit(1)

    try:
        from PIL import Image as Image_module, ImageTk as ImageTk_module
        Image = Image_module
        ImageTk = ImageTk_module
    except ImportError:
        print("Error: Pillow is required. Install with: pip install Pillow")
        sys.exit(1)


class ImageSlideshow:
    """Main slideshow application class."""

    def __init__(self, image_paths: List[Path], config: ConfigManager = None,
                 speed: float = None, repeat: bool = None,
                 fit_mode: str = None, status_format: Optional[str] = None,
                 always_on_top: bool = None, shuffle: bool = None,
                 external_tools: Optional[str] = None, paused: bool = None):
        """
        Initialize the slideshow.

        Args:
            image_paths: List of image file paths to display
            config: Configuration manager instance
            speed: Time in seconds between slides (overrides config)
            repeat: Whether to loop back to beginning (overrides config)
            fit_mode: How images fit in window (overrides config)
            status_format: Status text format with variables (overrides config)
            always_on_top: Keep window above all others (overrides config)
            shuffle: Randomize image order (overrides config)
            external_tools: Base name for external tool scripts (overrides config)
            paused: Start slideshow in paused mode (overrides config)
        """
        # Store config
        self.config = config or ConfigManager()
        
        # Get values from config with CLI overrides
        speed = speed if speed is not None else self.config.get('slideshow.speed', 3.0)
        repeat = repeat if repeat is not None else self.config.get('slideshow.repeat', False)
        fit_mode = fit_mode if fit_mode is not None else self.config.get('slideshow.fit_mode', 'shrink')
        status_format = status_format or self.config.get('slideshow.status_format')
        always_on_top = always_on_top if always_on_top is not None else self.config.get('slideshow.always_on_top', False)
        shuffle = shuffle if shuffle is not None else self.config.get('slideshow.shuffle', False)
        paused = paused if paused is not None else self.config.get('slideshow.paused_on_start', False)
        external_tools = external_tools or self.config.get('external_tools.base_name', 'tool')
        
        # Create the slideshow context
        self.context = SlideshowContext(
            image_paths=image_paths,
            speed=speed,
            repeat=repeat,
            fit_mode=fit_mode,
            status_format=status_format,
            always_on_top=always_on_top,
            shuffle=shuffle,
            paused=paused
        )

        # UI state (not part of context as it's UI-specific)
        self.is_fullscreen = False
        self.timer_id = None

        # Initialize action system components
        self.hotkey_manager = HotkeyManager(self.config, 'gui')
        self.gesture_manager = GestureManager(self.config, 'gui')
        self.action_history = ActionHistory(self.config.get('file_operations.max_undo_history', 50))
        
        # Register undo/redo actions
        action_registry.register(UndoAction(self.action_history))
        action_registry.register(RedoAction(self.action_history))
        
        # Initialize trash manager if enabled
        if self.config.get('file_operations.enable_trash', True):
            trash_dir = self.config.get('file_operations.trash_dir', '.trash')
            if image_paths:
                base_path = image_paths[0].parent
                self.trash_manager = TrashManager(base_path, trash_dir)
            else:
                self.trash_manager = None
        else:
            self.trash_manager = None
        
        # External tools setup
        self.external_tools = {}
        if external_tools:
            tool_manager = ExternalToolManager(external_tools, Path.cwd())
            tool_manager.register_tool_actions(action_registry)
            self.external_tools = tool_manager.tools
            if self.external_tools:
                print(f"Found external tools for keys: {', '.join(sorted(self.external_tools.keys()))}")

        if not self.context.image_paths:
            print("No images found to display.")
            sys.exit(1)

        # Initialize tkinter
        self.root = tk.Tk()
        self.root.title("Image Slideshow")
        self.root.geometry("640x480")

        # Set focus to receive keyboard events
        self.root.focus_set()

        # Set always on top if requested
        if self.context.always_on_top:
            self.root.attributes('-topmost', True)

        # Create canvas for image display
        self.canvas = tk.Canvas(self.root, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Create status text if format provided
        self.status_text_id = None
        if self.context.status_format:
            self.status_text_id = self.canvas.create_text(
                10, 10,  # Position at top-left with padding
                text='',
                fill='white',
                font=('Arial', 10),
                anchor='nw'
            )

        # Bind keyboard events using hotkey manager
        self.root.bind('<KeyPress>', self.handle_key_event)

        # Bind window resize event
        self.root.bind('<Configure>', self.on_resize)

        # Track window state
        self.window_maximized = False
        self.root.bind('<Map>', self.check_window_state)

        # Load first image
        self.current_photo = None
        self.display_current_image()

        # Start auto-advance
        self.schedule_next()

    def check_window_state(self, event=None):
        """Check if window is maximized."""
        try:
            state = self.root.state()
            # Handle different platform state names
            self.window_maximized = (state in ['zoomed', 'maximized', 'iconic'])
        except tk.TclError:
            # Fallback if state() is not available
            self.window_maximized = False
    
    def handle_key_event(self, event):
        """Handle keyboard events using the hotkey manager."""
        # Check if widgets still exist before processing
        try:
            if not self.canvas.winfo_exists() or not self.root.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            # Widget has been destroyed
            return
            
        # Parse tkinter event
        key, modifiers = TkinterHotkeyAdapter.parse_tkinter_event(event)
        
        # Let hotkey manager handle it and execute action
        result = self.hotkey_manager.handle_key_event(
            key, modifiers, self.context
        )
        
        # Handle special UI-specific results
        if result:
            # Get the action that was executed
            action_name = self.hotkey_manager.get_action_for_key(key, modifiers)
            
            # Handle UI updates based on action
            if action_name == 'toggle_fullscreen':
                # Handle fullscreen toggle for GUI
                self.is_fullscreen = result.get('is_fullscreen', not self.is_fullscreen)
                self.root.attributes('-fullscreen', self.is_fullscreen)
                self.resize_and_display()
            
            elif action_name == 'toggle_always_on_top':
                # Update window attributes
                self.root.attributes('-topmost', self.context.always_on_top)
                print(f"Always on top: {'on' if self.context.always_on_top else 'off'}")
            
            elif action_name == 'toggle_pause':
                # Handle pause/resume timer
                if self.context.is_paused:
                    if self.timer_id:
                        self.root.after_cancel(self.timer_id)
                        self.timer_id = None
                    print("Slideshow paused")
                else:
                    self.schedule_next()
                    print("Slideshow resumed")
            
            elif action_name == 'toggle_repeat':
                print(f"Repeat mode: {'on' if self.context.repeat else 'off'}")
            
            elif action_name == 'toggle_shuffle':
                print(f"Shuffle mode: {'on' if self.context.shuffle else 'off'}")
                # Shuffle updates the image list, so redisplay
                self.display_current_image()
            
            elif action_name in ['increase_speed', 'decrease_speed']:
                print(f"Speed: {self.context.speed_seconds:.1f}s per slide")
                self.reset_timer()
            
            elif action_name == 'quit':
                self.quit()
            
            elif action_name and action_name.startswith('external_tool_'):
                # External tool was executed via action system
                if result.get('action') == 'removed':
                    print(f"Tool removed image from list")
                    self.display_current_image()
            
            # Update display for navigation actions
            if action_name in ['navigate_next', 'navigate_previous']:
                self.reset_timer()
                self.display_current_image()
                if not self.context.is_paused:
                    self.schedule_next()
            
            # Always update status after any action
            self.update_status()

    def load_image(self, path: Path) -> Optional[object]:
        """Load an image from file with better error handling."""
        try:
            # Verify file exists and is readable
            if not path.exists():
                print(f"File not found: {path}")
                return None

            if not path.is_file():
                print(f"Not a file: {path}")
                return None

            # Try to open the image
            image = Image.open(path)
            # Verify it's a valid image by trying to get its size
            _ = image.size
            return image

        except (IOError, OSError) as e:
            print(f"I/O error loading {path}: {e}")
            return None
        except Image.UnidentifiedImageError:
            print(f"Not a valid image file: {path}")
            return None
        except Exception as e:
            print(f"Unexpected error loading {path}: {e}")
            return None

    def update_status(self):
        """Update the status text display."""
        if self.status_text_id:
            try:
                # Check if canvas still exists by trying to access its winfo
                if not self.canvas.winfo_exists():
                    return
                status_text = self.context.format_status()
                self.canvas.itemconfig(self.status_text_id, text=status_text)
                # Ensure status stays on top
                self.canvas.tag_raise(self.status_text_id)
            except (tk.TclError, AttributeError):
                # Widget has been destroyed or doesn't exist
                pass

    def display_current_image(self):
        """Display the current image."""
        if not self.context.image_paths:
            return

        # Clean up previous image resources
        if self.current_photo:
            del self.current_photo
            self.current_photo = None
        if self.context.current_image:
            self.context.current_image.close()
            self.context.current_image = None

        path = self.context.current_path
        if path is None:
            return

        image = self.load_image(path)

        if image is None:
            # Remove failed image from list to avoid retrying
            print(f"Removing failed image from list: {path}")
            self.context.image_paths.pop(self.context.current_index)

            # Check if we have any images left
            if len(self.context.image_paths) == 0:
                print("No more valid images to display.")
                self.quit()
                return

            # Adjust current index if we removed the last image
            if self.context.current_index >= len(self.context.image_paths):
                if self.context.repeat and len(self.context.image_paths) > 0:
                    self.context.current_index = 0
                else:
                    print("Reached end of image list.")
                    self.quit()
                    return

            # Try next image
            self.display_current_image()
            return

        self.context.current_image = image

        # Update window title
        self.root.title(f"Image Slideshow - {path.name} ({self.context.current_index + 1}/{len(self.context.image_paths)})")

        # Resize and display
        self.resize_and_display()

        # Update status display
        self.update_status()

    def resize_and_display(self):
        """Resize image to fit window and display."""
        if self.context.current_image is None:
            return

        # Get canvas dimensions
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # If canvas not yet rendered, use reasonable defaults or screen size
        if canvas_width <= 1:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            canvas_width = min(self.context.current_image.width, int(screen_width * 0.8))
            canvas_height = min(self.context.current_image.height, int(screen_height * 0.8))

        img_width, img_height = self.context.current_image.size
        display_image = None

        try:
            # Special case: always shrink-to-fit when maximized or fullscreen
            if self.window_maximized or self.is_fullscreen:
                scale = min(1.0, min(canvas_width / img_width, canvas_height / img_height))

                if scale < 1.0:
                    new_width = int(img_width * scale)
                    new_height = int(img_height * scale)
                    display_image = self.context.current_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    display_image = self.context.current_image

            # Normal window state - handle based on fit mode
            elif self.context.fit_mode == 'original':
                # Original mode: resize window to image
                display_image = self.context.current_image
                self.root.geometry(f"{img_width}x{img_height}")

            else:  # shrink mode (default)
                # Shrink to fit if needed, never expand
                scale = min(1.0, min(canvas_width / img_width, canvas_height / img_height))

                if scale < 1.0:
                    new_width = int(img_width * scale)
                    new_height = int(img_height * scale)
                    display_image = self.context.current_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    display_image = self.context.current_image

            # Convert to PhotoImage and display
            self.current_photo = ImageTk.PhotoImage(display_image)

            # Clear canvas and display image (preserve status text)
            # Delete all except status text
            for item in self.canvas.find_all():
                if item != self.status_text_id:
                    self.canvas.delete(item)

            # Create image
            self.canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                image=self.current_photo,
                anchor='center'
            )

            # Clean up temporary resized image if it was created
            if display_image is not self.context.current_image:
                display_image.close()

        except Exception as e:
            print(f"Error displaying image: {e}")
            # Try to continue with next image
            self.next_image(auto_advance=True)
            return

        # Ensure status stays on top
        if self.status_text_id:
            self.canvas.tag_raise(self.status_text_id)

    def on_resize(self, event=None):
        """Handle window resize event."""
        if event and event.widget == self.root:
            self.check_window_state()
            self.resize_and_display()

    def next_image(self, event=None, auto_advance=False):
        """Display next image - wrapper for auto-advance."""
        if not self.context.image_paths:
            return

        # Execute the navigate_next action
        action = action_registry.get('navigate_next')
        if action:
            old_index = self.context.current_index
            result = action.execute(self.context)
            
            # Check if we've reached the end
            if old_index == result['current_index'] and not self.context.repeat:
                # No change in index and not repeating - we're at the end
                if auto_advance:
                    self.quit()
                return
            
            # Only reset timer if this is a manual navigation
            if not auto_advance:
                self.reset_timer()
            
            self.display_current_image()
            if not self.context.is_paused:
                self.schedule_next()

    def reset_timer(self):
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    def previous_image(self, event=None):
        """Display previous image - kept for compatibility."""
        if not self.context.image_paths:
            return

        # Execute the navigate_previous action
        action = action_registry.get('navigate_previous')
        if action:
            action.execute(self.context)
            self.reset_timer()
            self.display_current_image()
            if not self.context.is_paused:
                self.schedule_next()

    def toggle_pause(self, event=None):
        """Toggle pause/play - kept for auto-advance handling."""
        action = action_registry.get('toggle_pause')
        if action:
            action.execute(self.context)
            
            if self.context.is_paused:
                # Cancel scheduled advance
                if self.timer_id:
                    self.root.after_cancel(self.timer_id)
                    self.timer_id = None
            else:
                # Resume auto-advance
                self.schedule_next()
            
            # Update status to show paused state
            self.update_status()

    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen mode."""
        # This is now handled in handle_key_event for proper action integration
        pass

    def toggle_repeat(self, event=None):
        """Toggle repeat mode."""
        # Now handled by action system through handle_key_event
        pass

    def toggle_always_on_top(self, event=None):
        """Toggle always on top mode."""
        action = action_registry.get('toggle_always_on_top')
        if action:
            action.execute(self.context)
            self.root.attributes('-topmost', self.context.always_on_top)
            print(f"Always on top: {'on' if self.context.always_on_top else 'off'}")
            self.update_status()

    def toggle_shuffle(self, event=None):
        """Toggle shuffle mode."""
        # Now handled by action system through handle_key_event
        pass

    def increase_speed(self, event=None):
        """Increase slide speed."""
        # Now handled by action system through handle_key_event
        pass

    def decrease_speed(self, event=None):
        """Decrease slide speed."""
        # Now handled by action system through handle_key_event
        pass

    def schedule_next(self):
        """Schedule next image advance."""
        if not self.context.is_paused and self.timer_id is None:
            self.timer_id = self.root.after(self.context.speed_ms, self.auto_advance)

    def auto_advance(self):
        """Automatically advance to next image."""
        self.timer_id = None

        # Check if we should continue before advancing
        if self.context.current_index >= len(self.context.image_paths) - 1 and not self.context.repeat:
            # At the end and not repeating, stop auto-advance
            return

        self.next_image(auto_advance=True)

    def quit(self, event=None):
        """Quit the application."""
        if self.timer_id:
            self.root.after_cancel(self.timer_id)

        # Clean up image resources
        if self.current_photo:
            del self.current_photo
            self.current_photo = None
        if self.context.current_image:
            self.context.current_image.close()
            self.context.current_image = None

        self.root.quit()
        self.root.destroy()

    def run(self):
        """Start the slideshow."""
        self.root.mainloop()

    # External tool discovery is now handled by ExternalToolManager in __init__
    # Tools are registered as actions and executed through the action system

    def execute_external_tool(self, key: str):
        """
        Execute an external tool script.

        Args:
            key: The key pressed ('0'-'9')
        """
        if key not in self.external_tools:
            return

        script_path = self.external_tools[key]

        # Build environment variables with QSS_ prefix
        env = os.environ.copy()
        for var_name, var_value in self.context.get_template_variables().items():
            env[f'QSS_{var_name.upper()}'] = str(var_value)

        print(f"Executing external tool: {script_path}")

        try:
            # Execute the script
            result = subprocess.run(
                [str(script_path)],
                env=env,
                capture_output=True,
                text=True
            )

            # Handle return code
            if result.returncode == 1:
                # Remove current image from list
                print("Tool returned 1, removing image from list")
                self.remove_current_image()
            elif result.returncode == 0:
                # No action needed
                print("Tool completed successfully")
            else:
                print(f"Tool returned unexpected code: {result.returncode}")

            # Print any output from the script
            if result.stdout:
                print(f"Tool output: {result.stdout}")
            if result.stderr:
                print(f"Tool error: {result.stderr}")

        except Exception as e:
            print(f"Error executing external tool: {e}")

    def remove_current_image(self):
        """Remove the current image from the slideshow list."""
        if not self.context.image_paths or self.context.current_index >= len(self.context.image_paths):
            return

        removed_path = self.context.image_paths.pop(self.context.current_index)
        print(f"Removed from slideshow: {removed_path}")

        # Also remove from original list if it exists there
        if removed_path in self.context.original_image_paths:
            self.context.original_image_paths.remove(removed_path)

        # Check if we have any images left
        if len(self.context.image_paths) == 0:
            print("No more images to display.")
            self.quit()
            return

        # Adjust current index if needed
        if self.context.current_index >= len(self.context.image_paths):
            if self.context.repeat and len(self.context.image_paths) > 0:
                self.context.current_index = 0
            else:
                self.context.current_index = len(self.context.image_paths) - 1

        # Display the current (or next) image
        self.display_current_image()