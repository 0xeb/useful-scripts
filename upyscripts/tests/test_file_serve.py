"""
Tests for upy.file_serve — file sharing server.

Tests cover:
- Directory browsing and navigation
- File download (correct content)
- Single-file mode
- File upload
- Password authentication
- Path traversal prevention
"""

import pytest
import tempfile
import time
import requests
import threading
import socket
from pathlib import Path

from upyscripts.file_serve import create_app


def find_free_port():
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_dir():
    """Create a temporary directory with test files and subdirectories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Files in root
        (root / "hello.txt").write_text("hello world")
        (root / "data.bin").write_bytes(b"\x00\x01\x02\x03")

        # Subdirectory with files
        sub = root / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested content")

        # Empty subdirectory
        (root / "empty").mkdir()

        yield root


@pytest.fixture
def server(test_dir):
    """Start a file server on the test directory (no password, uploads enabled)."""
    port = find_free_port()
    app = create_app(root_path=test_dir, allow_upload=True)
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False),
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{port}", test_dir


@pytest.fixture
def server_no_upload(test_dir):
    """Start a file server with uploads disabled."""
    port = find_free_port()
    app = create_app(root_path=test_dir, allow_upload=False)
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False),
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{port}", test_dir


@pytest.fixture
def server_password(test_dir):
    """Start a file server with password protection."""
    port = find_free_port()
    app = create_app(root_path=test_dir, password="secret123", allow_upload=True)
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False),
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{port}", test_dir


@pytest.fixture
def single_file_server(test_dir):
    """Start a file server in single-file mode."""
    file_path = test_dir / "hello.txt"
    port = find_free_port()
    app = create_app(root_path=file_path, single_file=True)
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False),
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{port}", file_path


# ---------------------------------------------------------------------------
# Directory browsing
# ---------------------------------------------------------------------------

class TestDirectoryBrowsing:
    """Test browsing directories."""

    def test_root_listing(self, server):
        """Root page lists files and subdirectories."""
        base, _ = server
        r = requests.get(f"{base}/")
        assert r.status_code == 200
        assert "hello.txt" in r.text
        assert "data.bin" in r.text
        assert "subdir" in r.text
        assert "empty" in r.text

    def test_subdirectory_listing(self, server):
        """Browsing a subdirectory shows its contents."""
        base, _ = server
        r = requests.get(f"{base}/browse/subdir")
        assert r.status_code == 200
        assert "nested.txt" in r.text

    def test_parent_link_in_subdir(self, server):
        """Subdirectory pages include a parent (..) link."""
        base, _ = server
        r = requests.get(f"{base}/browse/subdir")
        assert r.status_code == 200
        assert ".." in r.text

    def test_empty_directory(self, server):
        """Empty directories render without error."""
        base, _ = server
        r = requests.get(f"{base}/browse/empty")
        assert r.status_code == 200

    def test_nonexistent_directory_404(self, server):
        """Browsing a nonexistent path returns 404."""
        base, _ = server
        r = requests.get(f"{base}/browse/no_such_dir")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------

class TestFileDownload:
    """Test downloading files."""

    def test_download_text_file(self, server):
        """Download a text file and verify content."""
        base, _ = server
        r = requests.get(f"{base}/download/hello.txt")
        assert r.status_code == 200
        assert r.text == "hello world"

    def test_download_binary_file(self, server):
        """Download a binary file and verify content."""
        base, _ = server
        r = requests.get(f"{base}/download/data.bin")
        assert r.status_code == 200
        assert r.content == b"\x00\x01\x02\x03"

    def test_download_nested_file(self, server):
        """Download a file inside a subdirectory."""
        base, _ = server
        r = requests.get(f"{base}/download/subdir/nested.txt")
        assert r.status_code == 200
        assert r.text == "nested content"

    def test_download_nonexistent_404(self, server):
        """Downloading a nonexistent file returns 404."""
        base, _ = server
        r = requests.get(f"{base}/download/nope.txt")
        assert r.status_code == 404

    def test_download_has_attachment_header(self, server):
        """Response includes Content-Disposition attachment header."""
        base, _ = server
        r = requests.get(f"{base}/download/hello.txt")
        assert "attachment" in r.headers.get("Content-Disposition", "").lower()


# ---------------------------------------------------------------------------
# Single-file mode
# ---------------------------------------------------------------------------

class TestSingleFileMode:
    """Test serving a single file."""

    def test_index_shows_filename(self, single_file_server):
        """Index page shows the filename."""
        base, file_path = single_file_server
        r = requests.get(f"{base}/")
        assert r.status_code == 200
        assert file_path.name in r.text

    def test_download_single_file(self, single_file_server):
        """Can download the served file."""
        base, file_path = single_file_server
        r = requests.get(f"{base}/download/{file_path.name}")
        assert r.status_code == 200
        assert r.text == "hello world"

    def test_other_files_not_accessible(self, single_file_server):
        """Other filenames return 404 in single-file mode."""
        base, _ = single_file_server
        r = requests.get(f"{base}/download/data.bin")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    """Test file upload functionality."""

    def test_upload_file(self, server):
        """Upload a file and verify it lands on disk."""
        base, root = server
        r = requests.post(
            f"{base}/upload/",
            files={"file": ("upload_test.txt", b"uploaded content")},
            allow_redirects=False,
        )
        assert r.status_code == 302
        assert (root / "upload_test.txt").read_text() == "uploaded content"

    def test_upload_to_subdir(self, server):
        """Upload a file into a subdirectory."""
        base, root = server
        r = requests.post(
            f"{base}/upload/subdir",
            files={"file": ("sub_upload.txt", b"sub content")},
            allow_redirects=False,
        )
        assert r.status_code == 302
        assert (root / "subdir" / "sub_upload.txt").read_text() == "sub content"

    def test_upload_disabled(self, server_no_upload):
        """Upload returns 403 when uploads are disabled."""
        base, _ = server_no_upload
        r = requests.post(
            f"{base}/upload/",
            files={"file": ("test.txt", b"data")},
        )
        assert r.status_code == 403

    def test_upload_form_hidden_when_disabled(self, server_no_upload):
        """Directory listing hides the upload form when uploads are disabled."""
        base, _ = server_no_upload
        r = requests.get(f"{base}/")
        assert r.status_code == 200
        assert 'type="file"' not in r.text


# ---------------------------------------------------------------------------
# Password authentication
# ---------------------------------------------------------------------------

class TestPasswordAuth:
    """Test password protection."""

    def test_unauthenticated_redirects_to_login(self, server_password):
        """Unauthenticated requests redirect to /login."""
        base, _ = server_password
        r = requests.get(f"{base}/", allow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]

    def test_wrong_password_rejected(self, server_password):
        """Wrong password returns 401."""
        base, _ = server_password
        s = requests.Session()
        r = s.post(f"{base}/login", data={"password": "wrong"})
        assert r.status_code == 401

    def test_correct_password_grants_access(self, server_password):
        """Correct password allows browsing."""
        base, _ = server_password
        s = requests.Session()
        r = s.post(f"{base}/login", data={"password": "secret123"}, allow_redirects=False)
        assert r.status_code == 302  # redirect to /

        r = s.get(f"{base}/")
        assert r.status_code == 200
        assert "hello.txt" in r.text

    def test_authenticated_download(self, server_password):
        """Authenticated user can download files."""
        base, _ = server_password
        s = requests.Session()
        s.post(f"{base}/login", data={"password": "secret123"})

        r = s.get(f"{base}/download/hello.txt")
        assert r.status_code == 200
        assert r.text == "hello world"


# ---------------------------------------------------------------------------
# Edge cases — path traversal
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test security edge cases."""

    def test_path_traversal_browse_blocked(self, server):
        """Path traversal in browse URL is blocked."""
        base, _ = server
        r = requests.get(f"{base}/browse/../../etc/passwd")
        assert r.status_code == 404

    def test_path_traversal_download_blocked(self, server):
        """Path traversal in download URL is blocked."""
        base, _ = server
        r = requests.get(f"{base}/download/../../etc/passwd")
        assert r.status_code == 404

    def test_path_traversal_upload_blocked(self, server):
        """Path traversal in upload URL is blocked."""
        base, _ = server
        r = requests.post(
            f"{base}/upload/../../etc",
            files={"file": ("evil.txt", b"pwned")},
        )
        assert r.status_code == 404
