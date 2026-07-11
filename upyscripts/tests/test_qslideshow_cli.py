
from upyscripts.qslideshow.cli import parse_arguments
from upyscripts.qslideshow.config import ConfigManager
from upyscripts.qslideshow.core import collect_images_from_paths


def test_absent_cli_options_do_not_override_config():
    config = ConfigManager()
    config.set('slideshow.speed', 9.0)
    config.set('slideshow.repeat', True)
    config.set('images.recursive', True)
    config.set('web.port', 9123)

    args = parse_arguments(['images'])
    config.update_from_args(args)

    assert config.get('slideshow.speed') == 9.0
    assert config.get('slideshow.repeat') is True
    assert config.get('images.recursive') is True
    assert config.get('web.port') == 9123


def test_explicit_cli_options_override_config():
    config = ConfigManager()
    config.set('slideshow.speed', 9.0)
    config.set('images.recursive', False)
    config.set('web.dev_mode', False)

    args = parse_arguments(['images', '--speed', '2.5', '--recursive', '--web-dev'])
    config.update_from_args(args)

    assert config.get('slideshow.speed') == 2.5
    assert config.get('images.recursive') is True
    assert config.get('web.dev_mode') is True


def test_repeat_mode_is_authoritative_and_repeat_is_legacy_alias():
    explicit = parse_arguments(['images', '--repeat', '--repeat-mode', 'shuffle-each'])
    legacy = parse_arguments(['images', '--repeat'])
    explicit_config = ConfigManager()
    legacy_config = ConfigManager()

    explicit_config.update_from_args(explicit)
    legacy_config.update_from_args(legacy)

    assert explicit_config.get('slideshow.repeat_mode') == 'shuffle-each'
    assert legacy_config.get('slideshow.repeat_mode') == 'fixed'


def test_custom_extensions_apply_to_directory_file_and_response_file(tmp_path):
    nested = tmp_path / 'nested'
    nested.mkdir()
    direct = tmp_path / 'direct.avif'
    nested_image = nested / 'nested.AVIF'
    response_image = tmp_path / 'response.custom'
    direct.write_bytes(b'image')
    nested_image.write_bytes(b'image')
    response_image.write_bytes(b'image')
    response_file = tmp_path / 'images.txt'
    response_file.write_text(f'{response_image}\n', encoding='utf-8')

    discovered = collect_images_from_paths(
        [str(tmp_path), str(direct), f'@{response_file}'],
        recursive=True,
        exclude_patterns=['direct*'],
        additional_extensions=['avif', '.CUSTOM'],
    )

    assert discovered == [nested_image, response_image]


def test_config_exclusion_patterns_support_semicolon_splitting():
    args = parse_arguments(['images', '--exclude', '*.gif;thumbnail_*'])
    config = ConfigManager()
    config.update_from_args(args)

    assert config.get('images.exclude_patterns') == ['*.gif;thumbnail_*']
