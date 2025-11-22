"""
Comprehensive tests for qslideshow configuration system.

Tests cover:
- Default configuration loading
- Config file discovery (explicit, cwd, home, system)
- YAML parsing and error handling
- Deep merging of user config with defaults
- Dot-notation get/set operations
- CLI argument mapping (update_from_args)
- Context-specific hotkey/gesture retrieval
- Config file generation
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, patch

from upyscripts.qslideshow.config import ConfigManager


@pytest.fixture
def temp_config_dir():
    """Create temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_user_config():
    """Sample user configuration for testing."""
    return {
        'slideshow': {
            'speed': 5.0,  # Override default 3.0
            'repeat': True,  # Override default False
            'custom_field': 'test'  # New field
        },
        'hotkeys': {
            'common': {
                'toggle_pause': 'p'  # Override default
            },
            'gui': {
                'quit': 'Escape',  # Override
                'custom_action': 'x'  # New hotkey
            }
        }
    }


class TestConfigManagerInitialization:
    """Test configuration manager initialization."""

    def test_basic_initialization(self):
        """Test basic initialization with defaults."""
        config = ConfigManager()

        assert config.config is not None
        assert isinstance(config.config, dict)
        assert 'slideshow' in config.config
        assert 'hotkeys' in config.config

    def test_default_config_has_required_sections(self):
        """Test default config contains all required sections."""
        config = ConfigManager()

        required_sections = ['slideshow', 'images', 'gui', 'web',
                            'external_tools', 'file_operations',
                            'hotkeys', 'gestures']

        for section in required_sections:
            assert section in config.config, f"Missing section: {section}"

    def test_default_slideshow_settings(self):
        """Test default slideshow settings."""
        config = ConfigManager()

        assert config.get('slideshow.speed') == 3.0
        assert config.get('slideshow.repeat') == False
        assert config.get('slideshow.shuffle') == False
        assert config.get('slideshow.fit_mode') == 'shrink'

    def test_default_web_settings(self):
        """Test default web server settings."""
        config = ConfigManager()

        assert config.get('web.port') == 8000
        assert config.get('web.host') == '0.0.0.0'
        assert config.get('web.enable_wake_lock') == True


class TestConfigFileDiscovery:
    """Test configuration file discovery logic."""

    def test_explicit_path_takes_precedence(self, temp_config_dir):
        """Test that explicit config path is used first."""
        config_file = temp_config_dir / "my_config.yaml"
        config_file.write_text("slideshow:\n  speed: 10.0\n")

        config = ConfigManager()
        found = config.find_config_file(str(config_file))

        assert found == config_file

    def test_explicit_path_not_found_raises(self):
        """Test that nonexistent explicit path raises error."""
        config = ConfigManager()

        with pytest.raises(FileNotFoundError):
            config.find_config_file("/nonexistent/config.yaml")

    def test_finds_config_in_cwd(self, temp_config_dir, monkeypatch):
        """Test finding config in current working directory."""
        config_file = temp_config_dir / "qslideshow.yaml"
        config_file.write_text("slideshow:\n  speed: 5.0\n")

        # Mock cwd to return our temp dir
        monkeypatch.setattr(Path, 'cwd', lambda: temp_config_dir)

        config = ConfigManager()
        found = config.find_config_file()

        assert found == config_file

    def test_prefers_yaml_over_yml(self, temp_config_dir, monkeypatch):
        """Test that .yaml is preferred over .yml."""
        yaml_file = temp_config_dir / "qslideshow.yaml"
        yml_file = temp_config_dir / "qslideshow.yml"

        yaml_file.write_text("slideshow:\n  speed: 5.0\n")
        yml_file.write_text("slideshow:\n  speed: 7.0\n")

        monkeypatch.setattr(Path, 'cwd', lambda: temp_config_dir)

        config = ConfigManager()
        found = config.find_config_file()

        # Should find .yaml first (it's listed first in DEFAULT_CONFIG_NAMES)
        assert found == yaml_file

    def test_returns_none_when_no_config_found(self, temp_config_dir, monkeypatch):
        """Test returns None when no config file exists."""
        monkeypatch.setattr(Path, 'cwd', lambda: temp_config_dir)
        monkeypatch.setattr(Path, 'home', lambda: temp_config_dir)

        config = ConfigManager()
        found = config.find_config_file()

        assert found is None


class TestConfigLoading:
    """Test configuration loading from files."""

    def test_load_valid_yaml(self, temp_config_dir):
        """Test loading valid YAML configuration."""
        config_file = temp_config_dir / "qslideshow.yaml"
        config_file.write_text("""
slideshow:
  speed: 5.0
  repeat: true
hotkeys:
  common:
    toggle_pause: p
""")

        config = ConfigManager()
        config.load_config(str(config_file))

        assert config.get('slideshow.speed') == 5.0
        assert config.get('slideshow.repeat') == True
        assert config.get('hotkeys.common.toggle_pause') == 'p'

    def test_load_empty_file_uses_defaults(self, temp_config_dir):
        """Test that empty file falls back to defaults."""
        config_file = temp_config_dir / "qslideshow.yaml"
        config_file.write_text("")

        config = ConfigManager()
        config.load_config(str(config_file))

        # Should have defaults
        assert config.get('slideshow.speed') == 3.0

    def test_load_invalid_yaml_uses_defaults(self, temp_config_dir):
        """Test that invalid YAML falls back to defaults."""
        config_file = temp_config_dir / "qslideshow.yaml"
        config_file.write_text("invalid: yaml: content: [\n")

        config = ConfigManager()
        config.load_config(str(config_file))

        # Should have defaults despite error
        assert config.get('slideshow.speed') == 3.0

    def test_load_missing_explicit_file_raises(self):
        """Test that missing explicit file raises error."""
        config = ConfigManager()

        with pytest.raises(FileNotFoundError):
            config.load_config("/nonexistent/path.yaml")

    def test_load_no_config_file_uses_defaults(self, temp_config_dir, monkeypatch):
        """Test that when no config file exists, defaults are used."""
        # Set cwd to empty temp dir where no config exists
        monkeypatch.setattr(Path, 'cwd', lambda: temp_config_dir)
        monkeypatch.setattr(Path, 'home', lambda: temp_config_dir)

        config = ConfigManager()
        config.load_config()  # No explicit path

        # Should have defaults
        assert config.get('slideshow.speed') == 3.0


class TestDeepMerge:
    """Test deep merge logic."""

    def test_merge_simple_values(self):
        """Test merging simple key-value pairs."""
        config = ConfigManager()

        base = {'a': 1, 'b': 2}
        overlay = {'b': 3, 'c': 4}

        result = config._deep_merge(base, overlay)

        assert result == {'a': 1, 'b': 3, 'c': 4}

    def test_merge_nested_dicts(self):
        """Test merging nested dictionaries."""
        config = ConfigManager()

        base = {
            'slideshow': {
                'speed': 3.0,
                'repeat': False
            }
        }
        overlay = {
            'slideshow': {
                'speed': 5.0  # Override
                # repeat not specified, should keep False
            }
        }

        result = config._deep_merge(base, overlay)

        assert result['slideshow']['speed'] == 5.0
        assert result['slideshow']['repeat'] == False

    def test_merge_preserves_base(self):
        """Test that merge doesn't modify original base dict."""
        config = ConfigManager()

        base = {'a': {'b': 1}}
        overlay = {'a': {'c': 2}}

        result = config._deep_merge(base, overlay)

        # Base should be unchanged
        assert 'c' not in base['a']
        assert 'c' in result['a']

    def test_merge_overlay_completely_replaces_non_dicts(self):
        """Test that non-dict values are completely replaced."""
        config = ConfigManager()

        base = {'key': [1, 2, 3]}
        overlay = {'key': [4, 5]}

        result = config._deep_merge(base, overlay)

        # List should be replaced, not merged
        assert result['key'] == [4, 5]


class TestDotNotationGetSet:
    """Test dot-notation get/set operations."""

    def test_get_simple_key(self):
        """Test getting simple top-level key."""
        config = ConfigManager()
        config.config = {'speed': 5.0}

        assert config.get('speed') == 5.0

    def test_get_nested_key(self):
        """Test getting nested key with dot notation."""
        config = ConfigManager()
        config.config = {
            'slideshow': {
                'speed': 3.0
            }
        }

        assert config.get('slideshow.speed') == 3.0

    def test_get_deeply_nested_key(self):
        """Test getting deeply nested key."""
        config = ConfigManager()
        config.config = {
            'level1': {
                'level2': {
                    'level3': 'value'
                }
            }
        }

        assert config.get('level1.level2.level3') == 'value'

    def test_get_nonexistent_key_returns_default(self):
        """Test that missing key returns default value."""
        config = ConfigManager()
        config.config = {}

        assert config.get('nonexistent', 'default') == 'default'
        assert config.get('slideshow.nonexistent', None) is None

    def test_set_simple_key(self):
        """Test setting simple key."""
        config = ConfigManager()
        config.config = {}

        config.set('speed', 10.0)

        assert config.config['speed'] == 10.0

    def test_set_nested_key(self):
        """Test setting nested key."""
        config = ConfigManager()
        config.config = {}

        config.set('slideshow.speed', 5.0)

        assert config.config['slideshow']['speed'] == 5.0

    def test_set_creates_intermediate_dicts(self):
        """Test that set creates intermediate dictionaries."""
        config = ConfigManager()
        config.config = {}

        config.set('a.b.c.d', 'value')

        assert config.config['a']['b']['c']['d'] == 'value'

    def test_set_overwrites_existing(self):
        """Test that set overwrites existing value."""
        config = ConfigManager()
        config.config = {'slideshow': {'speed': 3.0}}

        config.set('slideshow.speed', 10.0)

        assert config.config['slideshow']['speed'] == 10.0


class TestUpdateFromArgs:
    """Test updating config from CLI arguments."""

    def test_update_slideshow_args(self):
        """Test updating slideshow-related arguments."""
        config = ConfigManager()
        args = Mock()
        args.speed = 10.0
        args.repeat = True
        args.shuffle = True
        args.fit_mode = 'original'
        args.always_on_top = True
        args.paused = True

        config.update_from_args(args)

        assert config.get('slideshow.speed') == 10.0
        assert config.get('slideshow.repeat') == True
        assert config.get('slideshow.shuffle') == True
        assert config.get('slideshow.fit_mode') == 'original'
        assert config.get('slideshow.always_on_top') == True
        assert config.get('slideshow.paused_on_start') == True

    def test_update_web_args(self):
        """Test updating web server arguments."""
        config = ConfigManager()
        args = Mock()
        args.port = 9000
        args.host = '127.0.0.1'
        args.dev_mode = True

        config.update_from_args(args)

        assert config.get('web.port') == 9000
        assert config.get('web.host') == '127.0.0.1'
        assert config.get('web.dev_mode') == True

    def test_update_ignores_none_values(self):
        """Test that None values are not applied."""
        config = ConfigManager()
        original_speed = config.get('slideshow.speed')

        args = Mock()
        args.speed = None

        config.update_from_args(args)

        # Should remain unchanged
        assert config.get('slideshow.speed') == original_speed

    def test_update_ignores_missing_attributes(self):
        """Test that missing attributes are skipped."""
        config = ConfigManager()
        args = Mock()
        # No attributes set

        # Should not raise
        config.update_from_args(args)


class TestContextSpecificRetrieval:
    """Test retrieving context-specific hotkeys and gestures."""

    def test_get_common_hotkeys(self):
        """Test getting common hotkeys."""
        config = ConfigManager()

        hotkeys = config.get_hotkeys('common')

        assert isinstance(hotkeys, dict)
        assert len(hotkeys) > 0

    def test_get_gui_hotkeys_includes_common(self):
        """Test that GUI hotkeys include common hotkeys."""
        config = ConfigManager()

        gui_hotkeys = config.get_hotkeys('gui')

        # Should have both common and GUI-specific hotkeys
        assert 'navigate_next' in gui_hotkeys or 'toggle_pause' in gui_hotkeys
        assert 'quit' in gui_hotkeys or 'open_folder' in gui_hotkeys

    def test_get_web_hotkeys_includes_common(self):
        """Test that web hotkeys include common hotkeys."""
        config = ConfigManager()

        web_hotkeys = config.get_hotkeys('web')

        # Should have both common and web-specific hotkeys
        assert 'navigate_next' in web_hotkeys or 'toggle_pause' in web_hotkeys

    def test_context_specific_overrides_common(self, temp_config_dir):
        """Test that context-specific hotkeys override common."""
        config_file = temp_config_dir / "qslideshow.yaml"
        config_file.write_text("""
hotkeys:
  common:
    toggle_pause: space
  gui:
    toggle_pause: p  # Override
""")

        config = ConfigManager()
        config.load_config(str(config_file))

        gui_hotkeys = config.get_hotkeys('gui')

        # GUI override should win
        assert gui_hotkeys['toggle_pause'] == 'p'

    def test_get_gestures(self):
        """Test getting gesture configuration."""
        config = ConfigManager()

        gestures = config.get_gestures('web')

        assert isinstance(gestures, dict)


class TestConfigFileGeneration:
    """Test configuration file generation."""

    def test_generate_default_config_file(self, temp_config_dir):
        """Test generating default config file."""
        config = ConfigManager()
        output_path = temp_config_dir / "generated.yaml"

        result_path = config.generate_default_config_file(output_path)

        assert result_path.exists()
        assert result_path == output_path

        # Verify it's valid YAML
        with open(result_path) as f:
            generated = yaml.safe_load(f)
            assert generated is not None
            assert 'slideshow' in generated

    def test_save_config(self, temp_config_dir):
        """Test saving current configuration."""
        config = ConfigManager()
        config.set('slideshow.speed', 99.0)

        save_path = temp_config_dir / "saved.yaml"
        config.save_config(save_path)

        assert save_path.exists()

        # Load it back and verify
        with open(save_path) as f:
            saved = yaml.safe_load(f)
            assert saved['slideshow']['speed'] == 99.0
