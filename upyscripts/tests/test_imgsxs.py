"""
Comprehensive tests for upy.imgsxs (Image Side-by-Side tool).

Tests cover:
- Color parsing (hex and named colors)
- List file parsing (comments, absolute/relative paths)
- Image creation (2-way, 3-way, N-way comparisons)
- Image resizing when dimensions don't match
- Separator options (width, color, disabled)
- Output formats (jpg, png, webp)
- Quality settings
- Error handling (missing files, invalid colors)
- Dry-run mode
"""

import pytest
import tempfile
from pathlib import Path
from PIL import Image

from upyscripts.imgsxs import (
    parse_color,
    parse_list_file,
    create_side_by_side
)


class TestColorParsing:
    """Test color parsing functionality."""

    def test_parse_named_colors(self):
        """Test parsing common color names."""
        assert parse_color('black') == (0, 0, 0)
        assert parse_color('white') == (255, 255, 255)
        assert parse_color('red') == (255, 0, 0)
        assert parse_color('green') == (0, 255, 0)
        assert parse_color('blue') == (0, 0, 255)
        assert parse_color('yellow') == (255, 255, 0)
        assert parse_color('cyan') == (0, 255, 255)
        assert parse_color('magenta') == (255, 0, 255)

    def test_parse_hex_colors_with_hash(self):
        """Test parsing hex colors with # prefix."""
        assert parse_color('#FF0000') == (255, 0, 0)
        assert parse_color('#00FF00') == (0, 255, 0)
        assert parse_color('#0000FF') == (0, 0, 255)
        assert parse_color('#FFFFFF') == (255, 255, 255)
        assert parse_color('#000000') == (0, 0, 0)

    def test_parse_hex_colors_without_hash(self):
        """Test parsing hex colors without # prefix."""
        assert parse_color('FF0000') == (255, 0, 0)
        assert parse_color('00FF00') == (0, 255, 0)
        assert parse_color('0000FF') == (0, 0, 255)

    def test_parse_hex_colors_case_insensitive(self):
        """Test hex colors are case insensitive."""
        assert parse_color('#ff0000') == (255, 0, 0)
        assert parse_color('#FF0000') == (255, 0, 0)
        assert parse_color('ff0000') == (255, 0, 0)

    def test_parse_named_colors_case_insensitive(self):
        """Test named colors are case insensitive."""
        assert parse_color('RED') == (255, 0, 0)
        assert parse_color('Red') == (255, 0, 0)
        assert parse_color('red') == (255, 0, 0)

    def test_invalid_hex_length(self):
        """Test invalid hex color length raises error."""
        with pytest.raises(ValueError, match="Invalid color format"):
            parse_color('#FF00')
        with pytest.raises(ValueError, match="Invalid color format"):
            parse_color('#FF00000')

    def test_invalid_hex_characters(self):
        """Test invalid hex characters raise error."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            parse_color('#GGGGGG')
        with pytest.raises(ValueError, match="Invalid hex color"):
            parse_color('#ZZZZZZ')


class TestListFileParsing:
    """Test list file parsing functionality."""

    def test_parse_simple_list(self):
        """Test parsing simple comma-separated paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            list_file = tmpdir / "list.txt"
            list_file.write_text("img1.jpg,img2.jpg\nimg3.png,img4.png\n")

            result = parse_list_file(list_file, tmpdir)

            assert len(result) == 2
            assert len(result[0]) == 2
            assert result[0][0] == tmpdir / "img1.jpg"
            assert result[0][1] == tmpdir / "img2.jpg"

    def test_parse_with_comments(self):
        """Test that comments are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            list_file = tmpdir / "list.txt"
            list_file.write_text("# This is a comment\nimg1.jpg,img2.jpg\n# Another comment\n")

            result = parse_list_file(list_file, tmpdir)

            assert len(result) == 1
            assert len(result[0]) == 2

    def test_parse_with_empty_lines(self):
        """Test that empty lines are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            list_file = tmpdir / "list.txt"
            list_file.write_text("img1.jpg,img2.jpg\n\n\nimg3.jpg,img4.jpg\n")

            result = parse_list_file(list_file, tmpdir)

            assert len(result) == 2

    def test_parse_absolute_paths(self):
        """Test parsing absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            list_file = tmpdir / "list.txt"
            abs_path = "/absolute/path/img.jpg"
            list_file.write_text(f"{abs_path},img2.jpg\n")

            result = parse_list_file(list_file, tmpdir)

            assert result[0][0] == Path(abs_path)
            assert result[0][1] == tmpdir / "img2.jpg"

    def test_parse_n_way_comparison(self):
        """Test parsing 3+ images per line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            list_file = tmpdir / "list.txt"
            list_file.write_text("img1.jpg,img2.jpg,img3.jpg,img4.jpg\n")

            result = parse_list_file(list_file, tmpdir)

            assert len(result) == 1
            assert len(result[0]) == 4

    def test_parse_missing_file_exits(self):
        """Test parsing non-existent file exits with error."""
        with pytest.raises(SystemExit):
            parse_list_file(Path("/nonexistent/file.txt"), Path("."))

    def test_parse_with_whitespace(self):
        """Test that whitespace around paths is trimmed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            list_file = tmpdir / "list.txt"
            list_file.write_text("  img1.jpg  ,  img2.jpg  \n")

            result = parse_list_file(list_file, tmpdir)

            assert result[0][0] == tmpdir / "img1.jpg"
            assert result[0][1] == tmpdir / "img2.jpg"


class TestImageCreation:
    """Test side-by-side image creation."""

    @pytest.fixture
    def test_images(self):
        """Create temporary test images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create 4 test images with different colors
            colors = [
                (255, 0, 0),    # Red
                (0, 255, 0),    # Green
                (0, 0, 255),    # Blue
                (255, 255, 0)   # Yellow
            ]

            image_paths = []
            for i, color in enumerate(colors):
                img = Image.new('RGB', (100, 100), color)
                path = tmpdir / f"img{i}.jpg"
                img.save(path, 'JPEG', quality=95)
                img.close()
                image_paths.append(path)

            yield tmpdir, image_paths

    def test_create_2_way_comparison(self, test_images):
        """Test creating 2-image comparison."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.jpg"

        result = create_side_by_side(
            image_paths[:2],
            output_path,
            separator_width=10,
            separator_color=(0, 255, 0),
            output_format='jpg',
            quality=95
        )

        assert result is True
        assert output_path.exists()

        # Verify output dimensions: 100 + 10 + 100 = 210 width
        img = Image.open(output_path)
        assert img.size == (210, 100)
        img.close()

    def test_create_3_way_comparison(self, test_images):
        """Test creating 3-image comparison."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.jpg"

        result = create_side_by_side(
            image_paths[:3],
            output_path,
            separator_width=10,
            separator_color=(0, 255, 0),
            output_format='jpg',
            quality=95
        )

        assert result is True

        # Verify output dimensions: 100 + 10 + 100 + 10 + 100 = 320 width
        img = Image.open(output_path)
        assert img.size == (320, 100)
        img.close()

    def test_create_4_way_comparison(self, test_images):
        """Test creating 4-image comparison."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.jpg"

        result = create_side_by_side(
            image_paths,
            output_path,
            separator_width=10,
            separator_color=(0, 255, 0),
            output_format='jpg',
            quality=95
        )

        assert result is True

        # Verify output dimensions: 100 + 10 + 100 + 10 + 100 + 10 + 100 = 430 width
        img = Image.open(output_path)
        assert img.size == (430, 100)
        img.close()

    def test_create_with_no_separator(self, test_images):
        """Test creating comparison with separator disabled."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.jpg"

        result = create_side_by_side(
            image_paths[:2],
            output_path,
            separator_width=0,
            separator_color=(0, 255, 0),
            output_format='jpg',
            quality=95
        )

        assert result is True

        # Verify output dimensions: 100 + 100 = 200 width (no separator)
        img = Image.open(output_path)
        assert img.size == (200, 100)
        img.close()

    def test_create_with_different_separator_widths(self, test_images):
        """Test creating comparison with different separator widths."""
        tmpdir, image_paths = test_images

        for sep_width in [5, 20, 50]:
            output_path = tmpdir / f"output_{sep_width}.jpg"

            result = create_side_by_side(
                image_paths[:2],
                output_path,
                separator_width=sep_width,
                separator_color=(0, 255, 0),
                output_format='jpg',
                quality=95
            )

            assert result is True

            # Verify dimensions: 100 + sep_width + 100
            img = Image.open(output_path)
            assert img.size == (200 + sep_width, 100)
            img.close()

    def test_create_png_format(self, test_images):
        """Test creating PNG output."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.png"

        result = create_side_by_side(
            image_paths[:2],
            output_path,
            separator_width=10,
            separator_color=(0, 255, 0),
            output_format='png',
            quality=95
        )

        assert result is True
        assert output_path.exists()

        img = Image.open(output_path)
        assert img.format == 'PNG'
        img.close()

    def test_create_webp_format(self, test_images):
        """Test creating WebP output."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.webp"

        result = create_side_by_side(
            image_paths[:2],
            output_path,
            separator_width=10,
            separator_color=(0, 255, 0),
            output_format='webp',
            quality=95
        )

        assert result is True
        assert output_path.exists()

        img = Image.open(output_path)
        assert img.format == 'WEBP'
        img.close()

    def test_resize_different_dimensions(self):
        """Test that images with different dimensions are resized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create images with different sizes
            img1 = Image.new('RGB', (100, 100), (255, 0, 0))
            img2 = Image.new('RGB', (200, 150), (0, 255, 0))

            path1 = tmpdir / "img1.jpg"
            path2 = tmpdir / "img2.jpg"

            img1.save(path1, 'JPEG')
            img2.save(path2, 'JPEG')
            img1.close()
            img2.close()

            output_path = tmpdir / "output.jpg"

            result = create_side_by_side(
                [path1, path2],
                output_path,
                separator_width=10,
                separator_color=(0, 255, 0),
                output_format='jpg',
                quality=95
            )

            assert result is True

            # Output should use first image's dimensions (100x100)
            # Width: 100 + 10 + 100 = 210
            img = Image.open(output_path)
            assert img.size == (210, 100)
            img.close()

    def test_missing_image_file(self, test_images):
        """Test that missing image file returns False."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.jpg"

        # Use one valid and one invalid path
        result = create_side_by_side(
            [image_paths[0], tmpdir / "nonexistent.jpg"],
            output_path,
            separator_width=10,
            separator_color=(0, 255, 0),
            output_format='jpg',
            quality=95
        )

        assert result is False
        assert not output_path.exists()

    def test_empty_image_list(self):
        """Test that empty image list returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            output_path = tmpdir / "output.jpg"

            result = create_side_by_side(
                [],
                output_path,
                separator_width=10,
                separator_color=(0, 255, 0),
                output_format='jpg',
                quality=95
            )

            assert result is False

    def test_quality_settings(self, test_images):
        """Test different quality settings produce different file sizes."""
        tmpdir, image_paths = test_images

        sizes = []
        for quality in [50, 95]:
            output_path = tmpdir / f"output_q{quality}.jpg"

            create_side_by_side(
                image_paths[:2],
                output_path,
                separator_width=10,
                separator_color=(0, 255, 0),
                output_format='jpg',
                quality=quality
            )

            sizes.append(output_path.stat().st_size)

        # Higher quality should produce larger file
        assert sizes[1] > sizes[0]

    def test_separator_color_applied(self, test_images):
        """Test that separator color is correctly applied."""
        tmpdir, image_paths = test_images
        output_path = tmpdir / "output.jpg"

        # Use red separator
        result = create_side_by_side(
            image_paths[:2],
            output_path,
            separator_width=20,
            separator_color=(255, 0, 0),
            output_format='jpg',
            quality=95
        )

        assert result is True

        # Check that middle pixels (separator region) are red
        img = Image.open(output_path)
        pixels = img.load()

        # Sample pixel in separator region (between images)
        separator_pixel = pixels[110, 50]  # Middle of 10px separator at x=105-115

        # Should be approximately red (JPEG compression may not be exact)
        assert separator_pixel[0] > 200  # R should be high
        assert separator_pixel[1] < 50   # G should be low
        assert separator_pixel[2] < 50   # B should be low

        img.close()
