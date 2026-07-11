from datetime import datetime

from upyscripts.lib.files.find import find_latest_file_date


def test_find_latest_file_date_filters_and_returns_latest(tmp_path):
    older = tmp_path / "older.py"
    newer = tmp_path / "newer.py"
    ignored = tmp_path / "newest.txt"
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")

    older.touch()
    newer.touch()
    ignored.touch()
    older_mtime = 1_700_000_000
    newer_mtime = older_mtime + 10
    ignored_mtime = newer_mtime + 10
    import os
    os.utime(older, (older_mtime, older_mtime))
    os.utime(newer, (newer_mtime, newer_mtime))
    os.utime(ignored, (ignored_mtime, ignored_mtime))

    latest_date, latest_file = find_latest_file_date(str(tmp_path), "*.py")

    assert latest_date == datetime.fromtimestamp(newer_mtime)
    assert latest_file == str(newer)


def test_find_latest_file_date_returns_empty_result(tmp_path):
    assert find_latest_file_date(str(tmp_path), "*.py") == (None, None)
