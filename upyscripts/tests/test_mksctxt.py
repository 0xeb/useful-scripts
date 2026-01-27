"""
Tests for mksctxt - Markdown to image converter.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from upyscripts.mksctxt import (
    hex_to_rgb,
    parse_markdown_simple,
    get_font,
    draw_rounded_rect,
    render_code_block,
    render_markdown_to_image,
    COLORS,
)


class TestHexToRgb:
    """Tests for hex_to_rgb function."""

    def test_basic_colors(self):
        assert hex_to_rgb('#ff0000') == (255, 0, 0)
        assert hex_to_rgb('#00ff00') == (0, 255, 0)
        assert hex_to_rgb('#0000ff') == (0, 0, 255)

    def test_without_hash(self):
        assert hex_to_rgb('ff0000') == (255, 0, 0)

    def test_black_and_white(self):
        assert hex_to_rgb('#000000') == (0, 0, 0)
        assert hex_to_rgb('#ffffff') == (255, 255, 255)

    def test_dracula_colors(self):
        assert hex_to_rgb('#282a36') == (40, 42, 54)
        assert hex_to_rgb('#f8f8f2') == (248, 248, 242)
        assert hex_to_rgb('#bd93f9') == (189, 147, 249)


class TestParseMarkdownSimple:
    """Tests for parse_markdown_simple function."""

    def test_h1_header(self):
        elements = parse_markdown_simple('# Hello World')
        assert len(elements) == 1
        assert elements[0]['type'] == 'h1'
        assert elements[0]['content'] == 'Hello World'

    def test_h2_header(self):
        elements = parse_markdown_simple('## Section Title')
        assert len(elements) == 1
        assert elements[0]['type'] == 'h2'
        assert elements[0]['content'] == 'Section Title'

    def test_h3_header(self):
        elements = parse_markdown_simple('### Subsection')
        assert len(elements) == 1
        assert elements[0]['type'] == 'h3'
        assert elements[0]['content'] == 'Subsection'

    def test_paragraph(self):
        elements = parse_markdown_simple('This is a paragraph.')
        assert len(elements) == 1
        assert elements[0]['type'] == 'paragraph'
        assert elements[0]['content'] == 'This is a paragraph.'

    def test_list_item_dash(self):
        elements = parse_markdown_simple('- Item one')
        assert len(elements) == 1
        assert elements[0]['type'] == 'list_item'
        assert elements[0]['content'] == 'Item one'

    def test_list_item_asterisk(self):
        elements = parse_markdown_simple('* Item two')
        assert len(elements) == 1
        assert elements[0]['type'] == 'list_item'
        assert elements[0]['content'] == 'Item two'

    def test_blockquote(self):
        elements = parse_markdown_simple('> This is a quote')
        assert len(elements) == 1
        assert elements[0]['type'] == 'blockquote'
        assert elements[0]['content'] == 'This is a quote'

    def test_code_block_with_language(self):
        md = '```python\nprint("hello")\n```'
        elements = parse_markdown_simple(md)
        assert len(elements) == 1
        assert elements[0]['type'] == 'code'
        assert elements[0]['lang'] == 'python'
        assert elements[0]['content'] == 'print("hello")'

    def test_code_block_without_language(self):
        md = '```\nsome code\n```'
        elements = parse_markdown_simple(md)
        assert len(elements) == 1
        assert elements[0]['type'] == 'code'
        assert elements[0]['lang'] == 'text'
        assert elements[0]['content'] == 'some code'

    def test_code_block_multiline(self):
        md = '```javascript\nconst x = 1;\nconst y = 2;\nconsole.log(x + y);\n```'
        elements = parse_markdown_simple(md)
        assert len(elements) == 1
        assert elements[0]['type'] == 'code'
        assert elements[0]['lang'] == 'javascript'
        assert 'const x = 1;' in elements[0]['content']
        assert 'console.log(x + y);' in elements[0]['content']

    def test_empty_line_spacer(self):
        elements = parse_markdown_simple('')
        assert len(elements) == 1
        assert elements[0]['type'] == 'spacer'

    def test_multiple_elements(self):
        md = '''# Title

This is a paragraph.

- Item 1
- Item 2

```python
x = 1
```'''
        elements = parse_markdown_simple(md)
        types = [e['type'] for e in elements]
        assert 'h1' in types
        assert 'paragraph' in types
        assert 'list_item' in types
        assert 'code' in types
        assert 'spacer' in types

    def test_empty_input(self):
        elements = parse_markdown_simple('')
        assert len(elements) == 1
        assert elements[0]['type'] == 'spacer'


class TestGetFont:
    """Tests for get_font function."""

    def test_returns_font(self):
        font = get_font(16)
        assert font is not None

    def test_bold_font(self):
        font = get_font(16, bold=True)
        assert font is not None

    def test_different_sizes(self):
        font_small = get_font(12)
        font_large = get_font(24)
        assert font_small is not None
        assert font_large is not None


class TestDrawRoundedRect:
    """Tests for draw_rounded_rect function."""

    def test_draws_without_error(self):
        img = Image.new('RGB', (100, 100), (255, 255, 255))
        draw = img.im  # Get internal image
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)

        # Should not raise
        draw_rounded_rect(draw, (10, 10, 90, 90), 10, '#ff0000')

    def test_small_radius(self):
        img = Image.new('RGB', (100, 100), (255, 255, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)

        draw_rounded_rect(draw, (10, 10, 90, 90), 2, '#0000ff')

    def test_zero_radius(self):
        img = Image.new('RGB', (100, 100), (255, 255, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)

        draw_rounded_rect(draw, (10, 10, 90, 90), 0, '#00ff00')


class TestRenderCodeBlock:
    """Tests for render_code_block function."""

    def test_python_code(self):
        code = 'print("hello")'
        font = get_font(16)
        img, height = render_code_block(code, 'python', font, 400, scale=1)

        assert isinstance(img, Image.Image)
        assert height > 0
        assert img.width == 400

    def test_javascript_code(self):
        code = 'const x = 1;\nconsole.log(x);'
        font = get_font(16)
        img, height = render_code_block(code, 'javascript', font, 400, scale=1)

        assert isinstance(img, Image.Image)
        assert height > 0

    def test_unknown_language_fallback(self):
        code = 'some random code'
        font = get_font(16)
        # Should not raise, falls back to guessing
        img, height = render_code_block(code, 'unknownlang123', font, 400, scale=1)

        assert isinstance(img, Image.Image)

    def test_multiline_code(self):
        code = 'line1\nline2\nline3\nline4'
        font = get_font(16)
        img, height = render_code_block(code, 'text', font, 400, scale=1)

        # Height should account for multiple lines
        assert height > 50

    def test_empty_code(self):
        code = ''
        font = get_font(16)
        img, height = render_code_block(code, 'text', font, 400, scale=1)

        assert isinstance(img, Image.Image)

    def test_scale_factor(self):
        code = 'x = 1'
        font = get_font(32)  # Scaled font
        img1, height1 = render_code_block(code, 'python', font, 400, scale=1)
        img2, height2 = render_code_block(code, 'python', font, 400, scale=2)

        # Height with scale=2 should be larger
        assert height2 > height1


class TestRenderMarkdownToImage:
    """Tests for render_markdown_to_image function."""

    def test_basic_render(self):
        md = '# Hello\n\nThis is a test.'
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            result = render_markdown_to_image(md, output_path)
            assert result == output_path
            assert os.path.exists(output_path)

            # Verify it's a valid image
            with Image.open(output_path) as img:
                assert img.width > 0
                assert img.height > 0
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_with_code_block(self):
        md = '# Code Example\n\n```python\nprint("hello")\n```'
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            result = render_markdown_to_image(md, output_path)
            assert os.path.exists(output_path)

            with Image.open(output_path) as img:
                assert img.width > 0
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_custom_width(self):
        md = '# Test'
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            render_markdown_to_image(md, output_path, width=1200, scale=1)
            with Image.open(output_path) as img:
                assert img.width == 1200
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_scale_factor(self):
        md = '# Test'
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            render_markdown_to_image(md, output_path, width=400, scale=2)
            with Image.open(output_path) as img:
                # With scale=2, actual width is 400*2=800
                assert img.width == 800
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_no_window_frame(self):
        md = '# Test'
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path1 = f.name
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path2 = f.name

        try:
            render_markdown_to_image(md, output_path1, window=True, scale=1)
            render_markdown_to_image(md, output_path2, window=False, scale=1)

            with Image.open(output_path1) as img1:
                height1 = img1.height
            with Image.open(output_path2) as img2:
                height2 = img2.height

            # With window frame, image should be taller
            assert height1 > height2
        finally:
            for p in [output_path1, output_path2]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_all_element_types(self):
        md = '''# Heading 1
## Heading 2
### Heading 3

Regular paragraph with **bold** and *italic*.

- List item 1
- List item 2

> A blockquote

```python
def hello():
    print("world")
```
'''
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            result = render_markdown_to_image(md, output_path)
            assert os.path.exists(output_path)

            with Image.open(output_path) as img:
                # Should have reasonable dimensions
                assert img.width > 0
                assert img.height > 200  # Multiple elements = tall image
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_empty_markdown(self):
        md = ''
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            result = render_markdown_to_image(md, output_path)
            assert os.path.exists(output_path)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


class TestCLI:
    """Tests for CLI argument parsing."""

    def test_main_missing_input(self):
        """Test that missing input file causes error."""
        import sys
        from io import StringIO
        from upyscripts.mksctxt import main

        with patch.object(sys, 'argv', ['mksctxt']):
            with pytest.raises(SystemExit):
                main()

    def test_main_nonexistent_file(self):
        """Test that nonexistent file causes error."""
        import sys
        from upyscripts.mksctxt import main

        with patch.object(sys, 'argv', ['mksctxt', 'nonexistent_file_12345.md']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_successful_render(self):
        """Test successful render through CLI."""
        import sys
        from upyscripts.mksctxt import main

        # Create temp input file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Test\n\nHello world.')
            input_path = f.name

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            with patch.object(sys, 'argv', ['mksctxt', input_path, '-o', output_path]):
                main()

            assert os.path.exists(output_path)
            with Image.open(output_path) as img:
                assert img.width > 0
        finally:
            for p in [input_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)

    def test_main_with_options(self):
        """Test CLI with various options."""
        import sys
        from upyscripts.mksctxt import main

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Test')
            input_path = f.name

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            output_path = f.name

        try:
            with patch.object(sys, 'argv', [
                'mksctxt', input_path,
                '-o', output_path,
                '-w', '1000',
                '-s', '1',
                '--no-window'
            ]):
                main()

            assert os.path.exists(output_path)
            with Image.open(output_path) as img:
                assert img.width == 1000
        finally:
            for p in [input_path, output_path]:
                if os.path.exists(p):
                    os.unlink(p)


class TestColors:
    """Tests for color definitions."""

    def test_all_colors_valid_hex(self):
        """All colors should be valid hex codes."""
        for name, color in COLORS.items():
            assert color.startswith('#'), f"{name} doesn't start with #"
            assert len(color) == 7, f"{name} has wrong length"
            # Should convert without error
            rgb = hex_to_rgb(color)
            assert all(0 <= c <= 255 for c in rgb), f"{name} has invalid RGB values"

    def test_required_colors_exist(self):
        """Required colors for rendering should exist."""
        required = ['background', 'foreground', 'titlebar', 'code_bg', 'purple', 'pink', 'comment']
        for color in required:
            assert color in COLORS, f"Missing required color: {color}"
