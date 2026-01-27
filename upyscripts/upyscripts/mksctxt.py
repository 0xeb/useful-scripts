"""
mksctxt - Make Screenshot from Text

Convert markdown files to beautiful, stylized images using PIL/Pillow.
Renders with Dracula theme and syntax highlighting.

Usage:
    upy.mksctxt input.md -o output.png
    upy.mksctxt input.md -o output.png --scale 4
    upy.mksctxt input.md -o output.png --no-window
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Tuple, List

from PIL import Image, ImageDraw, ImageFont
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.token import Token


# Dracula theme colors
COLORS = {
    'background': '#282a36',
    'foreground': '#f8f8f2',
    'comment': '#6272a4',
    'cyan': '#8be9fd',
    'green': '#50fa7b',
    'orange': '#ffb86c',
    'pink': '#ff79c6',
    'purple': '#bd93f9',
    'red': '#ff5555',
    'yellow': '#f1fa8c',
    'titlebar': '#21222c',
    'code_bg': '#1e1f29',
}

# Token to color mapping for syntax highlighting
TOKEN_COLORS = {
    Token.Comment: COLORS['comment'],
    Token.Comment.Single: COLORS['comment'],
    Token.Comment.Multiline: COLORS['comment'],
    Token.Keyword: COLORS['pink'],
    Token.Keyword.Namespace: COLORS['pink'],
    Token.Keyword.Type: COLORS['cyan'],
    Token.Name.Function: COLORS['green'],
    Token.Name.Class: COLORS['green'],
    Token.Name.Decorator: COLORS['green'],
    Token.Name.Builtin: COLORS['cyan'],
    Token.String: COLORS['yellow'],
    Token.String.Doc: COLORS['yellow'],
    Token.Number: COLORS['purple'],
    Token.Operator: COLORS['pink'],
    Token.Punctuation: COLORS['foreground'],
    Token.Name: COLORS['foreground'],
}


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font, using bundled JetBrains Mono or system fallback."""
    # Bundled font path (relative to this script)
    script_dir = Path(__file__).parent
    if bold:
        bundled_font = script_dir / 'mksctxt_fonts' / 'JetBrainsMono-Bold.ttf'
    else:
        bundled_font = script_dir / 'mksctxt_fonts' / 'JetBrainsMono-Regular.ttf'

    # Try bundled font first
    if bundled_font.exists():
        try:
            return ImageFont.truetype(str(bundled_font), size)
        except (OSError, IOError):
            pass

    # Fallback to system fonts
    font_names = ['Consolas', 'Courier New', 'DejaVuSansMono.ttf']
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size)
        except (OSError, IOError):
            continue

    # Last resort
    return ImageFont.load_default()


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int,
    fill: str
):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = xy
    fill_rgb = hex_to_rgb(fill)

    # Draw the main rectangles
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill_rgb)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill_rgb)

    # Draw the corners
    draw.ellipse([x1, y1, x1 + 2*radius, y1 + 2*radius], fill=fill_rgb)
    draw.ellipse([x2 - 2*radius, y1, x2, y1 + 2*radius], fill=fill_rgb)
    draw.ellipse([x1, y2 - 2*radius, x1 + 2*radius, y2], fill=fill_rgb)
    draw.ellipse([x2 - 2*radius, y2 - 2*radius, x2, y2], fill=fill_rgb)


def parse_markdown_simple(text: str) -> List[dict]:
    """
    Simple markdown parser that returns a list of elements.
    Each element is a dict with 'type' and 'content'.
    """
    elements = []
    lines = text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code block
        if line.startswith('```'):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(lines[i])
                i += 1
            elements.append({
                'type': 'code',
                'lang': lang or 'text',
                'content': '\n'.join(code_lines)
            })
            i += 1
            continue

        # Headers
        if line.startswith('# '):
            elements.append({'type': 'h1', 'content': line[2:]})
        elif line.startswith('## '):
            elements.append({'type': 'h2', 'content': line[3:]})
        elif line.startswith('### '):
            elements.append({'type': 'h3', 'content': line[4:]})

        # Blockquote
        elif line.startswith('> '):
            elements.append({'type': 'blockquote', 'content': line[2:]})

        # List item
        elif line.startswith('- ') or line.startswith('* '):
            elements.append({'type': 'list_item', 'content': line[2:]})

        # Empty line
        elif line.strip() == '':
            elements.append({'type': 'spacer', 'content': ''})

        # Regular paragraph
        else:
            elements.append({'type': 'paragraph', 'content': line})

        i += 1

    return elements


def render_code_block(
    code: str,
    lang: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    scale: int = 1
) -> Tuple[Image.Image, int]:
    """
    Render a syntax-highlighted code block.
    Returns the image and its height.
    """
    try:
        lexer = get_lexer_by_name(lang)
    except:
        lexer = guess_lexer(code)

    tokens = list(lexer.get_tokens(code))

    # Calculate dimensions
    lines = code.split('\n')
    line_height = font.size + 6 * scale
    padding = 12 * scale
    height = len(lines) * line_height + padding * 2
    width = max_width

    # Create image with code background
    img = Image.new('RGB', (width, height), hex_to_rgb(COLORS['code_bg']))
    draw = ImageDraw.Draw(img)

    x, y = padding, padding

    for token_type, token_value in tokens:
        # Get color for token
        color = COLORS['foreground']
        for ttype, tcolor in TOKEN_COLORS.items():
            if token_type in ttype or ttype in token_type:
                color = tcolor
                break

        # Handle newlines
        if '\n' in token_value:
            parts = token_value.split('\n')
            for i, part in enumerate(parts):
                if part:
                    draw.text((x, y), part, font=font, fill=hex_to_rgb(color))
                    bbox = font.getbbox(part)
                    x += bbox[2] - bbox[0]
                if i < len(parts) - 1:
                    x = padding
                    y += line_height
        else:
            draw.text((x, y), token_value, font=font, fill=hex_to_rgb(color))
            bbox = font.getbbox(token_value)
            x += bbox[2] - bbox[0]

    return img, height


def render_markdown_to_image(
    markdown_text: str,
    output_path: str,
    width: int = 800,
    scale: int = 2,
    window: bool = True
) -> str:
    """
    Render markdown to an image using Pillow.

    Args:
        markdown_text: The markdown content
        output_path: Where to save the image
        width: Final image width
        scale: Render scale factor (2 = retina quality)
        window: Show macOS-style window frame

    Returns:
        Path to generated image
    """
    elements = parse_markdown_simple(markdown_text)

    # Scale everything for sharp rendering
    s = scale

    # Fonts (scaled)
    font_h1 = get_font(32 * s, bold=True)
    font_h2 = get_font(24 * s, bold=True)
    font_body = get_font(18 * s)
    font_code = get_font(16 * s)

    # Tighter padding (reduced bulkiness)
    padding = 24 * s
    window_padding = 16 * s
    titlebar_height = 32 * s if window else 0

    # Calculate content height
    content_width = width * s - padding * 2

    # First pass: calculate total height
    y = titlebar_height + window_padding
    for elem in elements:
        if elem['type'] == 'h1':
            y += 44 * s
        elif elem['type'] == 'h2':
            y += 36 * s
        elif elem['type'] == 'paragraph':
            y += 28 * s
        elif elem['type'] == 'list_item':
            y += 30 * s
        elif elem['type'] == 'blockquote':
            y += 34 * s
        elif elem['type'] == 'code':
            lines = elem['content'].split('\n')
            y += len(lines) * 22 * s + 24 * s + 12 * s
        elif elem['type'] == 'spacer':
            y += 8 * s

    content_height = y + window_padding
    total_height = content_height

    # Create image with just the content box (no gradient background)
    img = Image.new('RGB', (width * s, total_height), hex_to_rgb(COLORS['background']))
    draw = ImageDraw.Draw(img)

    # Window dimensions (full image, no padding)
    window_x = 0
    window_y = 0
    window_w = width * s
    window_h = content_height

    # Draw titlebar and dots (only if window frame enabled)
    if window:
        draw_rounded_rect(draw, (window_x, window_y, window_x + window_w, window_y + titlebar_height), 10 * s, COLORS['titlebar'])
        draw.rectangle([window_x, window_y + titlebar_height - 10 * s, window_x + window_w, window_y + titlebar_height],
                       fill=hex_to_rgb(COLORS['titlebar']))

        # Draw dots
        dot_y = window_y + titlebar_height // 2
        dot_colors = ['#ff5f56', '#ffbd2e', '#27ca3f']
        for i, color in enumerate(dot_colors):
            dot_x = window_x + 14 * s + i * 18 * s
            r = 6 * s
            draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], fill=hex_to_rgb(color))

    # Render content
    x = window_x + window_padding
    y = window_y + titlebar_height + window_padding

    for elem in elements:
        if elem['type'] == 'h1':
            draw.text((x, y), elem['content'], font=font_h1, fill=hex_to_rgb(COLORS['purple']))
            y += 44 * s
        elif elem['type'] == 'h2':
            draw.text((x, y), elem['content'], font=font_h2, fill=hex_to_rgb(COLORS['pink']))
            y += 36 * s
        elif elem['type'] == 'paragraph':
            text = elem['content']
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'\*(.+?)\*', r'\1', text)
            draw.text((x, y), text, font=font_body, fill=hex_to_rgb(COLORS['foreground']))
            y += 28 * s
        elif elem['type'] == 'list_item':
            draw.text((x, y), '\u2022', font=font_body, fill=hex_to_rgb(COLORS['pink']))
            draw.text((x + 20 * s, y), elem['content'], font=font_body, fill=hex_to_rgb(COLORS['foreground']))
            y += 30 * s
        elif elem['type'] == 'blockquote':
            draw.rectangle([x, y, x + 4 * s, y + 24 * s], fill=hex_to_rgb(COLORS['purple']))
            draw.text((x + 14 * s, y), elem['content'], font=font_body, fill=hex_to_rgb(COLORS['comment']))
            y += 34 * s
        elif elem['type'] == 'code':
            code_img, code_h = render_code_block(elem['content'], elem['lang'], font_code, content_width - window_padding * 2, scale=s)
            img.paste(code_img, (x, y))
            y += code_h + 12 * s
        elif elem['type'] == 'spacer':
            y += 8 * s

    # Save image
    img.save(output_path, quality=95)
    return output_path


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='mksctxt - Convert markdown to styled images',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.md -o output.png
  %(prog)s input.md -o output.png --scale 4
  %(prog)s input.md -o output.png --no-window
  %(prog)s input.md -o output.png -w 1200
"""
    )

    parser.add_argument('input', nargs='?', help='Input markdown file')
    parser.add_argument('-o', '--output', default='output.png', help='Output image path (default: output.png)')
    parser.add_argument('-w', '--width', type=int, default=800, help='Image width (default: 800)')
    parser.add_argument('-s', '--scale', type=int, default=2, choices=[1, 2, 3, 4],
                        help='Resolution scale (default: 2, use 4 for high-res)')
    parser.add_argument('--no-window', action='store_true', help='Disable macOS-style window frame')

    args = parser.parse_args()

    if not args.input:
        parser.error("Input file is required")

    # Read input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    markdown_text = input_path.read_text(encoding='utf-8')

    # Render
    try:
        result = render_markdown_to_image(
            markdown_text,
            args.output,
            width=args.width,
            scale=args.scale,
            window=not args.no_window
        )
        print(f"Generated: {result}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
