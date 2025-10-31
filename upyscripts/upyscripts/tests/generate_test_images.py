#!/usr/bin/env python3
"""
Generate test images for qslideshow testing.
Creates a variety of patterned images for testing gallery and slideshow modes.
"""

from PIL import Image, ImageDraw, ImageFont
import random
import math
from pathlib import Path


def create_solid_color(size, color, number):
    """Create solid color image with number label."""
    img = Image.new('RGB', size, color)
    draw = ImageDraw.Draw(img)

    # Draw number in contrasting color
    contrast_color = (255 - color[0], 255 - color[1], 255 - color[2])
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except:
        font = ImageFont.load_default()

    text = str(number)
    # Get text bounding box for centering
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2

    draw.text((x, y), text, fill=contrast_color, font=font)
    return img


def create_gradient(size, start_color, end_color, number):
    """Create gradient image."""
    img = Image.new('RGB', size)
    draw = ImageDraw.Draw(img)

    for y in range(size[1]):
        ratio = y / size[1]
        r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
        draw.line([(0, y), (size[0], y)], fill=(r, g, b))

    # Add label
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except:
        font = ImageFont.load_default()

    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2

    # Draw with outline for visibility
    for dx in [-2, 0, 2]:
        for dy in [-2, 0, 2]:
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    return img


def create_checkerboard(size, color1, color2, squares, number):
    """Create checkerboard pattern."""
    img = Image.new('RGB', size)
    square_size = size[0] // squares

    for row in range(squares):
        for col in range(squares):
            color = color1 if (row + col) % 2 == 0 else color2
            x0 = col * square_size
            y0 = row * square_size
            x1 = x0 + square_size
            y1 = y0 + square_size

            draw = ImageDraw.Draw(img)
            draw.rectangle([x0, y0, x1, y1], fill=color)

    # Add label
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except:
        font = ImageFont.load_default()

    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2

    for dx in [-2, 0, 2]:
        for dy in [-2, 0, 2]:
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
    draw.text((x, y), text, fill=(255, 255, 0), font=font)

    return img


def create_stripes(size, color1, color2, stripe_count, vertical, number):
    """Create striped pattern."""
    img = Image.new('RGB', size)
    draw = ImageDraw.Draw(img)

    if vertical:
        stripe_width = size[0] // stripe_count
        for i in range(stripe_count):
            color = color1 if i % 2 == 0 else color2
            x0 = i * stripe_width
            x1 = x0 + stripe_width
            draw.rectangle([x0, 0, x1, size[1]], fill=color)
    else:
        stripe_height = size[1] // stripe_count
        for i in range(stripe_count):
            color = color1 if i % 2 == 0 else color2
            y0 = i * stripe_height
            y1 = y0 + stripe_height
            draw.rectangle([0, y0, size[0], y1], fill=color)

    # Add label
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except:
        font = ImageFont.load_default()

    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2

    for dx in [-2, 0, 2]:
        for dy in [-2, 0, 2]:
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    return img


def create_circles(size, bg_color, circle_color, count, number):
    """Create pattern with circles."""
    img = Image.new('RGB', size, bg_color)
    draw = ImageDraw.Draw(img)

    for i in range(count):
        angle = (2 * math.pi * i) / count
        radius = min(size) // 4
        center_x = size[0] // 2 + int(radius * math.cos(angle))
        center_y = size[1] // 2 + int(radius * math.sin(angle))
        circle_radius = min(size) // 8

        bbox = [center_x - circle_radius, center_y - circle_radius,
                center_x + circle_radius, center_y + circle_radius]
        draw.ellipse(bbox, fill=circle_color)

    # Add label
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except:
        font = ImageFont.load_default()

    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2

    for dx in [-2, 0, 2]:
        for dy in [-2, 0, 2]:
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    return img


def generate_test_images(output_dir, count=30, size=(800, 800)):
    """Generate a collection of test images with various patterns."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Generating {count} test images in {output_path}...")

    # Color palette
    colors = [
        (255, 0, 0),      # Red
        (0, 255, 0),      # Green
        (0, 0, 255),      # Blue
        (255, 255, 0),    # Yellow
        (255, 0, 255),    # Magenta
        (0, 255, 255),    # Cyan
        (255, 128, 0),    # Orange
        (128, 0, 255),    # Purple
        (0, 128, 255),    # Sky blue
        (128, 255, 0),    # Lime
    ]

    for i in range(count):
        num = i + 1

        if i < 10:
            # Solid colors
            color = colors[i % len(colors)]
            img = create_solid_color(size, color, num)
        elif i < 15:
            # Gradients
            start = colors[(i - 10) % len(colors)]
            end = colors[(i - 9) % len(colors)]
            img = create_gradient(size, start, end, num)
        elif i < 20:
            # Checkerboards
            c1 = colors[(i - 15) * 2 % len(colors)]
            c2 = colors[(i - 14) * 2 % len(colors)]
            squares = 4 + (i - 15)
            img = create_checkerboard(size, c1, c2, squares, num)
        elif i < 25:
            # Stripes
            c1 = colors[(i - 20) * 2 % len(colors)]
            c2 = colors[(i - 19) * 2 % len(colors)]
            vertical = (i - 20) % 2 == 0
            img = create_stripes(size, c1, c2, 8 + (i - 20), vertical, num)
        else:
            # Circles
            bg = colors[(i - 25) * 2 % len(colors)]
            fg = colors[(i - 24) * 2 % len(colors)]
            circle_count = 3 + (i - 25)
            img = create_circles(size, bg, fg, circle_count, num)

        filename = output_path / f"test_image_{num:03d}.png"
        img.save(filename)
        print(f"  Created: {filename}")

    print(f"\nSuccessfully generated {count} test images!")
    print(f"You can now test qslideshow with:")
    print(f"  upy.qslideshow {output_path} --web --web-gallery")


if __name__ == '__main__':
    import sys

    # Default output directory (tests/test_images/)
    default_dir = Path(__file__).parent / 'test_images'

    if len(sys.argv) > 1:
        output_dir = sys.argv[1]
    else:
        output_dir = default_dir

    count = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    generate_test_images(output_dir, count)
