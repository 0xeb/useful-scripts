import json
from datetime import datetime, timedelta
from pathlib import Path

from upyscripts.qslideshow.trash import TrashManager


def timestamp(days_ago):
    return (datetime.now() - timedelta(days=days_ago)).strftime('%Y%m%d_%H%M%S')


def test_cleanup_removes_only_expired_manifest_files(tmp_path):
    manager = TrashManager(tmp_path)
    expired = manager.trash_dir / 'expired.png'
    current = manager.trash_dir / 'current.png'
    expired.write_bytes(b'old')
    current.write_bytes(b'new')
    manager.manifest = {
        'expired.png': {'deleted_at': timestamp(31)},
        'current.png': {'deleted_at': timestamp(29)},
    }
    manager.save_manifest()

    removed = manager.cleanup_old_items(30)

    assert removed == 1
    assert not expired.exists()
    assert current.exists()
    assert set(manager.manifest) == {'current.png'}
    assert json.loads(manager.manifest_file.read_text()) == manager.manifest


def test_cleanup_ignores_malformed_and_unsafe_entries(tmp_path):
    manager = TrashManager(tmp_path)
    outside = tmp_path / 'outside.txt'
    outside.write_text('keep', encoding='utf-8')
    manager.manifest = {
        'malformed': {'deleted_at': 'not-a-date'},
        '../outside.txt': {'deleted_at': timestamp(100)},
    }

    removed = manager.cleanup_old_items(30)

    assert removed == 1
    assert outside.read_text(encoding='utf-8') == 'keep'
    assert 'malformed' in manager.manifest
    assert '../outside.txt' not in manager.manifest


def test_manifest_save_is_atomic_and_leaves_no_temporary_file(tmp_path):
    manager = TrashManager(tmp_path)
    manager.manifest = {'item': {'deleted_at': timestamp(1)}}

    manager.save_manifest()

    assert manager.manifest_file.exists()
    assert not manager.manifest_file.with_suffix('.json.tmp').exists()
