#!/usr/bin/env python3
"""
Image Side-by-Side Generator
Creates combined images showing multiple images side by side.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple
from PIL import Image


def parse_color(color_str: str) -> Tuple[int, int, int]:
    """
    Parse color string to RGB tuple.
    Supports hex format (#RRGGBB) and common color names.

    Args:
        color_str: Color as hex (#RRGGBB) or name

    Returns:
        RGB tuple (r, g, b)
    """
    # Common color names
    color_names = {
        'black': (0, 0, 0),
        'white': (255, 255, 255),
        'red': (255, 0, 0),
        'green': (0, 255, 0),
        'blue': (0, 0, 255),
        'yellow': (255, 255, 0),
        'cyan': (0, 255, 255),
        'magenta': (255, 0, 255),
    }

    color_lower = color_str.lower()
    if color_lower in color_names:
        return color_names[color_lower]

    # Parse hex color
    if color_str.startswith('#'):
        color_str = color_str[1:]

    if len(color_str) != 6:
        raise ValueError(f"Invalid color format: {color_str}. Use #RRGGBB or color name.")

    try:
        r = int(color_str[0:2], 16)
        g = int(color_str[2:4], 16)
        b = int(color_str[4:6], 16)
        return (r, g, b)
    except ValueError:
        raise ValueError(f"Invalid hex color: {color_str}")


def parse_list_file(list_path: Path, input_dir: Path) -> List[List[Path]]:
    """
    Parse the list file and resolve image paths.

    Args:
        list_path: Path to the list file
        input_dir: Base directory for resolving relative paths

    Returns:
        List of image path lists, one per output image
    """
    if not list_path.exists():
        print(f"Error: List file '{list_path}' does not exist!")
        sys.exit(1)

    result = []
    line_num = 0

    with open(list_path, 'r', encoding='utf-8') as f:
        for line in f:
            line_num += 1
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Parse comma-separated paths
            raw_paths = [p.strip() for p in line.split(',')]
            if not raw_paths:
                continue

            # Resolve paths
            resolved_paths = []
            for raw_path in raw_paths:
                if not raw_path:
                    continue

                path = Path(raw_path)

                # Check if absolute
                if path.is_absolute():
                    resolved_paths.append(path)
                else:
                    # Relative to input_dir
                    resolved_paths.append(input_dir / path)

            if resolved_paths:
                result.append(resolved_paths)

    return result


def create_side_by_side(
    image_paths: List[Path],
    output_path: Path,
    separator_width: int,
    separator_color: Tuple[int, int, int],
    output_format: str,
    quality: int
) -> bool:
    """
    Create a side-by-side image from multiple images.
    All images are normalized to the first image's resolution.

    Args:
        image_paths: List of image paths to combine
        output_path: Where to save the combined image
        separator_width: Width of separator in pixels (0 to disable)
        separator_color: RGB tuple for separator color
        output_format: Output format (jpg, png, etc.)
        quality: JPEG/WebP quality (1-100)

    Returns:
        True if successful, False otherwise
    """
    if not image_paths:
        return False

    # Check all files exist
    missing = []
    for img_path in image_paths:
        if not img_path.exists():
            missing.append(str(img_path))

    if missing:
        print(f"  Error: Missing image(s):")
        for m in missing:
            print(f"    - {m}")
        return False

    try:
        # Load all images
        images = [Image.open(path) for path in image_paths]

        # Use first image's dimensions as target
        target_width, target_height = images[0].size

        # Resize all images to match first image's dimensions
        resized_images = [images[0]]
        for img in images[1:]:
            if img.size != (target_width, target_height):
                resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                resized_images.append(resized)
            else:
                resized_images.append(img)

        # Calculate combined dimensions
        num_images = len(resized_images)
        num_separators = num_images - 1 if separator_width > 0 else 0
        combined_width = (target_width * num_images) + (separator_width * num_separators)
        combined_height = target_height

        # Create combined image
        combined = Image.new('RGB', (combined_width, combined_height), separator_color)

        # Paste images
        x_offset = 0
        for img in resized_images:
            combined.paste(img, (x_offset, 0))
            x_offset += target_width + separator_width

        # Save combined image
        save_kwargs = {}
        format_lower = output_format.lower()
        if format_lower in ['jpg', 'jpeg']:
            save_kwargs['quality'] = quality
            # Pillow expects 'JPEG' not 'JPG'
            pil_format = 'JPEG'
        elif format_lower == 'webp':
            save_kwargs['quality'] = quality
            pil_format = 'WEBP'
        else:
            pil_format = output_format.upper()

        combined.save(output_path, pil_format, **save_kwargs)

        # Close all images (ignore errors during cleanup)
        try:
            for img in images:
                img.close()
            for img in resized_images[1:]:  # First one is same as images[0]
                if img not in images:
                    img.close()
            combined.close()
        except:
            pass  # Ignore cleanup errors

        return True

    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    """Main function to process image combinations."""
    parser = argparse.ArgumentParser(
        description='Create side-by-side comparison images from multiple images.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input-dir ./photos -l list.txt
  %(prog)s --input-dir ./images -l pairs.txt -o ./output
  %(prog)s --input-dir . -l list.txt -f png --quality 100
  %(prog)s --input-dir . -l list.txt --separator-width 0
  %(prog)s --input-dir . -l list.txt --separator-width 20 --separator-color red
  %(prog)s --input-dir . -l list.txt --prefix comparison

List file format:
  # Lines starting with # are comments
  # Each line = one output image (comma-separated paths)
  image1.jpg,image2.jpg
  photo1.png,photo2.png,photo3.png
  /absolute/path/img.jpg,relative/img2.jpg
        """
    )

    # Required arguments
    parser.add_argument(
        '--input-dir',
        required=True,
        help='Base directory for resolving relative image paths'
    )

    parser.add_argument(
        '-l', '--list',
        required=True,
        help='List file with comma-separated image paths per line'
    )

    # Output options
    parser.add_argument(
        '-o', '--output',
        default='./sxs-output',
        help='Output folder (default: ./sxs-output)'
    )

    parser.add_argument(
        '-f', '--format',
        default='jpg',
        help='Output format: jpg, png, webp, etc. (default: jpg)'
    )

    parser.add_argument(
        '--quality',
        type=int,
        default=95,
        help='JPEG/WebP quality 1-100 (default: 95)'
    )

    parser.add_argument(
        '--prefix',
        default='sxs',
        help='Output filename prefix (default: sxs)'
    )

    # Separator options
    parser.add_argument(
        '--separator-width',
        type=int,
        default=10,
        help='Separator width in pixels (default: 10, specify 0 to disable)'
    )

    parser.add_argument(
        '--separator-color',
        default='#00FF00',
        help='Separator color as #RRGGBB or color name (default: #00FF00)'
    )

    # Other options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview operations without creating files'
    )

    args = parser.parse_args()

    # Validate input directory
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: Input directory '{args.input_dir}' does not exist!")
        return 1

    if not input_dir.is_dir():
        print(f"Error: '{args.input_dir}' is not a directory!")
        return 1

    # Validate list file
    list_path = Path(args.list)

    # Parse separator color
    try:
        separator_color = parse_color(args.separator_color)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Validate quality
    if args.quality < 1 or args.quality > 100:
        print("Error: Quality must be between 1 and 100")
        return 1

    # Parse list file
    print(f"Input directory: {input_dir.absolute()}")
    print(f"List file: {list_path.absolute()}")
    print(f"Output folder: {Path(args.output).absolute()}")
    print(f"Output format: {args.format}")
    print(f"Quality: {args.quality}")
    print(f"Separator: {'disabled' if args.separator_width == 0 else f'{args.separator_width}px, color {args.separator_color}'}")
    print(f"Dry run: {'Yes' if args.dry_run else 'No'}")
    print()

    image_sets = parse_list_file(list_path, input_dir)

    if not image_sets:
        print("No image sets found in list file!")
        return 0

    print(f"Found {len(image_sets)} image set(s) to process")
    print()

    # Create output directory if not dry run
    output_dir = Path(args.output)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Process each set
    success_count = 0
    for idx, image_paths in enumerate(image_sets, start=1):
        output_filename = f"{args.prefix}-{idx:03d}.{args.format}"
        output_path = output_dir / output_filename

        print(f"[{idx}/{len(image_sets)}] Processing:")
        for i, img_path in enumerate(image_paths, start=1):
            print(f"  {i}. {img_path}")
        print(f"  → {output_filename}")

        if args.dry_run:
            print("  (dry run - not creating file)")
            success_count += 1
        else:
            if create_side_by_side(
                image_paths,
                output_path,
                args.separator_width,
                separator_color,
                args.format,
                args.quality
            ):
                print(f"  ✓ Created successfully")
                success_count += 1

        print()

    print(f"Done! {'Would create' if args.dry_run else 'Created'} {success_count}/{len(image_sets)} image(s)")
    if not args.dry_run:
        print(f"Output location: {output_dir.absolute()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
