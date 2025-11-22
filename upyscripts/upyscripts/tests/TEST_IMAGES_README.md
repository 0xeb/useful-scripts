# Test Images for QSlideshow

This directory contains test utilities for qslideshow gallery mode testing.

## Generating Test Images

Run the test image generator script from the repository root:

```bash
# Generate 30 test images in the default location (upyscripts/tests/test_images/)
python upyscripts/tests/generate_test_images.py

# Or specify a custom output directory
python upyscripts/tests/generate_test_images.py /path/to/output

# Or specify both directory and count
python upyscripts/tests/generate_test_images.py /path/to/output 50
```

## Test Images Patterns

The generated images include various patterns for testing:

1. **Solid Colors** (images 1-10): Bright solid colors with large numbers
2. **Gradients** (images 11-15): Color gradients from one color to another
3. **Checkerboards** (images 16-20): Checkerboard patterns with varying grid sizes
4. **Stripes** (images 21-25): Horizontal and vertical stripes
5. **Circles** (images 26-30): Circular patterns with varying counts

Each image:
- Is 800x800 pixels (good for both thumbnails and full-screen viewing)
- Has a large number label in the center for easy identification
- Uses distinct patterns and colors for visual differentiation

## Testing Gallery Mode

Once images are generated, test the gallery mode with:

```bash
# Basic gallery mode with auto-responsive grid
upy.qslideshow test_images/ --web --web-gallery

# Fixed grid size (4 rows x 5 columns)
upy.qslideshow test_images/ --web --web-gallery 4x5

# Custom thumbnail size
upy.qslideshow test_images/ --web --web-gallery --web-gallery-thumbnail-size 150x150

# Custom grid and thumbnail size
upy.qslideshow test_images/ --web --web-gallery-grid 3x4 --web-gallery-thumbnail-size 200x200
```

## Testing Scenarios

### 1. Grid Sizes
- `1x1` - One image per page (pagination testing)
- `4x5` - Standard grid (20 images per page, needs 2 pages for 30 images)
- `5x6` - Large grid (30 images per page, all fit on one page)
- `auto` - Responsive grid (adapts to screen size)

### 2. Thumbnail Sizes
- `50x50` - Very small thumbnails
- `150x150` - Medium thumbnails (fast loading)
- `200x200` - Default size (good balance)
- `400x400` - Large thumbnails (high quality)

### 3. Full-Screen Viewer
- Click any thumbnail to open full-screen viewer
- Test navigation:
  - Arrow keys: Previous/Next
  - Navigation buttons: Click left/right arrows
  - Swipe gestures: Swipe left/right on touch devices
  - Double-tap: Close viewer
  - Escape/Q key: Close viewer

### 4. Mode Switching
- Press 'G' key to toggle between gallery and slideshow modes
- Verify auto-advance stops in gallery mode
- Verify auto-advance resumes when returning to slideshow mode

### 5. Pagination
- Test "First", "Previous", "Next", "Last" buttons
- Test clicking page numbers directly
- Test keyboard shortcuts (PageUp/PageDown)

### 6. Performance
- Test with 100+ images (generate more: `python generate_test_images.py output/ 100`)
- Monitor thumbnail loading time
- Verify LRU cache effectiveness (check memory usage)

## Image Generation Options

The generate_test_images.py script supports:
- Custom output directory
- Custom image count
- Custom image size (modify in code: `size=(800, 800)`)
- Different pattern types (modify patterns in code)

## Cleanup

To remove test images:

```bash
rm -rf test_images/
```
