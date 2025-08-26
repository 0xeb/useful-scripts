#!/usr/bin/env python3
"""
Web server implementation for qslideshow.
"""

import http.server
import json
import mimetypes
import uuid
import random
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse

from .core import SlideshowContext


class WebSlideshowHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for web slideshow."""

    def __init__(self, *args, web_slideshow=None, **kwargs):
        self.web_slideshow = web_slideshow
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """Override to reduce verbosity."""
        pass  # Suppress default logging

    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Serve main HTML file
        if path in ('/', '/index.html'):
            self.serve_html()
        # Serve JavaScript file
        elif path == '/slideshow.js':
            self.serve_javascript()
        # Serve manifest file for PWA
        elif path == '/app.manifest':
            self.serve_manifest()
        # API endpoints
        elif path == '/api/images':
            self.serve_image_list()
        elif path.startswith('/api/image/'):
            self.serve_image(path)
        elif path == '/api/status':
            self.serve_status()
        elif path == '/api/config':
            self.serve_config()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/control':
            self.handle_control()
        else:
            self.send_error(404, "Not Found")

    def get_session_id(self):
        """Get or create session ID from cookies."""
        cookie_header = self.headers.get('Cookie', '')
        session_id = None

        if cookie_header:
            for cookie in cookie_header.split(';'):
                if '=' in cookie:
                    name, value = cookie.strip().split('=', 1)
                    if name == 'slideshow_session':
                        session_id = value
                        break

        return session_id

    def _require_session(self):
        session_id = self.get_session_id()
        if not session_id or session_id not in self.web_slideshow.sessions:
            return None, None
        return session_id, self.web_slideshow.sessions[session_id]

    def serve_html(self):
        """Serve the main HTML page."""
        # Try to load external HTML file first
        html_file = Path(__file__).parent / 'web' / 'index.html'

        if not html_file.exists():
            self.send_error(500, "Server misconfiguration: index.html not found")
            return

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Create or get session
        session_id = self.get_session_id()
        if not session_id or session_id not in self.web_slideshow.sessions:
            session_id = str(uuid.uuid4())
            self.web_slideshow.create_session(session_id)

        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Set-Cookie', f'slideshow_session={session_id}; Path=/; HttpOnly')
        self.end_headers()
        self.wfile.write(html_content.encode())

    def serve_javascript(self):
        """Serve the JavaScript file."""
        # Try to load external JS file first
        js_file = Path(__file__).parent / 'web' / 'slideshow.js'

        if not js_file.exists():
            self.send_error(500, "Server misconfiguration: slideshow.js not found")
            return

        with open(js_file, 'r', encoding='utf-8') as f:
            js_content = f.read()

        self.send_response(200)
        self.send_header('Content-Type', 'application/javascript')
        self.end_headers()
        self.wfile.write(js_content.encode())

    def serve_manifest(self):
        """Serve the PWA manifest file."""
        manifest_file = Path(__file__).parent / 'web' / 'app.manifest'

        if not manifest_file.exists():
            # Serve a default manifest if file doesn't exist
            manifest = {
                "name": "Web Slideshow",
                "short_name": "Slideshow",
                "display": "fullscreen",
                "orientation": "any",
                "start_url": "/",
                "background_color": "#000000",
                "theme_color": "#000000"
            }
            manifest_content = json.dumps(manifest)
        else:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest_content = f.read()

        self.send_response(200)
        self.send_header('Content-Type', 'application/manifest+json')
        self.end_headers()
        self.wfile.write(manifest_content.encode())

    def serve_image_list(self):
        """Serve the list of images."""
        session_id, session = self._require_session()
        if session is None:
            self.send_error(401, "No session")
            return

        image_list = []
        for i, idx in enumerate(session.image_order):
            path = self.web_slideshow.image_paths[idx]
            image_list.append({
                'index': i,
                'name': path.name,
                'path': str(path)
            })

        response = {'images': image_list}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def serve_image(self, path):
        """Serve an image file."""
        session_id, session = self._require_session()
        if session is None:
            self.send_error(401, "No session")
            return
        try:
            sess_idx = int(path.split('/')[-1])
            if 0 <= sess_idx < len(session.image_order):
                real_idx = session.image_order[sess_idx]
                image_path = self.web_slideshow.image_paths[real_idx]

                if image_path.exists():
                    mime_type, _ = mimetypes.guess_type(str(image_path))
                    if not mime_type:
                        mime_type = 'application/octet-stream'

                    self.send_response(200)
                    self.send_header('Content-Type', mime_type)
                    self.send_header('Cache-Control', 'max-age=3600')
                    self.end_headers()

                    with open(image_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error(404, "Image not found")
            else:
                self.send_error(404, "Invalid image index")
        except (ValueError, IndexError):
            self.send_error(400, "Invalid request")

    def serve_status(self):
        """Serve current status for this session."""
        session_id, session = self._require_session()
        if session is None:
            self.send_error(401, "No session")
            return

        status_text = session.format_status() if session.status_format else ""

        response = {
            'current_index': session.current_index,
            'total_images': len(session.image_order),
            'is_paused': session.is_paused,
            'speed': session.speed_seconds,
            'repeat': session.repeat,
            'shuffle': session.shuffle,
            'status_text': status_text
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def serve_config(self):
        """Serve configuration."""
        session_id, session = self._require_session()
        if session is None:
            self.send_error(401, "No session")
            return

        config = {
            'speed': session.speed_seconds,
            'repeat': session.repeat,
            'shuffle': session.shuffle,
            'fit_mode': session.fit_mode,
            'always_on_top': session.always_on_top
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(config).encode())

    def handle_control(self):
        """Handle control commands."""
        session_id, session = self._require_session()
        if session is None:
            self.send_error(401, "No session")
            return

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            self.send_error(400, "No data")
            return
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data.decode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
        action = data.get('action')

        result = {'success': False}

        if action == 'next':
            session.current_index += 1
            if session.current_index >= len(session.image_order):
                if session.repeat:
                    session.current_index = 0
                    session.repeat_count += 1
                else:
                    session.current_index = len(session.image_order) - 1
            result = {'success': True, 'current_index': session.current_index}

        elif action == 'previous':
            session.current_index -= 1
            if session.current_index < 0:
                if session.repeat:
                    session.current_index = len(session.image_order) - 1
                else:
                    session.current_index = 0
            result = {'success': True, 'current_index': session.current_index}

        elif action == 'toggle_pause':
            session.is_paused = not session.is_paused
            result = {'success': True, 'is_paused': session.is_paused}

        elif action == 'toggle_repeat':
            session.repeat = not session.repeat
            result = {'success': True, 'repeat': session.repeat}

        elif action == 'toggle_shuffle':
            session.shuffle = not session.shuffle
            if session.shuffle:
                random.shuffle(session.image_order)
            else:
                session.image_order = list(range(len(self.web_slideshow.image_paths)))
            session.current_index = 0
            result = {'success': True, 'shuffle': session.shuffle, 'current_index': session.current_index}

        elif action == 'increase_speed':
            session.speed_seconds += 1.0
            result = {'success': True, 'speed': session.speed_seconds}

        elif action == 'decrease_speed':
            session.speed_seconds = max(0.1, session.speed_seconds - 1.0)
            result = {'success': True, 'speed': session.speed_seconds}

        else:
            result = {'success': False, 'error': 'Unknown action'}
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


class WebSlideshow:
    """Web-based slideshow server."""

    def __init__(self, image_paths: List[Path], config: Dict[str, Any], port: int = 8000):
        """
        Initialize web slideshow server.

        Args:
            image_paths: List of image paths to serve
            config: Configuration dictionary
            port: Port to run server on
        """
        self.image_paths = image_paths
        self.original_image_paths = image_paths.copy()
        self.config = config
        self.port = port
        self.sessions: Dict[str, SlideshowContext] = {}  # session_id -> SlideshowContext

        # Apply shuffle to the main list if requested
        if config.get('shuffle', False):
            random.shuffle(self.image_paths)

        # Create handler with reference to this slideshow
        self.handler = lambda *args, **kwargs: WebSlideshowHandler(
            *args, web_slideshow=self, **kwargs
        )

    def create_session(self, session_id: str):
        """Create a new session for a client."""
        # Each session gets its own context
        session = SlideshowContext(
            image_paths=self.image_paths,  # Share the same image list
            speed=self.config.get('speed', 3.0),
            repeat=self.config.get('repeat', False),
            fit_mode=self.config.get('fit_mode', 'shrink'),
            status_format=self.config.get('status_format'),
            always_on_top=self.config.get('always_on_top', False),
            shuffle=False,  # prevent mutation of shared image list
            paused=self.config.get('paused', False)
        )
        session.current_index = 0  # Each client starts at image 0
        # Set current_image to None as we don't load images in web mode
        session.current_image = None
        # Per-session order (list of indices into self.image_paths)
        n = len(self.image_paths)
        session.image_order = list(range(n))
        if self.config.get('shuffle', False):
            random.shuffle(session.image_order)
            session.shuffle = True
        else:
            session.shuffle = False
        self.sessions[session_id] = session
        return session

    def run(self):
        """Start the web server."""
        server_address = ('', self.port)
        httpd = http.server.HTTPServer(server_address, self.handler)

        print(f"Web slideshow server running on:")
        print(f"  http://localhost:{self.port}")
        print(f"  http://0.0.0.0:{self.port}")
        print(f"\nServing {len(self.image_paths)} images")
        print("Press Ctrl+C to stop the server")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")