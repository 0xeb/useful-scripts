#!/usr/bin/env python3
"""
Simple file sharing server — browse, download, and upload files over LAN.
"""

import argparse
import socket
import secrets
from pathlib import Path
from urllib.parse import quote, unquote

from flask import (
    Flask,
    request,
    redirect,
    render_template_string,
    send_file,
    abort,
    session,
    url_for,
)
from werkzeug.utils import secure_filename


DEFAULT_PORT = 8019

# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

LOGIN_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Login — File Server</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;
           background: #f5f5f5; }
    .card { background: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.12);
            width: 320px; }
    h2 { margin-top: 0; }
    input[type=password] { width: 100%; padding: .5rem; margin: .5rem 0; box-sizing: border-box;
                           border: 1px solid #ccc; border-radius: 4px; }
    button { padding: .5rem 1.5rem; background: #0366d6; color: #fff; border: none;
             border-radius: 4px; cursor: pointer; }
    button:hover { background: #0255b3; }
    .error { color: #d00; margin-bottom: .5rem; }
  </style>
</head>
<body>
  <div class="card">
    <h2>File Server</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="post" action="/login">
      <input type="password" name="password" placeholder="Password" autofocus>
      <button type="submit">Login</button>
    </form>
  </div>
</body>
</html>
"""

SINGLE_FILE_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Download — {{ filename }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;
           background: #f5f5f5; }
    .card { background: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.12);
            text-align: center; }
    a.btn { display: inline-block; padding: .75rem 2rem; background: #0366d6; color: #fff;
            text-decoration: none; border-radius: 4px; margin-top: 1rem; }
    a.btn:hover { background: #0255b3; }
    .size { color: #666; }
  </style>
</head>
<body>
  <div class="card">
    <h2>{{ filename }}</h2>
    <p class="size">{{ size }}</p>
    <a class="btn" href="/download/{{ filename_encoded }}">Download</a>
  </div>
</body>
</html>
"""

DIRECTORY_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           max-width: 900px; margin: 2rem auto; padding: 0 1rem; background: #f5f5f5; }
    h1 { word-break: break-all; }
    table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
            overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
    th, td { text-align: left; padding: .6rem 1rem; border-bottom: 1px solid #eee; }
    th { background: #fafafa; }
    a { color: #0366d6; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .size { color: #666; white-space: nowrap; }
    .upload-form { margin-top: 1.5rem; background: #fff; padding: 1.5rem; border-radius: 8px;
                   box-shadow: 0 1px 4px rgba(0,0,0,.1); }
    .upload-form input[type=file] { margin-right: .5rem; }
    .upload-form button { padding: .5rem 1.5rem; background: #28a745; color: #fff; border: none;
                          border-radius: 4px; cursor: pointer; }
    .upload-form button:hover { background: #22863a; }
    .msg { padding: .5rem 1rem; margin-bottom: 1rem; border-radius: 4px; }
    .msg.ok { background: #dcffe4; color: #22863a; }
    .msg.err { background: #ffeef0; color: #d00; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  {% if message %}<div class="msg {{ msg_class }}">{{ message }}</div>{% endif %}
  <table>
    <tr><th>Name</th><th>Size</th></tr>
    {% if parent_href is not none %}
    <tr><td><a href="{{ parent_href }}">..</a></td><td></td></tr>
    {% endif %}
    {% for entry in entries %}
    <tr>
      <td><a href="{{ entry.href }}">{{ entry.name }}{{ "/" if entry.is_dir else "" }}</a></td>
      <td class="size">{{ entry.size }}</td>
    </tr>
    {% endfor %}
  </table>
  {% if allow_upload %}
  <div class="upload-form">
    <form method="post" enctype="multipart/form-data" action="{{ upload_action }}">
      <input type="file" name="file" required>
      <button type="submit">Upload</button>
    </form>
  </div>
  {% endif %}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_size(size_bytes):
    """Return a human-readable file size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def get_local_ips():
    """Return a list of non-loopback IPv4 addresses for this machine."""
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("127."):
                ips.append(addr)
    except Exception:
        pass
    # Deduplicate while preserving order
    return list(dict.fromkeys(ips))


def _is_safe_path(base: Path, target: Path) -> bool:
    """Return True if *target* is inside *base* (no path traversal)."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(root_path, password=None, allow_upload=True, single_file=False):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(16)

    root = Path(root_path).resolve()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------
    def _requires_auth():
        return password is not None

    def _is_authenticated():
        return not _requires_auth() or session.get("authenticated")

    @app.before_request
    def check_auth():
        if request.endpoint in ("login", "login_post", "static"):
            return
        if _requires_auth() and not _is_authenticated():
            return redirect(url_for("login"))

    @app.route("/login", methods=["GET"])
    def login():
        return render_template_string(LOGIN_HTML, error=None)

    @app.route("/login", methods=["POST"])
    def login_post():
        if request.form.get("password") == password:
            session["authenticated"] = True
            return redirect("/")
        return render_template_string(LOGIN_HTML, error="Incorrect password"), 401

    # ------------------------------------------------------------------
    # Single-file mode
    # ------------------------------------------------------------------
    if single_file:
        file_path = root  # root is actually the file in this mode

        @app.route("/")
        def index():
            size = format_size(file_path.stat().st_size)
            return render_template_string(
                SINGLE_FILE_HTML,
                filename=file_path.name,
                filename_encoded=quote(file_path.name),
                size=size,
            )

        @app.route("/download/<path:filename>")
        def download(filename):
            if unquote(filename) != file_path.name:
                abort(404)
            return send_file(file_path, as_attachment=True)

        return app

    # ------------------------------------------------------------------
    # Directory mode
    # ------------------------------------------------------------------
    @app.route("/", defaults={"subpath": ""})
    @app.route("/browse/<path:subpath>")
    def browse(subpath):
        target = (root / unquote(subpath)).resolve()
        if not _is_safe_path(root, target) or not target.is_dir():
            abort(404)

        message = request.args.get("msg")
        msg_class = request.args.get("cls", "ok")

        entries = []
        try:
            items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            abort(403)

        for item in items:
            rel = item.relative_to(root)
            if item.is_dir():
                href = "/browse/" + quote(str(rel.as_posix()))
                entries.append({"name": item.name, "href": href, "size": "", "is_dir": True})
            else:
                href = "/download/" + quote(str(rel.as_posix()))
                size = format_size(item.stat().st_size)
                entries.append({"name": item.name, "href": href, "size": size, "is_dir": False})

        parent_href = None
        if target != root:
            parent_rel = target.parent.relative_to(root)
            parent_href = "/browse/" + quote(str(parent_rel.as_posix())) if str(parent_rel) != "." else "/"

        rel_display = str(target.relative_to(root))
        title = "/" if rel_display == "." else "/" + rel_display.replace("\\", "/")

        upload_action = "/upload/" + quote(subpath) if subpath else "/upload/"

        return render_template_string(
            DIRECTORY_HTML,
            title=title,
            entries=entries,
            parent_href=parent_href,
            allow_upload=allow_upload,
            upload_action=upload_action,
            message=message,
            msg_class=msg_class,
        )

    @app.route("/download/<path:filepath>")
    def download(filepath):
        target = (root / unquote(filepath)).resolve()
        if not _is_safe_path(root, target) or not target.is_file():
            abort(404)
        return send_file(target, as_attachment=True)

    @app.route("/upload/", defaults={"subpath": ""}, methods=["POST"])
    @app.route("/upload/<path:subpath>", methods=["POST"])
    def upload(subpath):
        if not allow_upload:
            abort(403)

        target_dir = (root / unquote(subpath)).resolve()
        if not _is_safe_path(root, target_dir) or not target_dir.is_dir():
            abort(404)

        if "file" not in request.files:
            redir = "/browse/" + quote(subpath) if subpath else "/"
            return redirect(f"{redir}?msg=No+file+selected&cls=err")

        f = request.files["file"]
        if f.filename == "":
            redir = "/browse/" + quote(subpath) if subpath else "/"
            return redirect(f"{redir}?msg=No+file+selected&cls=err")

        filename = secure_filename(f.filename)
        f.save(target_dir / filename)

        redir = "/browse/" + quote(subpath) if subpath else "/"
        return redirect(f"{redir}?msg=Uploaded+{quote(filename)}&cls=ok")

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Serve files for download (and upload) over the local network",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="File or directory to serve (default: current directory)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--password", default=None, help="Require a password to access the server")
    parser.add_argument("--no-upload", action="store_true", help="Disable file uploads")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"Error: '{args.path}' does not exist")
        return 1

    single_file = target.is_file()
    app = create_app(
        root_path=target,
        password=args.password,
        allow_upload=not args.no_upload and not single_file,
        single_file=single_file,
    )

    # Print access info
    print(f"Serving {'file' if single_file else 'directory'}: {target}")
    print(f"Local:   http://localhost:{args.port}")
    for ip in get_local_ips():
        print(f"Network: http://{ip}:{args.port}")
    if args.password:
        print("Password protection: enabled")
    if args.no_upload or single_file:
        print("Uploads: disabled")
    print()

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
