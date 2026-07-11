"""Focused tests for qslideshow GUI image loading behavior."""

from pathlib import Path
from unittest.mock import Mock, patch

from upyscripts.qslideshow.core import SlideshowContext
from upyscripts.qslideshow.gui import ImageSlideshow


def make_slideshow(paths, *, repeat=False, current_index=0):
    """Build a slideshow instance without initializing tkinter."""
    slideshow = ImageSlideshow.__new__(ImageSlideshow)
    slideshow.context = SlideshowContext(list(paths), repeat=repeat)
    slideshow.context.current_index = current_index
    slideshow.current_photo = None
    slideshow.root = Mock()
    slideshow.resize_and_display = Mock()
    slideshow.update_status = Mock()
    slideshow.quit = Mock()
    return slideshow


def test_failed_image_is_removed_and_next_image_is_displayed():
    bad = Path("missing.png")
    good = Path("good.png")
    image = Mock()
    slideshow = make_slideshow([bad, good])
    slideshow.load_image = Mock(side_effect=[None, image])

    slideshow.display_current_image()

    assert slideshow.context.image_paths == [good]
    assert slideshow.context.current_image is image
    assert slideshow.context.current_index == 0
    assert slideshow.load_image.call_count == 2
    slideshow.root.title.assert_called_once_with("Image Slideshow - good.png (1/1)")
    slideshow.resize_and_display.assert_called_once_with()
    slideshow.update_status.assert_called_once_with()
    slideshow.quit.assert_not_called()


def test_many_failed_images_do_not_recurse():
    paths = [Path(f"missing-{index}.png") for index in range(1500)]
    slideshow = make_slideshow(paths)
    slideshow.load_image = Mock(return_value=None)

    with patch("builtins.print"):
        slideshow.display_current_image()

    assert slideshow.context.image_paths == []
    assert slideshow.load_image.call_count == len(paths)
    slideshow.quit.assert_called_once_with()


def test_failed_final_image_quits_without_repeat():
    good = Path("good.png")
    bad = Path("missing.png")
    slideshow = make_slideshow([good, bad], current_index=1)
    slideshow.load_image = Mock(return_value=None)

    slideshow.display_current_image()

    assert slideshow.context.image_paths == [good]
    assert slideshow.load_image.call_count == 1
    slideshow.quit.assert_called_once_with()
    slideshow.resize_and_display.assert_not_called()


def test_failed_final_image_wraps_with_repeat():
    good = Path("good.png")
    bad = Path("missing.png")
    image = Mock()
    slideshow = make_slideshow([good, bad], repeat=True, current_index=1)
    slideshow.load_image = Mock(side_effect=[None, image])

    slideshow.display_current_image()

    assert slideshow.context.image_paths == [good]
    assert slideshow.context.current_index == 0
    assert slideshow.context.current_image is image
    assert slideshow.load_image.call_count == 2
    slideshow.quit.assert_not_called()


def test_all_invalid_images_quit_once():
    slideshow = make_slideshow([Path("one.png"), Path("two.png")], repeat=True)
    slideshow.load_image = Mock(return_value=None)

    slideshow.display_current_image()

    assert slideshow.context.image_paths == []
    slideshow.quit.assert_called_once_with()
