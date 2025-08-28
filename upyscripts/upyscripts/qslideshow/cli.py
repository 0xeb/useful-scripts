#!/usr/bin/env python3
"""
Command-line interface for qslideshow.
Handles argument parsing and orchestrates between GUI and web server modes.
"""

import argparse
import sys
from pathlib import Path

from .core import (
    TEMPLATE_VARIABLES,
    STATUS_PRESETS,
    get_variable_descriptions,
    get_status_template,
    collect_images_from_paths
)


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

    parser.add_argument(
        'paths',
        nargs='+',
        help='One or more image folder paths or @response_file'
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
        help=f'Status text with variables: {", ".join(f"{{{var}}}" for var in TEMPLATE_VARIABLES.keys())}'
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
        '--paused',
        action='store_true',
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
        default=8000,
        help='Port for web server mode (default: 8000)'
    )

    parser.add_argument(
        '--web-dev',
        action='store_true',
        help='Development mode: disable browser caching for live editing of web files'
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

    return parser.parse_args()


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

    # Collect image files from all specified paths
    image_files = collect_images_from_paths(
        args.paths, 
        recursive=args.recursive,
        exclude_patterns=exclude_patterns
    )

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
        from .webserver import WebSlideshow
        
        config = {
            'speed': args.speed,
            'repeat': args.repeat,
            'fit_mode': args.fit_mode,
            'status_format': status_format,
            'always_on_top': args.always_on_top,
            'shuffle': args.shuffle,
            'paused': args.paused,
            'web_dev': getattr(args, 'web_dev', False)
        }

        web_slideshow = WebSlideshow(
            image_files,
            config=config,
            port=args.port
        )
        
        if args.web_dev:
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

        # Create and run slideshow
        slideshow = ImageSlideshow(
            image_files,
            speed=args.speed,
            repeat=args.repeat,
            fit_mode=args.fit_mode,
            status_format=status_format,
            always_on_top=args.always_on_top,
            shuffle=args.shuffle,
            external_tools=args.external_tools,
            paused=args.paused
        )

        try:
            slideshow.run()
        except KeyboardInterrupt:
            print("\nSlideshow interrupted.")
            sys.exit(0)


if __name__ == '__main__':
    main()