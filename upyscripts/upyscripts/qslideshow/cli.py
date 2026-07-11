#!/usr/bin/env python3
"""
Command-line interface for qslideshow.
Handles argument parsing and orchestrates between GUI and web server modes.
"""

import argparse
import sys

from .core import (
    TEMPLATE_VARIABLES,
    STATUS_PRESETS,
    get_variable_descriptions,
    get_status_template,
    collect_images_from_paths
)
from .config import ConfigManager


def parse_grid_size(value):
    """
    Parse grid size in ROWSxCOLS format (e.g., '4x5' = 4 rows, 5 columns).
    Returns tuple (rows, cols) or raises argparse.ArgumentTypeError.
    """
    if not value or value.lower() == 'auto':
        return None  # Auto/responsive mode
    try:
        parts = value.lower().split('x')
        if len(parts) != 2:
            raise ValueError
        rows, cols = int(parts[0]), int(parts[1])
        if rows < 1 or cols < 1:
            raise ValueError("Grid dimensions must be positive")
        if rows > 50 or cols > 50:
            raise ValueError("Grid dimensions too large (max 50x50)")
        return (rows, cols)
    except (ValueError, IndexError) as e:
        raise argparse.ArgumentTypeError(
            f"Invalid grid size '{value}'. Use format: ROWSxCOLS (e.g., '4x5') or 'auto'"
        ) from e


def parse_size(value):
    """
    Parse size in WIDTHxHEIGHT format (e.g., '200x200').
    Returns tuple (width, height) or raises argparse.ArgumentTypeError.
    """
    try:
        parts = value.lower().split('x')
        if len(parts) != 2:
            raise ValueError
        width, height = int(parts[0]), int(parts[1])
        if width < 10 or height < 10:
            raise ValueError("Dimensions must be at least 10x10 pixels")
        if width > 2000 or height > 2000:
            raise ValueError("Dimensions too large (max 2000x2000)")
        return (width, height)
    except (ValueError, IndexError) as e:
        raise argparse.ArgumentTypeError(
            f"Invalid size '{value}'. Use format: WIDTHxHEIGHT (e.g., '200x200')"
        ) from e


def parse_arguments(args=None):
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
  %(prog)s /path/to/images                    # GUI mode with single folder
  %(prog)s folder1 folder2 folder3            # Multiple folders
  %(prog)s ~/Pictures ~/Downloads/*.jpg       # Mix folders and specific files
  %(prog)s /path/to/images --web              # Web server mode
  %(prog)s /path/to/images --web --port 8080  # Web server on custom port
  %(prog)s dir1 dir2 --recursive --speed 5    # Multiple dirs with recursion
  %(prog)s @image_list.txt --repeat            # Using response file
  %(prog)s . ~/Photos -r -x "*.gif" -x "*.ico" # Current dir + another with exclusions

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
  0-9: Execute external tools (when --external-tools is used)
  Q/Escape: Quit

Template variables:
{get_variable_descriptions()}
        '''
    )

    # Make paths optional if --generate-config is used
    parser.add_argument(
        'paths',
        nargs='*',  # Changed from '+' to '*' to make it optional
        help='One or more image folder paths or @response_file'
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=None,
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
        default=None,
        metavar='SECONDS',
        help='Seconds between slides (default: 3.0)'
    )

    parser.add_argument(
        '--repeat',
        action='store_true',
        default=None,
        help='Deprecated alias for --repeat-mode fixed'
    )

    parser.add_argument(
        '--repeat-mode',
        choices=['none', 'fixed', 'shuffle', 'shuffle-each'],
        default=None,
        help='End-of-list behavior (default from config: none)'
    )

    parser.add_argument(
        '-f', '--fit-mode',
        choices=['shrink', 'original'],
        default=None,
        help='Image display mode: shrink (default) or original'
    )

    parser.add_argument(
        '--status',
        type=str,
        help=f'Status text with variables: {", ".join(f"{{{var}}}" for var in TEMPLATE_VARIABLES.keys())}'
    )

    parser.add_argument(
        '--always-on-top',
        action='store_true',
        default=None,
        help='Keep window above all other windows'
    )

    parser.add_argument(
        '--shuffle',
        action='store_true',
        default=None,
        help='Randomize image order'
    )

    parser.add_argument(
        '--paused',
        action='store_true',
        default=None,
        help='Start slideshow in paused mode'
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
        default=None,
        help='Port for web server mode (default: 8000)'
    )

    parser.add_argument(
        '--web-password',
        type=str,
        metavar='PASSWORD',
        help='Optional password for web server access (enables authentication)'
    )

    parser.add_argument(
        '--web-dev',
        action='store_true',
        default=None,
        help='Development mode: disable browser caching for live editing of web files'
    )

    parser.add_argument(
        '--web-gallery',
        nargs='?',
        const='auto',
        type=parse_grid_size,
        metavar='ROWSxCOLS',
        help='Enable gallery mode with grid layout (e.g., "4x5" for 4 rows, 5 columns, '
             'or "auto" for responsive). If used without value, defaults to "auto". '
             'Web mode only.'
    )

    parser.add_argument(
        '--web-gallery-grid',
        type=parse_grid_size,
        metavar='ROWSxCOLS',
        help='Grid size for gallery mode (e.g., "4x5" for 4 rows, 5 columns, or "auto"). '
             'Overrides --web-gallery if both are specified.'
    )

    parser.add_argument(
        '--web-gallery-thumbnail-size',
        type=parse_size,
        metavar='WIDTHxHEIGHT',
        default=None,
        help='Thumbnail size for gallery mode in pixels (default: 200x200, e.g., "150x150")'
    )

    # Generate QSS_* environment variable names from TEMPLATE_VARIABLES
    qss_vars = ', '.join(f'QSS_{var.upper()}' for var in TEMPLATE_VARIABLES.keys())

    parser.add_argument(
        '--external-tools',
        type=str,
        metavar='SCRIPT_NAME',
        help=f'Enable external tool hotkeys (0-9). Looks for scripts matching '
             f'SCRIPT_NAME[0-9].ext in current directory. Scripts receive QSS_* '
             f'environment variables: {qss_vars}. Return code 0: no action, '
             f'1: remove image from list.'
    )
    
    parser.add_argument(
        '--filter-script',
        type=str,
        metavar='PATH',
        help='Path to a pre-display filter script. Called before each image is shown. '
             'Return code 0: show image, non-zero: skip. Receives QSS_* env vars.'
    )

    parser.add_argument(
        '--post-script',
        type=str,
        metavar='PATH',
        help='Path to a post-tool hook script. Called after any external tool (0-9) runs. '
             'Receives QSS_* env vars plus QSS_TOOL_RC, QSS_TOOL_STDOUT, QSS_TOOL_STDERR, '
             'QSS_PREV_FULL_PATH, QSS_PREV_IMG_NAME, QSS_IMG_REMOVED.'
    )

    parser.add_argument(
        '--generate-config',
        action='store_true',
        help='Generate a default config file in current directory and exit'
    )
    
    parser.add_argument(
        '--config',
        metavar='PATH',
        help='Path to configuration file (default: search for qslideshow.yaml)'
    )

    return parser.parse_args(args)


def main():
    """Main entry point."""
    # Parse arguments first
    args = parse_arguments()
    
    # Initialize configuration manager
    config_manager = ConfigManager()
    
    # Handle --generate-config option
    if args.generate_config:
        path = config_manager.generate_default_config_file()
        print(f"Generated default config file: {path}")
        sys.exit(0)
    
    # Load config from file if specified or find default
    config_path = getattr(args, 'config', None)
    config_manager.load_config(config_path)
    
    # Update config with command-line arguments (CLI overrides config file)
    config_manager.update_from_args(args)
    
    # Paths are required if not generating config
    if not args.paths:
        print("Error: No image paths provided. Use --help for usage information.")
        sys.exit(1)

    exclude_patterns = []
    for pattern_arg in config_manager.get('images.exclude_patterns', []) or []:
        exclude_patterns.extend(
            pattern.strip() for pattern in pattern_arg.split(';') if pattern.strip()
        )

    # Collect image files from all specified paths
    image_files = collect_images_from_paths(
        args.paths, 
        recursive=config_manager.get('images.recursive', False),
        exclude_patterns=exclude_patterns,
        additional_extensions=config_manager.get('images.extensions', []),
    )

    if not image_files:
        print("No images found.")
        sys.exit(1)

    print(f"Found {len(image_files)} images")

    # Expand status preset if needed
    status_format = config_manager.get('slideshow.status_format')
    if status_format:
        status_format = get_status_template(status_format)
        config_manager.set('slideshow.status_format', status_format)

    # Apply filter/post script CLI overrides to config
    if hasattr(args, 'filter_script') and args.filter_script:
        config_manager.set('external_tools.filter_script', args.filter_script)
    if hasattr(args, 'post_script') and args.post_script:
        config_manager.set('external_tools.post_script', args.post_script)

    # Check if web mode is requested
    if args.web:
        # Run as web server
        from .webserver import WebSlideshow
        
        # Update config with status format
        if status_format:
            config_manager.set('slideshow.status_format', status_format)
        
        # Pass the config manager which has both file config and CLI overrides
        web_slideshow = WebSlideshow(
            image_files,
            config=config_manager,
            port=config_manager.get('web.port', 8000),
            password=args.web_password if hasattr(args, 'web_password') else None
        )
        
        if config_manager.get('web.dev_mode', False):
            print("🔧 Development mode enabled - browser caching disabled")

        try:
            web_slideshow.run()
        except KeyboardInterrupt:
            print("\nWeb server stopped.")
            sys.exit(0)
    else:
        # Run traditional tkinter GUI
        from .gui import ImageSlideshow, import_dependencies
        
        # Import dependencies after argument parsing and only when needed
        import_dependencies()

        # Update config with status format
        if status_format:
            config_manager.set('slideshow.status_format', status_format)
        
        # Create and run slideshow with config manager
        slideshow = ImageSlideshow(
            image_files,
            config=config_manager,
            status_format=status_format,
        )

        try:
            slideshow.run()
        except KeyboardInterrupt:
            print("\nSlideshow interrupted.")
            sys.exit(0)


if __name__ == '__main__':
    main()
