#!/usr/bin/env python3
"""
Core slideshow logic and utilities.
Contains shared components used by both GUI and web server implementations.
"""

import random
import fnmatch
from pathlib import Path
from typing import List, Optional, Dict


# Default image file extensions
DEFAULT_IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.tiff', '.tif', '.webp', '.ico', '.svg'
}

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
    return '\n'.join(f"  {{{var}}}: {desc}" for var, desc in TEMPLATE_VARIABLES.items())

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


class SlideshowContext:
    """Holds the complete state and context of the slideshow."""

    def __init__(self, image_paths: List[Path], speed: float = 3.0, repeat: bool = False,
                 fit_mode: str = 'shrink', status_format: Optional[str] = None,
                 always_on_top: bool = False, shuffle: bool = False, paused: bool = False):
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
        self.is_paused = paused
        self.repeat_count = 0

        # Apply shuffle if requested
        if self.shuffle:
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


def find_images(directory: Path, recursive: bool, exclude_patterns: List[str] = []) -> List[Path]:
    """Find all image files in a directory, case-insensitively."""
    if not directory.is_dir():
        print(f"Error: Path is not a directory: {directory}")
        return []

    image_files = []

    # Create a case-insensitive set of extensions
    extensions = {ext.lower() for ext in DEFAULT_IMAGE_EXTENSIONS}

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
                        if path.suffix.lower() in DEFAULT_IMAGE_EXTENSIONS:
                            image_files.append(path)
    except Exception as e:
        print(f"Error reading response file: {e}")

    return image_files


def collect_images_from_paths(path_args: List[str], recursive: bool = False, 
                             exclude_patterns: List[str] = None) -> List[Path]:
    """
    Collect image files from multiple paths, handling directories, files, and response files.
    
    Args:
        path_args: List of path strings (directories, files, or @response_files)
        recursive: Whether to search subdirectories recursively
        exclude_patterns: List of patterns to exclude from search
        
    Returns:
        List of unique image file paths, preserving discovery order
    """
    if exclude_patterns is None:
        exclude_patterns = []
        
    image_files = []
    
    for path_arg in path_args:
        if path_arg.startswith('@'):
            # Response file
            response_file = Path(path_arg[1:])
            image_files.extend(parse_response_file(response_file))
        else:
            # Directory or file
            path = Path(path_arg)
            if path.is_dir():
                # Search directory for images
                images = find_images(path, recursive, exclude_patterns)
                image_files.extend(images)
            elif path.is_file():
                # Single file directly specified
                if path.suffix.lower() in {ext.lower() for ext in DEFAULT_IMAGE_EXTENSIONS}:
                    # Check against exclude patterns
                    if not any(fnmatch.fnmatch(path.name, p) for p in exclude_patterns):
                        image_files.append(path)
                else:
                    print(f"Warning: {path} is not a recognized image file")
            else:
                print(f"Warning: Path does not exist: {path}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_files = []
    for f in image_files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(f)
    
    return unique_files