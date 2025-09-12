#!/usr/bin/env python3
"""
GHView: a tiny local GitHub‑style browser for any folder/repo.

Usage:
  python ghview.py [ROOT_DIR] [--port 8000]

Features:
  • Directory listing with README rendering (like GitHub)
  • Renders .md/.markdown with GitHub‑like styles
  • Syntax‑highlighted source viewer for common code files
  • Click through folders/files; images and other assets just work
  • Safe path handling (no escaping root)
"""
import argparse
import html
import io
import mimetypes
import os
import posixpath
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

# Third‑party deps: markdown + pygments
import markdown
from pygments import highlight
from pygments.lexers import get_lexer_for_filename, guess_lexer
from pygments.formatters import HtmlFormatter

GITHUB_CSS = r"""
/* Minimal GitHub‑ish look */
:root{--bg:#0b0c0f;--panel:#0f1116;--text:#e6e7eb;--muted:#a9adbb;--link:#6ea8fe;--border:#20242f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,"Apple Color Emoji","Segoe UI Emoji"}
.container{max-width:1120px;margin:0 auto;padding:24px}
.header{display:flex;gap:12px;align-items:center;margin-bottom:16px}
.header a{color:var(--link);text-decoration:none}
.header .crumbs{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:16px;box-shadow:0 2px 24px rgba(0,0,0,.35)}
.listing{overflow:auto}
.listing table{width:100%;border-collapse:separate;border-spacing:0}
.listing th,.listing td{padding:10px 12px;border-bottom:1px solid var(--border);white-space:nowrap}
.listing th:first-child,.listing td:first-child{padding-left:16px}
.listing th:last-child,.listing td:last-child{padding-right:16px}
.listing tr:hover td{background:rgba(255,255,255,.02)}
.file{display:flex;gap:10px;align-items:center}
.badge{font-size:12px;color:var(--muted)}
.markdown-body{padding:24px}
.markdown-body h1,.markdown-body h2,.markdown-body h3{border-bottom:1px solid var(--border);padding-bottom:4px}
.markdown-body pre{background:#0b0d12;border:1px solid var(--border);padding:12px;border-radius:12px;overflow:auto}
.markdown-body code{background:#0b0d12;border:1px solid var(--border);padding:.1em .35em;border-radius:8px}
.rawbar{display:flex;gap:8px;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--border)}
.rawbar a{color:var(--link);text-decoration:none}
.footer{color:var(--muted);margin-top:16px;font-size:13px}
.breadcrumb{display:inline-block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
"""

ICON_FILE = "📄"
ICON_DIR = "📁"
ICON_MD = "📝"
ICON_IMG = "🖼️"

MD_EXTS = {".md", ".markdown"}
CODE_EXTS = {
    ".py",".js",".jsx",".ts",".tsx",".json",".yml",".yaml",".toml",".ini",
    ".sh",".bash",".zsh",".rb",".go",".rs",".java",".kt",".c",".h",".cpp",".hpp",
    ".css",".html",".sql",".php",".pl",".lua",".r",".swift"
}
IMG_EXTS = {".png",".jpg",".jpeg",".gif",".svg",".webp",".bmp",".ico"}

class GHViewHandler(SimpleHTTPRequestHandler):
    # root directory injected on server init
    def translate_path(self, path):
        # Prevent .. traversal & map to root
        path = posixpath.normpath(unquote(path.split("?",1)[0]))
        words = [w for w in path.split('/') if w and w != '.']
        full = self.server.root
        for w in words:
            if w == '..':
                continue
            full = os.path.join(full, w)
        
        # Resolve symlinks and ensure path is still under root
        try:
            real_path = os.path.realpath(full)
            real_root = os.path.realpath(self.server.root)
            if not real_path.startswith(real_root + os.sep) and real_path != real_root:
                return self.server.root
        except (OSError, ValueError):
            return self.server.root
            
        return full

    def _send_headers(self, content_type="text/html; charset=utf-8", content_length=None):
        """Send response headers with security headers"""
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        # Security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'none'")
        self.end_headers()
    
    def list_directory(self, path):
        # Render README (if present) + directory listing
        try:
            entries = sorted(os.listdir(path), key=str.lower)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None
        readme_file = next((f for f in entries if f.lower() in ("readme.md","readme.markdown")), None)
        content = io.StringIO()
        content.write(self._html_header(path))

        # README panel
        if readme_file and os.path.isfile(os.path.join(path, readme_file)):
            content.write('<div class="panel" style="margin-bottom:16px">')
            content.write('<div class="rawbar"><div><strong>README</strong></div>'
                          f'<div><a href="{html.escape(readme_file)}?raw=1">Raw</a></div></div>')
            md_html = self._render_markdown(os.path.join(path, readme_file))
            content.write(f'<article class="markdown-body">{md_html}</article>')
            content.write('</div>')

        # Listing panel
        content.write('<div class="panel listing">')
        content.write('<table><thead><tr><th>Name</th><th class="badge">Type</th><th class="badge" style="text-align:right">Size</th></tr></thead><tbody>')
        # Parent link if not at root
        rel = os.path.relpath(path, self.server.root)
        if rel != '.':
            content.write('<tr><td class="file">⬆️ <a href="..">..</a></td><td></td><td></td></tr>')
        for name in entries:
            if name.startswith('.'):
                continue
            full = os.path.join(path, name)
            display = html.escape(name)
            ext = os.path.splitext(name)[1].lower()
            if os.path.isdir(full):
                icon = ICON_DIR
                href = name + '/'
                typ = 'dir'
                size = ''
            else:
                if ext in MD_EXTS:
                    icon, typ = ICON_MD, 'markdown'
                elif ext in IMG_EXTS:
                    icon, typ = ICON_IMG, 'image'
                else:
                    icon, typ = ICON_FILE, (ext[1:] or 'file')
                href = name
                size = self._fmt_size(os.path.getsize(full))
            content.write(f'<tr><td class="file">{icon} <a href="{html.escape(href)}">{display}</a></td><td class="badge">{html.escape(typ)}</td><td class="badge" style="text-align:right">{html.escape(size)}</td></tr>')
        content.write('</tbody></table></div>')

        content.write(self._html_footer())
        body = content.getvalue().encode('utf-8', 'surrogateescape')
        self._send_headers(content_length=len(body))
        return io.BytesIO(body)

    def do_GET(self):
        # Ensure directory URLs have trailing slash
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                self.send_response(301)
                self.send_header('Location', self.path + '/')
                self.end_headers()
                return
            f = self.list_directory(path)
            if f:
                self.copyfile(f, self.wfile)
            return

        # File request
        query = ''
        if '?' in self.path:
            _, query = self.path.split('?', 1)
        raw = 'raw=1' in query

        ext = os.path.splitext(path)[1].lower()
        if not os.path.exists(path):
            self.send_error(404, "File not found")
            return

        if raw or (ext in IMG_EXTS):
            # Serve as static
            return super().do_GET()

        if ext in MD_EXTS:
            return self._serve_markdown(path)

        if ext in CODE_EXTS or self._is_text_file(path):
            return self._serve_source(path)

        # Fallback to static for binaries/others
        return super().do_GET()

    # Helpers
    def _serve_markdown(self, filepath):
        body_html = self._render_markdown(filepath)
        title = os.path.basename(filepath)
        out = io.StringIO()
        out.write(self._html_header(filepath, title=title, raw_link=True))
        out.write('<div class="panel">')
        out.write('<div class="rawbar"><div><strong>Markdown</strong></div>'
                  f'<div><a href="{html.escape(os.path.basename(filepath))}?raw=1">Raw</a></div></div>')
        out.write(f'<article class="markdown-body">{body_html}</article>')
        out.write('</div>')
        out.write(self._html_footer())
        data = out.getvalue().encode('utf-8')
        self._send_headers(content_length=len(data))
        self.wfile.write(data)

    def _serve_source(self, filepath):
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            code = f.read()
        try:
            lexer = get_lexer_for_filename(filepath, code)
        except Exception:
            try:
                lexer = guess_lexer(code)
            except Exception:
                lexer = None
        if lexer is None:
            escaped = f"<pre><code>{html.escape(code)}</code></pre>"
            highlighted = escaped
            css = ''
        else:
            formatter = HtmlFormatter(nowrap=False, linenos=True)
            highlighted = highlight(code, lexer, formatter)
            css = f"<style>{formatter.get_style_defs('.highlight')}</style>"
        title = os.path.basename(filepath)
        out = io.StringIO()
        out.write(self._html_header(filepath, title=title, raw_link=True))
        out.write(css)
        out.write('<div class="panel">')
        out.write('<div class="rawbar"><div><strong>Source</strong></div>'
                  f'<div><a href="{html.escape(os.path.basename(filepath))}?raw=1">Raw</a></div></div>')
        out.write(f'<div class="markdown-body">{highlighted}</div>')
        out.write('</div>')
        out.write(self._html_footer())
        data = out.getvalue().encode('utf-8')
        self._send_headers(content_length=len(data))
        self.wfile.write(data)

    def _render_markdown(self, filepath):
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        # Use safe mode to prevent arbitrary HTML injection
        try:
            # Try to use the safe_mode if available (older versions)
            return markdown.markdown(text, extensions=['fenced_code','tables','toc','codehilite'], safe_mode='escape')
        except TypeError:
            # For newer versions that don't have safe_mode, the markdown library
            # escapes HTML by default, but we can ensure text is clean
            return markdown.markdown(html.escape(text), extensions=['fenced_code','tables','toc','codehilite'])

    def _html_header(self, path, title=None, raw_link=False):
        rel = os.path.relpath(os.path.dirname(path) if os.path.isfile(path) else path, self.server.root)
        crumbs = []
        accum = ''
        crumbs.append('<a href="/">/</a>')
        if rel != '.':
            for part in rel.split(os.sep):
                if not part:
                    continue
                accum = f"{accum}/{part}" if accum else part
                crumbs.append(f'<span>/</span> <a href="/{accum}/">{html.escape(part)}</a>')
        title_text = title or ("Index of /" if rel == '.' else f"Index of /{rel}")
        return f"""
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title_text)}</title>
<style>{GITHUB_CSS}</style>
</head><body>
<div class="container">
  <div class="header">
    <div class="crumbs breadcrumb">{''.join(crumbs)}</div>
  </div>
"""

    def _html_footer(self):
        return """
  <div class="footer">GHView • local repo browser</div>
</div>
</body></html>
"""

    def _fmt_size(self, n):
        for unit in ['B','KB','MB','GB','TB']:
            if n < 1024.0:
                return f"{n:3.1f} {unit}" if unit != 'B' else f"{int(n)} {unit}"
            n /= 1024.0
        return f"{n:.1f} PB"

    def _is_text_file(self, path, blocksize=512):
        try:
            with open(path, 'rb') as f:
                chunk = f.read(blocksize)
            if b'\0' in chunk:
                return False
            # Heuristic: if it's mostly printable bytes
            textchars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)))
            return all(c in textchars for c in chunk)
        except Exception:
            return False


def run(root, port):
    Handler = GHViewHandler
    httpd = HTTPServer(("127.0.0.1", port), Handler)
    httpd.root = os.path.abspath(root)
    sa = httpd.socket.getsockname()
    print(f"Serving {httpd.root} at http://{sa[0]}:{sa[1]}/ (Ctrl+C to quit)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


def main():
    parser = argparse.ArgumentParser(description='Local GitHub‑style repo browser')
    parser.add_argument('root', nargs='?', default='.', help='Root folder to serve (default: .)')
    parser.add_argument('--port', type=int, default=8000, help='Port (default: 8000)')
    args = parser.parse_args()
    
    run(args.root, args.port)


if __name__ == '__main__':
    main()
