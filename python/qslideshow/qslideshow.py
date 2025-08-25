#!/usr/bin/env python3
"""
Cross-platform image slideshow viewer.
"""

import argparse
import sys
import random
from pathlib import Path
from typing import List, Optional, Dict, Any
import fnmatch
import http.server
import json
import mimetypes
import uuid
from urllib.parse import urlparse

# Available template variables for status display and script execution
TEMPLATE_VARIABLES = {
    # Image identification
    'img_idx': 'Current image index (1-based)',
    'img_total': 'Total number of images',
    'img_name': 'Image filename with extension',
    'base_name': 'Image filename without extension', 
    'extension': 'Image file extension (with dot)',
    
    # File and path information
    'img_path': 'Full image file path',
    'full_path': 'Full absolute image file path',
    'img_size': 'Image dimensions (WxH)',
    'file_size': 'File size in bytes',
    'img_size_mb': 'File size in MB',
    
    # Slideshow state
    'speed': 'Current slide speed',
    'paused': 'Pause state (True/False)',
    'repeat': 'Repeat mode (True/False)',
    'repeat_count': 'Number of times repeated',
    'always_on_top': 'Always on top setting (True/False)',
    'shuffle': 'Shuffle mode (True/False)',
    'progress_percent': 'Progress through slideshow as percentage',
}

def get_variable_list() -> str:
    """Get formatted list of available template variables for help text."""
    return ', '.join(f'{{{var}}}' for var in TEMPLATE_VARIABLES.keys())

def get_variable_descriptions() -> str:
    """Get formatted descriptions of template variables."""
    lines = []
    for var, desc in TEMPLATE_VARIABLES.items():
        lines.append(f"  {{{var}}}: {desc}")
    return '\n'.join(lines)

# Preset status line templates for --status $1-$9
STATUS_PRESETS = {
    "$1": "Media {img_idx}/{img_total} {progress_percent}%",
    "$2": "Media {img_idx}/{img_total} (r:{repeat_count})",
    "$3": "{img_idx}/{img_total}: {progress_percent}% {full_path}",
    "$4": "Media {img_path} ({img_size_mb}mb): {img_idx}/{img_total}",
    "$5": "{base_name}{extension} - {img_size} ({file_size}) - {speed}",
    "$6": "{full_path} | {progress_percent}% complete",
    # Add more presets ($7-$9) here as needed
}

def get_status_template(arg: str) -> str:
    """Return a pre-filled status template for $1-$9, or the arg itself if not a preset."""
    return STATUS_PRESETS.get(arg, arg)


def parse_arguments():
    """Parse command line arguments."""
    # Build status line presets for epilog dynamically from STATUS_PRESETS
    status_presets_lines = []
    for key, val in STATUS_PRESETS.items():
        # Show user-friendly format (single braces) but escape percent signs for epilog
        user_friendly_val = val.replace('%', '%%')  # Only escape % for argparse
        status_presets_lines.append(f"  --status {key}   {user_friendly_val}")

    parser = argparse.ArgumentParser(
        description='Cross-platform image slideshow viewer with web server mode',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'''
Examples:
  %(prog)s /path/to/images                    # GUI mode
  %(prog)s /path/to/images --web              # Web server mode
  %(prog)s /path/to/images --web --port 8080  # Web server on custom port
  %(prog)s /path/to/images --recursive --speed 5
  %(prog)s @image_list.txt --repeat
  %(prog)s . -r -x "*.gif" -x "*.ico"

Status line presets:
{chr(10).join(status_presets_lines)}

Keyboard shortcuts:
  Left/Right arrows: Navigate images
  Space/Enter: Toggle pause
  F: Toggle fullscreen
  R: Toggle repeat mode  
  T: Toggle always on top
  S: Toggle shuffle mode
  +/=: Increase speed by 1 second (slower)
  -: Decrease speed by 1 second (faster)
  Q/Escape: Quit

Template variables:
{get_variable_descriptions()}
        '''
    )
    
    parser.add_argument(
        'path',
        help='Image folder path or @response_file'
    )
    
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Search subdirectories for images'
    )
    
    parser.add_argument(
        '-x', '--exclude',
        action='append',
        metavar='PATTERN',
        help='Exclude files matching pattern (can be used multiple times)'
    )
    
    parser.add_argument(
        '-s', '--speed',
        type=float,
        default=3.0,
        metavar='SECONDS',
        help='Seconds between slides (default: 3.0)'
    )
    
    parser.add_argument(
        '--repeat',
        action='store_true',
        help='Loop back to first image after last'
    )
    
    parser.add_argument(
        '-f', '--fit-mode',
        choices=['shrink', 'original'],
        default='shrink',
        help='Image display mode: shrink (default) or original'
    )
    
    parser.add_argument(
        '--status',
        type=str,
        help=f'Status text with variables: {get_variable_list()}'
    )
    
    parser.add_argument(
        '--always-on-top',
        action='store_true',
        help='Keep window above all other windows'
    )
    
    parser.add_argument(
        '--shuffle',
        action='store_true',
        help='Randomize image order'
    )
    
    parser.add_argument(
        '--web', '--server',
        action='store_true',
        dest='web',
        help='Run as web server instead of GUI'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port for web server mode (default: 8000)'
    )
    
    return parser.parse_args()

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


class SlideshowContext:
    """Holds the complete state and context of the slideshow."""
    
    def __init__(self, image_paths: List[Path], speed: float = 3.0, repeat: bool = False,
                 fit_mode: str = 'shrink', status_format: Optional[str] = None,
                 always_on_top: bool = False, shuffle: bool = False):
        # Core image data
        self.image_paths = image_paths
        self.original_image_paths = image_paths.copy()
        self.current_index = 0
        self.current_image: Optional[object] = None  # Current PIL Image object
        
        # Slideshow settings
        self.speed_seconds = speed
        self.repeat = repeat
        self.fit_mode = fit_mode
        self.status_format = status_format
        self.always_on_top = always_on_top
        self.shuffle = shuffle
        
        # Runtime state
        self.is_paused = False
        self.repeat_count = 0
        
        # Apply shuffle if requested
        if self.shuffle:
            import random
            random.shuffle(self.image_paths)
    
    @property
    def speed_ms(self) -> int:
        """Get speed in milliseconds for tkinter."""
        return int(self.speed_seconds * 1000)
    
    @property
    def current_path(self) -> Optional[Path]:
        """Get the current image path."""
        if not self.image_paths or self.current_index >= len(self.image_paths):
            return None
        return self.image_paths[self.current_index]
    
    def get_template_variables(self) -> Dict[str, str]:
        """Get current values for all template variables."""
        if not self.image_paths or self.current_path is None:
            return {}
            
        path = self.current_path
        variables = {}
        
        # Image identification
        variables['img_idx'] = str(self.current_index + 1)
        variables['img_total'] = str(len(self.image_paths))
        variables['img_name'] = path.name
        variables['base_name'] = path.stem
        variables['extension'] = path.suffix
        
        # File and path information
        variables['img_path'] = str(path)
        variables['full_path'] = str(path.absolute())
        
        # Image size if available
        if self.current_image:
            img_width, img_height = self.current_image.size
            variables['img_size'] = f"{img_width}x{img_height}"
        else:
            variables['img_size'] = 'N/A'
            
        # File size information
        try:
            file_size = path.stat().st_size
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            variables['file_size'] = size_str
            variables['img_size_mb'] = f"{file_size / (1024 * 1024):.2f}"
        except (OSError, FileNotFoundError, AttributeError):
            variables['file_size'] = 'N/A'
            variables['img_size_mb'] = 'N/A'
        
        # Slideshow state
        variables['speed'] = f"{self.speed_seconds:.1f}s"
        variables['paused'] = "PAUSED" if self.is_paused else ""
        variables['repeat'] = "REPEAT" if self.repeat else ""
        variables['repeat_count'] = str(self.repeat_count)
        variables['always_on_top'] = "TOP" if self.always_on_top else ""
        variables['shuffle'] = "SHUFFLE" if self.shuffle else ""
        
        # Progress percentage
        if len(self.image_paths) > 0:
            progress = int(((self.current_index + 1) / len(self.image_paths)) * 100)
            variables['progress_percent'] = f"{progress}"
        else:
            variables['progress_percent'] = "0"
            
        return variables
    
    def format_template(self, template: str) -> str:
        """Format a template string with current variable values."""
        if not template or not self.image_paths:
            return ""
            
        variables = self.get_template_variables()
        result = template
        
        for var_name, var_value in variables.items():
            result = result.replace(f'{{{var_name}}}', str(var_value))
            
        return result
    
    def format_status(self) -> str:
        """Format the status string with variable substitution."""
        if not self.status_format:
            return ""
        return self.format_template(self.status_format)


class ImageSlideshow:
    """Main slideshow application class."""
    
    DEFAULT_IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', 
        '.tiff', '.tif', '.webp', '.ico', '.svg'
    }
    
    def __init__(self, image_paths: List[Path], speed: float = 3.0, repeat: bool = False, 
                 fit_mode: str = 'shrink', status_format: Optional[str] = None,
                 always_on_top: bool = False, shuffle: bool = False):
        """
        Initialize the slideshow.
        
        Args:
            image_paths: List of image file paths to display
            speed: Time in seconds between slides
            repeat: Whether to loop back to beginning
            fit_mode: How images fit in window ('shrink' or 'original')
            status_format: Status text format with variables
            always_on_top: Keep window above all others
            shuffle: Randomize image order
        """
        # Create the slideshow context
        self.context = SlideshowContext(
            image_paths=image_paths,
            speed=speed,
            repeat=repeat,
            fit_mode=fit_mode,
            status_format=status_format,
            always_on_top=always_on_top,
            shuffle=shuffle
        )
        
        # UI state (not part of context as it's UI-specific)
        self.is_fullscreen = False
        self.timer_id = None
        
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
        
        # Bind keyboard events
        self.root.bind('<Left>', self.previous_image)
        self.root.bind('<Right>', self.next_image)
        self.root.bind('<space>', self.toggle_pause)
        self.root.bind('<Return>', self.toggle_pause)
        self.root.bind('<Escape>', self.quit)
        self.root.bind('q', self.quit)
        self.root.bind('Q', self.quit)
        self.root.bind('f', self.toggle_fullscreen)
        self.root.bind('F', self.toggle_fullscreen)
        self.root.bind('r', self.toggle_repeat)
        self.root.bind('R', self.toggle_repeat)
        self.root.bind('t', self.toggle_always_on_top)
        self.root.bind('T', self.toggle_always_on_top)
        self.root.bind('s', self.toggle_shuffle)
        self.root.bind('S', self.toggle_shuffle)
        self.root.bind('+', self.increase_speed)
        self.root.bind('=', self.increase_speed)  # Also bind '=' for easier access (no shift needed)
        self.root.bind('-', self.decrease_speed)
        
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
            status_text = self.context.format_status()
            self.canvas.itemconfig(self.status_text_id, text=status_text)
            # Ensure status stays on top
            self.canvas.tag_raise(self.status_text_id)
    
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
            print(f"Removing failed image: {path}")
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
        """Display next image."""
        if not self.context.image_paths:
            return

        # Only reset timer if this is a manual navigation
        if not auto_advance:
            self.reset_timer()

        self.context.current_index += 1

        if self.context.current_index >= len(self.context.image_paths):
            if self.context.repeat:
                self.context.current_index = 0
                self.context.repeat_count += 1
            else:
                self.quit()
                return

        self.display_current_image()
        if not self.context.is_paused:
            self.schedule_next()
    
    def reset_timer(self):
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    def previous_image(self, event=None):
        """Display previous image."""
        if not self.context.image_paths:
            return

        self.reset_timer()
        
        self.context.current_index -= 1
        
        if self.context.current_index < 0:
            if self.context.repeat:
                self.context.current_index = len(self.context.image_paths) - 1
            else:
                self.context.current_index = 0
        
        self.display_current_image()
        if not self.context.is_paused:
            self.schedule_next()
            
    def toggle_pause(self, event=None):
        """Toggle pause/play."""
        self.context.is_paused = not self.context.is_paused
        
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
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes('-fullscreen', self.is_fullscreen)
        self.resize_and_display()
    
    def toggle_repeat(self, event=None):
        """Toggle repeat mode."""
        self.context.repeat = not self.context.repeat
        status = "on" if self.context.repeat else "off"
        print(f"Repeat mode: {status}")
        
        # Update status to show repeat state
        self.update_status()
    
    def toggle_always_on_top(self, event=None):
        """Toggle always on top mode."""
        self.context.always_on_top = not self.context.always_on_top
        self.root.attributes('-topmost', self.context.always_on_top)
        status = "on" if self.context.always_on_top else "off"
        print(f"Always on top: {status}")
        
        # Update status if needed
        self.update_status()
    
    def toggle_shuffle(self, event=None):
        """Toggle shuffle mode."""
        self.context.shuffle = not self.context.shuffle
        
        if self.context.shuffle:
            # Shuffle the list
            random.shuffle(self.context.image_paths)
        else:
            # Restore original order
            self.context.image_paths = self.context.original_image_paths.copy()
        
        # Reset to first image
        self.context.current_index = 0
        self.display_current_image()
        
        status = "on" if self.context.shuffle else "off"
        print(f"Shuffle mode: {status}")
        
        # Update status if needed
        self.update_status()
    
    def increase_speed(self, event=None):
        """Increase slide speed by 1 second (slower)."""
        self.context.speed_seconds += 1.0
        print(f"Speed: {self.context.speed_seconds:.1f}s per slide")
        self.update_status()
    
    def decrease_speed(self, event=None):
        """Decrease slide speed by 1 second (faster), minimum 0.1s."""
        if self.context.speed_seconds > 0.1:
            self.context.speed_seconds = max(0.1, self.context.speed_seconds - 1.0)
            print(f"Speed: {self.context.speed_seconds:.1f}s per slide")
            self.update_status()
    
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


class WebSlideshowHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for web slideshow."""
    
    def __init__(self, *args, web_slideshow=None, **kwargs):
        self.web_slideshow = web_slideshow
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Override to reduce verbosity."""
        pass  # Suppress default logging
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Serve main HTML file
        if path == '/' or path == '/index.html':
            self.serve_html()
        # Serve JavaScript file
        elif path == '/slideshow.js':
            self.serve_javascript()
        # Serve manifest file for PWA
        elif path == '/app.manifest':
            self.serve_manifest()
        # API endpoints
        elif path == '/api/images':
            self.serve_image_list()
        elif path.startswith('/api/image/'):
            self.serve_image(path)
        elif path == '/api/status':
            self.serve_status()
        elif path == '/api/config':
            self.serve_config()
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/control':
            self.handle_control()
        else:
            self.send_error(404, "Not Found")
    
    def get_session_id(self):
        """Get or create session ID from cookies."""
        cookie_header = self.headers.get('Cookie', '')
        session_id = None
        
        if cookie_header:
            for cookie in cookie_header.split(';'):
                if '=' in cookie:
                    name, value = cookie.strip().split('=', 1)
                    if name == 'slideshow_session':
                        session_id = value
                        break
        
        return session_id
    
    def serve_html(self):
        """Serve the main HTML page."""
        # Try to load external HTML file first
        html_file = Path(__file__).parent / 'web' / 'index.html'
        
        if not html_file.exists():
            self.send_error(500, "Server misconfiguration: index.html not found")
            return
        
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Create or get session
        session_id = self.get_session_id()
        if not session_id or session_id not in self.web_slideshow.sessions:
            session_id = str(uuid.uuid4())
            self.web_slideshow.create_session(session_id)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Set-Cookie', f'slideshow_session={session_id}; Path=/; HttpOnly')
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_javascript(self):
        """Serve the JavaScript file."""
        # Try to load external JS file first
        js_file = Path(__file__).parent / 'web' / 'slideshow.js'
        
        if not js_file.exists():
            self.send_error(500, "Server misconfiguration: slideshow.js not found")
            return

        with open(js_file, 'r', encoding='utf-8') as f:
            js_content = f.read()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/javascript')
        self.end_headers()
        self.wfile.write(js_content.encode())
    
    def serve_manifest(self):
        """Serve the PWA manifest file."""
        manifest_file = Path(__file__).parent / 'web' / 'app.manifest'
        
        if not manifest_file.exists():
            # Serve a default manifest if file doesn't exist
            manifest = {
                "name": "Web Slideshow",
                "short_name": "Slideshow",
                "display": "fullscreen",
                "orientation": "any",
                "start_url": "/",
                "background_color": "#000000",
                "theme_color": "#000000"
            }
            manifest_content = json.dumps(manifest)
        else:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest_content = f.read()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/manifest+json')
        self.end_headers()
        self.wfile.write(manifest_content.encode())
    
    def serve_image_list(self):
        """Serve the list of images."""
        session_id = self.get_session_id()
        if not session_id or session_id not in self.web_slideshow.sessions:
            self.send_error(401, "No session")
            return
        
        image_list = []
        for i, path in enumerate(self.web_slideshow.image_paths):
            image_list.append({
                'index': i,
                'name': path.name,
                'path': str(path)
            })
        
        response = {'images': image_list}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
    
    def serve_image(self, path):
        """Serve an image file."""
        try:
            index = int(path.split('/')[-1])
            if 0 <= index < len(self.web_slideshow.image_paths):
                image_path = self.web_slideshow.image_paths[index]
                
                if image_path.exists():
                    mime_type, _ = mimetypes.guess_type(str(image_path))
                    if not mime_type:
                        mime_type = 'application/octet-stream'
                    
                    self.send_response(200)
                    self.send_header('Content-Type', mime_type)
                    self.send_header('Cache-Control', 'max-age=3600')
                    self.end_headers()
                    
                    with open(image_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error(404, "Image not found")
            else:
                self.send_error(404, "Invalid image index")
        except (ValueError, IndexError):
            self.send_error(400, "Invalid request")
    
    def serve_status(self):
        """Serve current status for this session."""
        session_id = self.get_session_id()
        if not session_id or session_id not in self.web_slideshow.sessions:
            self.send_error(401, "No session")
            return
        
        session = self.web_slideshow.sessions[session_id]
        status_text = session.format_status() if session.status_format else ""
        
        response = {
            'current_index': session.current_index,
            'total_images': len(self.web_slideshow.image_paths),
            'is_paused': session.is_paused,
            'speed': session.speed_seconds,
            'repeat': session.repeat,
            'shuffle': session.shuffle,
            'status_text': status_text
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
    
    def serve_config(self):
        """Serve configuration."""
        session_id = self.get_session_id()
        if not session_id or session_id not in self.web_slideshow.sessions:
            self.send_error(401, "No session")
            return
        
        session = self.web_slideshow.sessions[session_id]
        
        config = {
            'speed': session.speed_seconds,
            'repeat': session.repeat,
            'shuffle': session.shuffle,
            'fit_mode': session.fit_mode,
            'always_on_top': session.always_on_top
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(config).encode())
    
    def handle_control(self):
        """Handle control commands."""
        session_id = self.get_session_id()
        if not session_id or session_id not in self.web_slideshow.sessions:
            self.send_error(401, "No session")
            return
        
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode())
                action = data.get('action')
                session = self.web_slideshow.sessions[session_id]
                
                result = {'success': False}
                
                if action == 'next':
                    session.current_index += 1
                    if session.current_index >= len(self.web_slideshow.image_paths):
                        if session.repeat:
                            session.current_index = 0
                            session.repeat_count += 1
                        else:
                            session.current_index = len(self.web_slideshow.image_paths) - 1
                    result = {'success': True, 'current_index': session.current_index}
                
                elif action == 'previous':
                    session.current_index -= 1
                    if session.current_index < 0:
                        if session.repeat:
                            session.current_index = len(self.web_slideshow.image_paths) - 1
                        else:
                            session.current_index = 0
                    result = {'success': True, 'current_index': session.current_index}
                
                elif action == 'toggle_pause':
                    session.is_paused = not session.is_paused
                    result = {'success': True, 'is_paused': session.is_paused}
                
                elif action == 'toggle_repeat':
                    session.repeat = not session.repeat
                    result = {'success': True, 'repeat': session.repeat}
                
                elif action == 'toggle_shuffle':
                    session.shuffle = not session.shuffle
                    if session.shuffle:
                        # Note: In web mode, shuffle affects display order but not the actual list
                        pass
                    result = {'success': True, 'shuffle': session.shuffle}
                
                elif action == 'increase_speed':
                    session.speed_seconds += 1.0
                    result = {'success': True, 'speed': session.speed_seconds}
                
                elif action == 'decrease_speed':
                    if session.speed_seconds > 0.1:
                        session.speed_seconds = max(0.1, session.speed_seconds - 1.0)
                    result = {'success': True, 'speed': session.speed_seconds}
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
        else:
            self.send_error(400, "No data")


class WebSlideshow:
    """Web-based slideshow server."""
    
    def __init__(self, image_paths: List[Path], config: Dict[str, Any], port: int = 8000):
        """
        Initialize web slideshow server.
        
        Args:
            image_paths: List of image paths to serve
            config: Configuration dictionary
            port: Port to run server on
        """
        self.image_paths = image_paths
        self.original_image_paths = image_paths.copy()
        self.config = config
        self.port = port
        self.sessions = {}  # session_id -> SlideshowContext
        
        # Apply shuffle to the main list if requested
        if config.get('shuffle', False):
            random.shuffle(self.image_paths)
        
        # Create handler with reference to this slideshow
        self.handler = lambda *args, **kwargs: WebSlideshowHandler(
            *args, web_slideshow=self, **kwargs
        )
    
    def create_session(self, session_id: str):
        """Create a new session for a client."""
        # Each session gets its own context
        session = SlideshowContext(
            image_paths=self.image_paths,  # Share the same image list
            speed=self.config.get('speed', 3.0),
            repeat=self.config.get('repeat', False),
            fit_mode=self.config.get('fit_mode', 'shrink'),
            status_format=self.config.get('status_format'),
            always_on_top=self.config.get('always_on_top', False),
            shuffle=self.config.get('shuffle', False)
        )
        session.current_index = 0  # Each client starts at image 0
        # Set current_image to None as we don't load images in web mode
        session.current_image = None
        self.sessions[session_id] = session
        return session
    
    def run(self):
        """Start the web server."""
        server_address = ('', self.port)
        httpd = http.server.HTTPServer(server_address, self.handler)
        
        print(f"Web slideshow server running on:")
        print(f"  http://localhost:{self.port}")
        print(f"  http://0.0.0.0:{self.port}")
        print(f"\nServing {len(self.image_paths)} images")
        print("Press Ctrl+C to stop the server")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


def find_images(directory: Path, recursive: bool, exclude_patterns: List[str]) -> List[Path]:
    """Find all image files in a directory, case-insensitively."""
    if not directory.is_dir():
        print(f"Error: Path is not a directory: {directory}")
        return []
        
    image_files = []
    
    # Create a case-insensitive set of extensions
    extensions = {ext.lower() for ext in ImageSlideshow.DEFAULT_IMAGE_EXTENSIONS}
    
    glob_pattern = '**/*' if recursive else '*'
    
    for path in directory.glob(glob_pattern):
        if path.is_file() and path.suffix.lower() in extensions:
            # Check against exclude patterns
            if not any(fnmatch.fnmatch(path.name, p) for p in exclude_patterns):
                image_files.append(path)
                
    return sorted(image_files)


def parse_response_file(filepath: Path) -> List[Path]:
    """
    Parse a response file containing image paths.
    
    Args:
        filepath: Path to response file
        
    Returns:
        List of image file paths
    """
    if not filepath.exists():
        print(f"Error: Response file does not exist: {filepath}")
        return []
    
    image_files = []
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    path = Path(line)
                    if path.exists() and path.is_file():
                        if path.suffix.lower() in ImageSlideshow.DEFAULT_IMAGE_EXTENSIONS:
                            image_files.append(path)
    except Exception as e:
        print(f"Error reading response file: {e}")
    
    return image_files


def main():
    """Main entry point."""
    # Parse arguments first
    args = parse_arguments()
    
    # Parse exclude patterns
    exclude_patterns = []
    if args.exclude:
        for pattern_arg in args.exclude:
            # Split by semicolon if multiple patterns in one argument
            patterns = pattern_arg.split(';')
            exclude_patterns.extend(p.strip() for p in patterns if p.strip())
    
    # Get image files
    if args.path.startswith('@'):
        # Response file
        response_file = Path(args.path[1:])
        image_files = parse_response_file(response_file)
    else:
        # Directory
        dir_path = Path(args.path)
        image_files = find_images(dir_path, args.recursive, exclude_patterns)
    
    if not image_files:
        print("No images found.")
        sys.exit(1)
    
    print(f"Found {len(image_files)} images")
    
    # Expand status preset if needed
    status_format = None
    if args.status:
        status_format = get_status_template(args.status)
    
    # Check if web mode is requested
    if args.web:
        # Run as web server
        config = {
            'speed': args.speed,
            'repeat': args.repeat,
            'fit_mode': args.fit_mode,
            'status_format': status_format,
            'always_on_top': args.always_on_top,
            'shuffle': args.shuffle
        }
        
        web_slideshow = WebSlideshow(
            image_files,
            config=config,
            port=args.port
        )
        
        try:
            web_slideshow.run()
        except KeyboardInterrupt:
            print("\nWeb server stopped.")
            sys.exit(0)
    else:
        # Run traditional tkinter GUI
        # Import dependencies after argument parsing and only when needed
        import_dependencies()
        
        # Create and run slideshow
        slideshow = ImageSlideshow(
            image_files,
            speed=args.speed,
            repeat=args.repeat,
            fit_mode=args.fit_mode,
            status_format=status_format,
            always_on_top=args.always_on_top,
            shuffle=args.shuffle
        )
        
        try:
            slideshow.run()
        except KeyboardInterrupt:
            print("\nSlideshow interrupted.")
            sys.exit(0)


if __name__ == '__main__':
    main()