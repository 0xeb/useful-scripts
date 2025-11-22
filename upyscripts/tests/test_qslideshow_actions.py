"""
Comprehensive tests for qslideshow action system.

Tests cover:
- Navigation actions (next, previous, boundaries)
- Control actions (pause, fullscreen, repeat, shuffle, always on top)
- Speed actions (increase, decrease, limits)
- File manager actions (open folder, reveal file)
- Memory actions (remember, note)
- External tool discovery and execution
- Action registry and lookup
- Error handling and edge cases
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, call
from PIL import Image

from upyscripts.qslideshow.core import SlideshowContext
from upyscripts.qslideshow.actions import (
    action_registry,
    NavigateNextAction,
    NavigatePreviousAction,
    TogglePauseAction,
    ToggleFullscreenAction,
    ToggleRepeatAction,
    ToggleShuffleAction,
    ToggleAlwaysOnTopAction,
    IncreaseSpeedAction,
    DecreaseSpeedAction,
    OpenFolderAction,
    RevealFileAction,
    RememberAction,
    NoteAction,
    ExternalToolAction,
    ExternalToolManager,
    QuitAction,
)


@pytest.fixture
def test_images():
    """Create temporary test images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        images = []
        for i in range(5):
            img_path = tmpdir / f"test{i}.png"
            img = Image.new('RGB', (100, 100), color=(i*50, 0, 0))
            img.save(img_path)
            images.append(img_path)
        yield images


@pytest.fixture
def slideshow_context(test_images):
    """Create a basic slideshow context."""
    return SlideshowContext(
        image_paths=test_images,
        speed=3.0,
        repeat=False,
        shuffle=False,
        paused=False
    )


@pytest.fixture
def web_slideshow_context(test_images):
    """Create a web mode slideshow context with image_order."""
    ctx = SlideshowContext(
        image_paths=test_images,
        speed=3.0,
        repeat=False,
        shuffle=False,
        paused=False
    )
    # Add web mode image_order attribute
    ctx.image_order = list(range(len(test_images)))
    return ctx


class TestNavigationActions:
    """Test navigation action behavior."""

    def test_navigate_next_basic(self, slideshow_context):
        """Test basic next navigation."""
        action = NavigateNextAction()
        assert slideshow_context.current_index == 0

        result = action.execute(slideshow_context)
        assert result["current_index"] == 1
        assert slideshow_context.current_index == 1

    def test_navigate_next_at_end_no_repeat(self, slideshow_context):
        """Test next at end without repeat stays at last image."""
        action = NavigateNextAction()
        slideshow_context.current_index = 4  # Last image

        result = action.execute(slideshow_context)
        assert result["current_index"] == 4
        assert slideshow_context.current_index == 4

    def test_navigate_next_at_end_with_repeat(self, slideshow_context):
        """Test next at end with repeat wraps to first."""
        action = NavigateNextAction()
        slideshow_context.repeat = True
        slideshow_context.current_index = 4

        result = action.execute(slideshow_context)
        assert result["current_index"] == 0
        assert slideshow_context.current_index == 0
        assert slideshow_context.repeat_count == 1

    def test_navigate_previous_basic(self, slideshow_context):
        """Test basic previous navigation."""
        action = NavigatePreviousAction()
        slideshow_context.current_index = 2

        result = action.execute(slideshow_context)
        assert result["current_index"] == 1
        assert slideshow_context.current_index == 1

    def test_navigate_previous_at_start_no_repeat(self, slideshow_context):
        """Test previous at start without repeat stays at first."""
        action = NavigatePreviousAction()
        slideshow_context.current_index = 0

        result = action.execute(slideshow_context)
        assert result["current_index"] == 0
        assert slideshow_context.current_index == 0

    def test_navigate_previous_at_start_with_repeat(self, slideshow_context):
        """Test previous at start with repeat wraps to last."""
        action = NavigatePreviousAction()
        slideshow_context.repeat = True
        slideshow_context.current_index = 0

        result = action.execute(slideshow_context)
        assert result["current_index"] == 4
        assert slideshow_context.current_index == 4

    def test_navigate_next_web_mode(self, web_slideshow_context):
        """Test navigation in web mode uses image_order length."""
        action = NavigateNextAction()
        web_slideshow_context.current_index = 0

        result = action.execute(web_slideshow_context)
        assert result["current_index"] == 1

        # Test at boundary
        web_slideshow_context.current_index = 4
        result = action.execute(web_slideshow_context)
        assert result["current_index"] == 4  # Stays at end

    def test_navigate_previous_web_mode(self, web_slideshow_context):
        """Test previous in web mode uses image_order length."""
        action = NavigatePreviousAction()
        web_slideshow_context.current_index = 2

        result = action.execute(web_slideshow_context)
        assert result["current_index"] == 1


class TestControlActions:
    """Test control action behavior."""

    def test_toggle_pause(self, slideshow_context):
        """Test pause toggle."""
        action = TogglePauseAction()
        assert slideshow_context.is_paused == False

        result = action.execute(slideshow_context)
        assert result["is_paused"] == True
        assert slideshow_context.is_paused == True

        result = action.execute(slideshow_context)
        assert result["is_paused"] == False
        assert slideshow_context.is_paused == False

    def test_toggle_repeat(self, slideshow_context):
        """Test repeat toggle."""
        action = ToggleRepeatAction()
        assert slideshow_context.repeat == False

        result = action.execute(slideshow_context)
        assert result["repeat"] == True
        assert slideshow_context.repeat == True

    def test_toggle_shuffle_gui_mode(self, slideshow_context):
        """Test shuffle in GUI mode manipulates image_paths."""
        action = ToggleShuffleAction()
        original_paths = slideshow_context.image_paths.copy()

        result = action.execute(slideshow_context)
        assert result["shuffle"] == True
        assert slideshow_context.shuffle == True
        # Paths might be shuffled (not guaranteed to be different with small list)
        assert set(slideshow_context.image_paths) == set(original_paths)

        # Toggle off restores original order
        result = action.execute(slideshow_context)
        assert result["shuffle"] == False
        assert slideshow_context.image_paths == original_paths

    def test_toggle_shuffle_web_mode(self, web_slideshow_context):
        """Test shuffle in web mode manipulates image_order."""
        action = ToggleShuffleAction()
        original_order = web_slideshow_context.image_order.copy()
        web_slideshow_context.current_index = 2

        # Get current image
        current_image_idx = web_slideshow_context.image_order[2]

        result = action.execute(web_slideshow_context)
        assert result["shuffle"] == True
        assert web_slideshow_context.shuffle == True
        # Current index should update to where the image moved
        assert "current_index" in result

        # Toggle off restores sequential order
        result = action.execute(web_slideshow_context)
        assert result["shuffle"] == False
        assert web_slideshow_context.image_order == list(range(5))

    def test_toggle_fullscreen(self, slideshow_context):
        """Test fullscreen toggle."""
        action = ToggleFullscreenAction()

        result = action.execute(slideshow_context, is_fullscreen=False)
        assert result["is_fullscreen"] == True
        assert result["action"] == "toggle_fullscreen"

        result = action.execute(slideshow_context, is_fullscreen=True)
        assert result["is_fullscreen"] == False

    def test_toggle_always_on_top(self, slideshow_context):
        """Test always on top toggle."""
        action = ToggleAlwaysOnTopAction()
        assert slideshow_context.always_on_top == False

        result = action.execute(slideshow_context)
        assert result["always_on_top"] == True
        assert slideshow_context.always_on_top == True

    def test_quit_action(self, slideshow_context):
        """Test quit action."""
        action = QuitAction()
        result = action.execute(slideshow_context)
        assert result["action"] == "quit"


class TestSpeedActions:
    """Test speed control actions."""

    def test_increase_speed(self, slideshow_context):
        """Test speed increase (slower playback)."""
        action = IncreaseSpeedAction()
        slideshow_context.speed_seconds = 3.0

        result = action.execute(slideshow_context)
        assert result["speed"] == 4.0
        assert slideshow_context.speed_seconds == 4.0

    def test_increase_speed_max_limit(self, slideshow_context):
        """Test speed increase stops at max (60s)."""
        action = IncreaseSpeedAction()
        slideshow_context.speed_seconds = 60.0

        result = action.execute(slideshow_context)
        assert result["speed"] == 60.0
        assert slideshow_context.speed_seconds == 60.0

    def test_decrease_speed(self, slideshow_context):
        """Test speed decrease (faster playback)."""
        action = DecreaseSpeedAction()
        slideshow_context.speed_seconds = 3.0

        result = action.execute(slideshow_context)
        assert result["speed"] == 2.0
        assert slideshow_context.speed_seconds == 2.0

    def test_decrease_speed_min_limit(self, slideshow_context):
        """Test speed decrease stops at min (0.5s)."""
        action = DecreaseSpeedAction()
        slideshow_context.speed_seconds = 0.5

        result = action.execute(slideshow_context)
        assert result["speed"] == 0.5
        assert slideshow_context.speed_seconds == 0.5


class TestFileManagerActions:
    """Test file manager actions."""

    @patch('subprocess.run')
    @patch('platform.system')
    def test_open_folder_macos(self, mock_system, mock_run, slideshow_context):
        """Test open folder on macOS."""
        mock_system.return_value = "Darwin"
        action = OpenFolderAction()

        result = action.execute(slideshow_context)
        assert "opened" in result
        assert "platform" in result
        assert result["platform"] == "Darwin"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "open"

    @patch('subprocess.run')
    @patch('platform.system')
    def test_open_folder_windows(self, mock_system, mock_run, slideshow_context):
        """Test open folder on Windows."""
        mock_system.return_value = "Windows"
        action = OpenFolderAction()

        result = action.execute(slideshow_context)
        assert "opened" in result
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "explorer"

    @patch('subprocess.run')
    @patch('platform.system')
    def test_reveal_file_macos(self, mock_system, mock_run, slideshow_context):
        """Test reveal file on macOS."""
        mock_system.return_value = "Darwin"
        action = RevealFileAction()

        result = action.execute(slideshow_context)
        assert "revealed" in result
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "open"
        assert "-R" in args

    def test_open_folder_empty_images(self):
        """Test open folder with no images."""
        ctx = SlideshowContext([], speed=3.0)
        action = OpenFolderAction()

        result = action.execute(ctx)
        assert "error" in result


class TestMemoryActions:
    """Test memory action behavior."""

    def test_remember_action(self, slideshow_context):
        """Test remember action creates file with correct format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            remember_file = Path(tmpdir) / "remember.txt"
            action = RememberAction(remember_file=remember_file)

            result = action.execute(slideshow_context)
            assert result["remembered"] == str(slideshow_context.image_paths[0])
            assert result["file"] == str(remember_file)
            assert remember_file.exists()

            # Check file contents
            content = remember_file.read_text()
            assert str(slideshow_context.image_paths[0]) in content
            assert "Index: 1/5" in content

    def test_remember_action_multiple_calls(self, slideshow_context):
        """Test remember action appends to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            remember_file = Path(tmpdir) / "remember.txt"
            action = RememberAction(remember_file=remember_file)

            action.execute(slideshow_context)
            slideshow_context.current_index = 1
            action.execute(slideshow_context)

            content = remember_file.read_text()
            # Should have both images
            assert str(slideshow_context.image_paths[0]) in content
            assert str(slideshow_context.image_paths[1]) in content

    def test_note_action(self, slideshow_context):
        """Test note action with custom text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_file = Path(tmpdir) / "notes.txt"
            action = NoteAction(notes_file=notes_file)

            result = action.execute(slideshow_context, note_text="Great photo!")
            assert result["noted"] == str(slideshow_context.image_paths[0])
            assert result["note"] == "Great photo!"
            assert notes_file.exists()

            content = notes_file.read_text()
            assert "Great photo!" in content
            assert str(slideshow_context.image_paths[0]) in content

    def test_note_action_empty_note(self, slideshow_context):
        """Test note action with empty note."""
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_file = Path(tmpdir) / "notes.txt"
            action = NoteAction(notes_file=notes_file)

            result = action.execute(slideshow_context, note_text="")
            assert notes_file.exists()


class TestExternalToolManager:
    """Test external tool discovery and registration."""

    def test_discover_numeric_tools(self):
        """Test discovering numeric tools (0-99)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create some tool scripts
            (tmpdir / "tool0.sh").touch()
            (tmpdir / "tool1.py").touch()
            (tmpdir / "tool_10.sh").touch()
            (tmpdir / "tool99.bat").touch()

            manager = ExternalToolManager(base_name="tool", search_dir=tmpdir)
            tools = manager.list_tools()

            assert len(tools) == 4
            tool_ids = [t[0] for t in tools]
            assert "0" in tool_ids
            assert "1" in tool_ids
            assert "10" in tool_ids
            assert "99" in tool_ids

    def test_discover_alphabetic_tools(self):
        """Test discovering alphabetic tools (a-z)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "tool_a.sh").touch()
            (tmpdir / "tool_z.py").touch()
            (tmpdir / "toolb.sh").touch()  # No underscore

            manager = ExternalToolManager(base_name="tool", search_dir=tmpdir)
            tools = manager.list_tools()

            assert len(tools) == 3
            tool_ids = [t[0] for t in tools]
            assert "a" in tool_ids
            assert "z" in tool_ids
            assert "b" in tool_ids

    def test_tool_discovery_sorts_correctly(self):
        """Test tools are sorted numerically then alphabetically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "tool_1.sh").touch()
            (tmpdir / "tool_10.sh").touch()
            (tmpdir / "tool_2.sh").touch()
            (tmpdir / "tool_a.sh").touch()
            (tmpdir / "tool_z.sh").touch()

            manager = ExternalToolManager(base_name="tool", search_dir=tmpdir)
            tools = manager.list_tools()

            tool_ids = [t[0] for t in tools]
            # Numeric first (sorted numerically), then alphabetic
            assert tool_ids == ["1", "2", "10", "a", "z"]

    def test_tool_script_extensions(self):
        """Test various script extensions are recognized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            extensions = ['.sh', '.py', '.bat', '.cmd', '.exe', '.ps1', '.rb', '.pl']
            for i, ext in enumerate(extensions):
                (tmpdir / f"tool_{i}{ext}").touch()

            manager = ExternalToolManager(base_name="tool", search_dir=tmpdir)
            assert len(manager.tools) == len(extensions)

    def test_non_script_files_ignored(self):
        """Test non-script files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "tool_1.sh").touch()
            (tmpdir / "tool_2.txt").touch()  # Not a script
            (tmpdir / "tool_3.jpg").touch()  # Not a script
            (tmpdir / "readme.md").touch()   # Doesn't match pattern

            manager = ExternalToolManager(base_name="tool", search_dir=tmpdir)
            assert len(manager.tools) == 1

    def test_get_tool_by_id(self):
        """Test retrieving tool by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            tool_path = tmpdir / "tool_5.sh"
            tool_path.touch()

            manager = ExternalToolManager(base_name="tool", search_dir=tmpdir)
            retrieved = manager.get_tool("5")

            assert retrieved == tool_path
            assert manager.get_tool("999") is None


class TestExternalToolAction:
    """Test external tool action execution."""

    def test_external_tool_execution_success(self, slideshow_context):
        """Test successful external tool execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create a simple script that exits with 0
            tool_path = tmpdir / "tool_1.sh"
            tool_path.write_text("#!/bin/bash\necho 'Success'\nexit 0\n")
            tool_path.chmod(0o755)

            action = ExternalToolAction(tool_id="1", tool_path=tool_path)
            result = action.execute(slideshow_context)

            assert result["success"] == True
            assert result["tool"] == "1"

    def test_external_tool_execution_remove_image(self, slideshow_context):
        """Test tool returning 1 removes current image."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create script that returns 1 (remove image)
            tool_path = tmpdir / "tool_1.sh"
            tool_path.write_text("#!/bin/bash\nexit 1\n")
            tool_path.chmod(0o755)

            initial_count = len(slideshow_context.image_paths)
            slideshow_context.current_index = 2
            current_image = slideshow_context.image_paths[2]

            action = ExternalToolAction(tool_id="1", tool_path=tool_path)
            result = action.execute(slideshow_context)

            assert result["action"] == "removed"
            assert len(slideshow_context.image_paths) == initial_count - 1
            assert current_image not in slideshow_context.image_paths

    def test_external_tool_missing(self, slideshow_context):
        """Test error when tool doesn't exist."""
        action = ExternalToolAction(tool_id="999", tool_path=Path("/nonexistent/tool"))
        result = action.execute(slideshow_context)

        assert "error" in result
        assert "not found" in result["error"]

    @patch.dict(os.environ, {}, clear=True)
    def test_external_tool_environment_variables(self, slideshow_context):
        """Test QSS_* environment variables are passed to tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create script that prints environment
            tool_path = tmpdir / "tool_1.sh"
            if os.name == 'nt':
                tool_path.write_text("@echo off\necho %QSS_IMG_IDX%\nexit 0\n")
            else:
                tool_path.write_text("#!/bin/bash\necho $QSS_IMG_IDX\nexit 0\n")
            tool_path.chmod(0o755)

            action = ExternalToolAction(tool_id="1", tool_path=tool_path)
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                action.execute(slideshow_context)

                # Check that environment was passed
                env_passed = mock_run.call_args[1]['env']
                assert 'QSS_IMG_IDX' in env_passed
                assert env_passed['QSS_IMG_IDX'] == '1'  # Current index + 1


class TestActionRegistry:
    """Test action registry functionality."""

    def test_default_actions_registered(self):
        """Test that default actions are registered."""
        # Navigation
        assert action_registry.get("navigate_next") is not None
        assert action_registry.get("navigate_previous") is not None

        # Controls
        assert action_registry.get("toggle_pause") is not None
        assert action_registry.get("toggle_fullscreen") is not None
        assert action_registry.get("toggle_repeat") is not None
        assert action_registry.get("toggle_shuffle") is not None
        assert action_registry.get("toggle_always_on_top") is not None

        # Speed
        assert action_registry.get("increase_speed") is not None
        assert action_registry.get("decrease_speed") is not None

        # File manager
        assert action_registry.get("open_folder") is not None
        assert action_registry.get("reveal_file") is not None

        # Memory
        assert action_registry.get("remember") is not None
        assert action_registry.get("note") is not None

        # Quit
        assert action_registry.get("quit") is not None

    def test_list_actions_by_context(self):
        """Test filtering actions by context."""
        both_actions = action_registry.list_actions("both")
        gui_actions = action_registry.list_actions("gui")
        web_actions = action_registry.list_actions("web")

        # All actions should work in at least one context
        assert len(both_actions) > 0
        assert len(gui_actions) > 0
        assert len(web_actions) > 0

    def test_action_not_found(self):
        """Test getting non-existent action."""
        action = action_registry.get("nonexistent_action")
        assert action is None
