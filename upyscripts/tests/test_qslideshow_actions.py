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
from upyscripts.qslideshow.repeat_modes import RepeatMode
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
    FilterScriptRunner,
    PostScriptRunner,
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

    def test_shuffle_each_reshuffles_at_every_forward_cycle(self, test_images):
        context = SlideshowContext(test_images.copy(), repeat_mode='shuffle-each')
        context.image_paths = test_images.copy()
        context.current_index = len(test_images) - 1
        action = NavigateNextAction()

        with patch('upyscripts.qslideshow.actions.random.shuffle') as shuffle:
            shuffle.side_effect = lambda order: order.reverse()
            result = action.execute(context)

        assert result['current_index'] == 0
        assert context.image_paths == list(reversed(test_images))
        assert context.repeat_count == 1

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

    def test_toggle_repeat_cycles_authoritative_modes(self, slideshow_context):
        action = ToggleRepeatAction()

        assert slideshow_context.repeat_mode == RepeatMode.NONE
        assert action.execute(slideshow_context)['repeat_mode'] == 'fixed'
        with patch('upyscripts.qslideshow.actions.random.shuffle'):
            assert action.execute(slideshow_context)['repeat_mode'] == 'shuffle'
            assert action.execute(slideshow_context)['repeat_mode'] == 'shuffle-each'
        result = action.execute(slideshow_context)

        assert result == {'repeat': False, 'repeat_mode': 'none'}

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


class TestFilterScriptRunner:
    """Test pre-display filter script runner."""

    def test_filter_allows_image(self, slideshow_context):
        """Test filter script that allows image (exit 0)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "filter.sh"
            script.write_text("#!/bin/bash\nexit 0\n")
            script.chmod(0o755)

            runner = FilterScriptRunner(script)
            assert runner.should_display(slideshow_context) is True

    def test_filter_skips_image(self, slideshow_context):
        """Test filter script that rejects image (exit 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "filter.sh"
            script.write_text("#!/bin/bash\nexit 1\n")
            script.chmod(0o755)

            runner = FilterScriptRunner(script)
            assert runner.should_display(slideshow_context) is False

    def test_filter_missing_script(self, slideshow_context):
        """Test graceful handling when filter script doesn't exist."""
        runner = FilterScriptRunner(Path("/nonexistent/filter.sh"))
        # Should default to showing image
        assert runner.should_display(slideshow_context) is True

    def test_filter_env_variables(self, slideshow_context):
        """Test QSS_* environment variables are passed to filter script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "filter.sh"
            script.write_text("#!/bin/bash\nexit 0\n")
            script.chmod(0o755)

            runner = FilterScriptRunner(script)
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)
                runner.should_display(slideshow_context)

                env_passed = mock_run.call_args[1]['env']
                assert 'QSS_IMG_IDX' in env_passed
                assert 'QSS_FULL_PATH' in env_passed
                assert 'QSS_IMG_NAME' in env_passed


class TestPostScriptRunner:
    """Test post-tool hook script runner."""

    def test_post_hook_receives_tool_info(self, slideshow_context):
        """Test that post script receives tool execution details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "post.sh"
            script.write_text("#!/bin/bash\nexit 0\n")
            script.chmod(0o755)

            runner = PostScriptRunner(script)
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)
                runner.run_post_hook(
                    slideshow_context,
                    tool_id="3", tool_rc=0,
                    tool_stdout="output", tool_stderr="",
                    prev_full_path="/old/path.jpg", prev_img_name="path.jpg",
                    img_removed=False
                )

                env_passed = mock_run.call_args[1]['env']
                assert env_passed['QSS_TOOL_ID'] == '3'
                assert env_passed['QSS_TOOL_RC'] == '0'
                assert env_passed['QSS_TOOL_STDOUT'] == 'output'
                assert env_passed['QSS_TOOL_STDERR'] == ''

    def test_post_hook_receives_prev_state(self, slideshow_context):
        """Test that post script receives pre-tool image state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "post.sh"
            script.write_text("#!/bin/bash\nexit 0\n")
            script.chmod(0o755)

            runner = PostScriptRunner(script)
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)
                runner.run_post_hook(
                    slideshow_context,
                    tool_id="1", tool_rc=0,
                    tool_stdout="", tool_stderr="",
                    prev_full_path="/photos/cat.jpg", prev_img_name="cat.jpg",
                    img_removed=False
                )

                env_passed = mock_run.call_args[1]['env']
                assert env_passed['QSS_PREV_FULL_PATH'] == '/photos/cat.jpg'
                assert env_passed['QSS_PREV_IMG_NAME'] == 'cat.jpg'

    def test_post_hook_img_removed_flag(self, slideshow_context):
        """Test QSS_IMG_REMOVED is set when tool returns 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "post.sh"
            script.write_text("#!/bin/bash\nexit 0\n")
            script.chmod(0o755)

            runner = PostScriptRunner(script)
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                # When image was removed
                runner.run_post_hook(
                    slideshow_context,
                    tool_id="1", tool_rc=1,
                    tool_stdout="", tool_stderr="",
                    prev_full_path="/p.jpg", prev_img_name="p.jpg",
                    img_removed=True
                )
                env_passed = mock_run.call_args[1]['env']
                assert env_passed['QSS_IMG_REMOVED'] == '1'

                # When image was NOT removed
                runner.run_post_hook(
                    slideshow_context,
                    tool_id="1", tool_rc=0,
                    tool_stdout="", tool_stderr="",
                    prev_full_path="/p.jpg", prev_img_name="p.jpg",
                    img_removed=False
                )
                env_passed = mock_run.call_args[1]['env']
                assert env_passed['QSS_IMG_REMOVED'] == ''

    def test_post_hook_error_does_not_crash(self, slideshow_context):
        """Test that post script errors don't propagate."""
        runner = PostScriptRunner(Path("/nonexistent/post.sh"))
        # Should not raise
        runner.run_post_hook(
            slideshow_context,
            tool_id="1", tool_rc=0,
            tool_stdout="", tool_stderr="",
            prev_full_path="/p.jpg", prev_img_name="p.jpg",
            img_removed=False
        )


class TestFilterIntegration:
    """Test filter script integration with navigation actions."""

    def test_navigate_next_skips_filtered(self, slideshow_context):
        """Test that navigation skips images rejected by filter."""
        call_count = [0]

        def mock_should_display(ctx):
            # Reject image at index 1, allow all others
            return ctx.current_index != 1

        runner = FilterScriptRunner(Path("/dummy"))
        runner.should_display = mock_should_display
        slideshow_context.filter_runner = runner
        slideshow_context.current_index = 0

        action = NavigateNextAction()
        result = action.execute(slideshow_context)

        # Should skip index 1 and land on index 2
        assert slideshow_context.current_index == 2

    def test_navigate_previous_skips_filtered(self, slideshow_context):
        """Test that backward navigation skips filtered images."""
        def mock_should_display(ctx):
            return ctx.current_index != 1

        runner = FilterScriptRunner(Path("/dummy"))
        runner.should_display = mock_should_display
        slideshow_context.filter_runner = runner
        slideshow_context.current_index = 2

        action = NavigatePreviousAction()
        result = action.execute(slideshow_context)

        # Should skip index 1 and land on index 0
        assert slideshow_context.current_index == 0

    def test_all_images_filtered_shows_anyway(self, slideshow_context):
        """Test loop protection: if all images filtered, still shows one."""
        def mock_should_display(ctx):
            return False  # reject everything

        runner = FilterScriptRunner(Path("/dummy"))
        runner.should_display = mock_should_display
        slideshow_context.filter_runner = runner
        slideshow_context.current_index = 0

        action = NavigateNextAction()
        result = action.execute(slideshow_context)

        # Should not hang; index should be some valid value
        assert 0 <= slideshow_context.current_index < len(slideshow_context.image_paths)

    def test_no_filter_no_change(self, slideshow_context):
        """Test that navigation works normally without filter_runner."""
        slideshow_context.filter_runner = None
        slideshow_context.current_index = 0

        action = NavigateNextAction()
        result = action.execute(slideshow_context)

        assert slideshow_context.current_index == 1


class TestPostScriptIntegration:
    """Test post script integration with external tool execution."""

    def test_external_tool_triggers_post_hook(self, slideshow_context):
        """Test that running an external tool triggers the post script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create a tool that exits 0
            tool_path = tmpdir / "tool_1.sh"
            tool_path.write_text("#!/bin/bash\necho 'done'\nexit 0\n")
            tool_path.chmod(0o755)

            # Create a mock post runner
            post_runner = Mock()
            slideshow_context.post_runner = post_runner

            action = ExternalToolAction(tool_id="1", tool_path=tool_path)
            action.execute(slideshow_context)

            # Post runner should have been called
            post_runner.run_post_hook.assert_called_once()
            call_kwargs = post_runner.run_post_hook.call_args[1]
            assert call_kwargs['tool_id'] == '1'
            assert call_kwargs['tool_rc'] == 0
            assert call_kwargs['img_removed'] is False

    def test_external_tool_remove_triggers_post_hook(self, slideshow_context):
        """Test post hook called with img_removed=True when tool returns 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create a tool that exits 1 (remove image)
            tool_path = tmpdir / "tool_1.sh"
            tool_path.write_text("#!/bin/bash\nexit 1\n")
            tool_path.chmod(0o755)

            post_runner = Mock()
            slideshow_context.post_runner = post_runner
            slideshow_context.current_index = 2
            prev_name = slideshow_context.image_paths[2].name

            action = ExternalToolAction(tool_id="1", tool_path=tool_path)
            action.execute(slideshow_context)

            post_runner.run_post_hook.assert_called_once()
            call_kwargs = post_runner.run_post_hook.call_args[1]
            assert call_kwargs['tool_rc'] == 1
            assert call_kwargs['img_removed'] is True
            assert call_kwargs['prev_img_name'] == prev_name
