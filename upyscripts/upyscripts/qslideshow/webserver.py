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
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from .core import SlideshowContext
from .config import ConfigManager
from .actions import action_registry, ExternalToolManager
from .hotkeys import HotkeyManager, WebHotkeyAdapter
from .gestures import GestureManager
from .history import ActionHistory, UndoAction, RedoAction
from .trash import TrashManager


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
        # Serve login page
        elif path == '/login.html':
            self.serve_login()
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
        elif path == '/api/actions':
            self.serve_actions()
        elif path == '/api/hotkeys':
            self.serve_hotkeys()
        elif path == '/api/gestures':
            self.serve_gestures()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/authenticate':
            self.handle_authenticate()
        elif self.path == '/api/control':
            self.handle_control()
        elif self.path == '/api/execute':
            self.handle_execute_action()
        elif self.path == '/api/gesture':
            self.handle_gesture()
        else:
            self.send_error(404, "Not Found")

    def get_auth_session_id(self):
        """Get authentication session ID from cookie (shared across tabs)."""
        cookie_header = self.headers.get('Cookie', '')
        auth_session_id = None

        if cookie_header:
            for cookie in cookie_header.split(';'):
                if '=' in cookie:
                    name, value = cookie.strip().split('=', 1)
                    if name == 'auth_session':
                        auth_session_id = value
                        break

        return auth_session_id

    def get_slideshow_session_id(self):
        """Get slideshow session ID from header (unique per tab)."""
        return self.headers.get('X-Session-ID')

    def _require_session(self):
        """Get slideshow session. Creates new session if header provides an ID."""
        session_id = self.get_slideshow_session_id()
        if not session_id:
            return None, None

        # Create session if it doesn't exist
        if session_id not in self.web_slideshow.sessions:
            self.web_slideshow.create_session(session_id)

        return session_id, self.web_slideshow.sessions[session_id]

    def _check_authentication(self):
        """Check if the auth session is authenticated. Returns True if no password or authenticated."""
        # If no password is set, always allow access
        if not self.web_slideshow.password:
            return True

        # Check if auth session is authenticated
        auth_session_id = self.get_auth_session_id()
        return auth_session_id in self.web_slideshow.authenticated_sessions

    def serve_html(self):
        """Serve the main HTML page."""
        # Check authentication if password is set
        if not self._check_authentication():
            self.send_response(302)
            self.send_header('Location', '/login.html')
            self.end_headers()
            return

        # Try to load external HTML file first
        html_file = Path(__file__).parent / 'web' / 'index.html'

        if not html_file.exists():
            self.send_error(500, "Server misconfiguration: index.html not found")
            return

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # No need to create session here - client will send session ID via header
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        
        # Add cache-busting headers in development mode
        if self.web_slideshow.config.get('web_dev', False):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        
        self.end_headers()
        self.wfile.write(html_content.encode())

    def serve_login(self):
        """Serve the login page."""
        login_file = Path(__file__).parent / 'web' / 'login.html'

        if not login_file.exists():
            self.send_error(500, "Server misconfiguration: login.html not found")
            return

        with open(login_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        self.send_response(200)
        self.send_header('Content-Type', 'text/html')

        # Add cache-busting headers in development mode
        if self.web_slideshow.config.get('web_dev', False):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')

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
        
        # Add cache-busting headers in development mode
        if self.web_slideshow.config.get('web_dev', False):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        
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
        
        # Add cache-busting headers in development mode
        if self.web_slideshow.config.get('web_dev', False):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        
        self.end_headers()
        self.wfile.write(manifest_content.encode())

    def serve_image_list(self):
        """Serve the list of images."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

        session_id, session = self._require_session()
        if session is None:
            self.send_error(400, "Missing session ID header")
            return

        image_list = []
        # Use image_order if available, otherwise use direct indices
        if hasattr(session, 'image_order'):
            for i, idx in enumerate(session.image_order):
                path = self.web_slideshow.image_paths[idx]
                image_list.append({
                    'index': i,
                    'name': path.name,
                    'path': str(path)
                })
        else:
            for i, path in enumerate(self.web_slideshow.image_paths):
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
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

        session_id, session = self._require_session()
        if session is None:
            # For image serving, we can work without a session
            session_id = None
            session = None
        
        try:
            sess_idx = int(path.split('/')[-1])
            
            # Get the actual image path
            if session and hasattr(session, 'image_order'):
                if 0 <= sess_idx < len(session.image_order):
                    real_idx = session.image_order[sess_idx]
                    image_path = self.web_slideshow.image_paths[real_idx]
                else:
                    self.send_error(404, "Image not found")
                    return
            else:
                # No session or no image_order, use direct index
                if 0 <= sess_idx < len(self.web_slideshow.image_paths):
                    image_path = self.web_slideshow.image_paths[sess_idx]
                else:
                    self.send_error(404, "Image not found")
                    return
            
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
        except (ValueError, IndexError):
            self.send_error(400, "Invalid request")

    def serve_status(self):
        """Serve current status for this session."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

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
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

        session_id, session = self._require_session()
        if session is None:
            self.send_error(401, "No session")
            return

        config = {
            'speed': session.speed_seconds,
            'repeat': session.repeat,
            'shuffle': session.shuffle,
            'fit_mode': session.fit_mode,
            'always_on_top': session.always_on_top,
            'has_undo': session.action_history.can_undo() if hasattr(session, 'action_history') else False,
            'has_redo': session.action_history.can_redo() if hasattr(session, 'action_history') else False
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(config).encode())

    def handle_authenticate(self):
        """Handle password authentication."""
        # Read password from POST data
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

        password = data.get('password', '')

        # Check if password matches
        if self.web_slideshow.password and password == self.web_slideshow.password:
            # Get or create auth session
            auth_session_id = self.get_auth_session_id()
            if not auth_session_id:
                auth_session_id = str(uuid.uuid4())

            # Mark auth session as authenticated
            self.web_slideshow.authenticated_sessions.add(auth_session_id)

            # Return success with auth cookie
            response = {'success': True}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Set-Cookie', f'auth_session={auth_session_id}; Path=/; HttpOnly')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            # Return error
            response = {'success': False, 'error': 'Invalid password'}
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

    def handle_control(self):
        """Handle control commands using the action system."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

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
        
        action_name = data.get('action')
        
        # Map old action names to new action system names
        action_map = {
            'next': 'navigate_next',
            'previous': 'navigate_previous',
            'toggle_pause': 'toggle_pause',
            'toggle_repeat': 'toggle_repeat',
            'toggle_shuffle': 'toggle_shuffle',
            'increase_speed': 'increase_speed',
            'decrease_speed': 'decrease_speed',
            'toggle_fullscreen': 'toggle_fullscreen'
        }
        
        # Get the mapped action name
        mapped_action = action_map.get(action_name, action_name)
        
        # Get the action from registry
        action = action_registry.get(mapped_action)
        
        if action and action.can_execute('web'):
            # Execute the action
            try:
                result = action.execute(session, **data.get('params', {}))
                result['success'] = True
            except Exception as e:
                result = {'success': False, 'error': str(e)}
        else:
            result = {'success': False, 'error': f'Unknown or unavailable action: {action_name}'}
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
    
    def serve_actions(self):
        """Serve list of available actions."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

        actions = []
        for action in action_registry.list_actions('web'):
            actions.append({
                'name': action.name,
                'description': action.description,
                'context': action.context.value
            })
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'actions': actions}).encode())
    
    def serve_hotkeys(self):
        """Serve hotkey mappings."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

        session_id, session = self._require_session()
        if session is None:
            # Create temporary hotkey manager just for info
            hotkey_manager = HotkeyManager(self.web_slideshow.config, 'web')
        else:
            hotkey_manager = session.hotkey_manager if hasattr(session, 'hotkey_manager') else HotkeyManager(self.web_slideshow.config, 'web')
        
        mappings = hotkey_manager.get_all_mappings()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'hotkeys': mappings}).encode())
    
    def serve_gestures(self):
        """Serve gesture mappings."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

        session_id, session = self._require_session()
        if session is None:
            # Create temporary gesture manager just for info
            gesture_manager = GestureManager(self.web_slideshow.config, 'web')
        else:
            gesture_manager = session.gesture_manager if hasattr(session, 'gesture_manager') else GestureManager(self.web_slideshow.config, 'web')
        
        mappings = gesture_manager.get_all_mappings()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'gestures': mappings}).encode())
    
    def handle_execute_action(self):
        """Execute an action by name."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

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
        
        action_name = data.get('action')
        params = data.get('params', {})
        
        action = action_registry.get(action_name)
        if action and action.can_execute('web'):
            try:
                result = action.execute(session, **params)
                result['success'] = True
            except Exception as e:
                result = {'success': False, 'error': str(e)}
        else:
            result = {'success': False, 'error': f'Action not found or not available: {action_name}'}
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
    
    def handle_gesture(self):
        """Handle gesture events."""
        if not self._check_authentication():
            self.send_error(401, "Unauthorized")
            return

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
        
        event_type = data.get('event_type')
        touches = data.get('touches', [])
        
        # Get or create gesture manager for session
        if not hasattr(session, 'gesture_manager'):
            session.gesture_manager = GestureManager(self.web_slideshow.config, 'web')
        
        result = session.gesture_manager.handle_touch_event(
            event_type, touches, session
        )
        
        if result is None:
            result = {'success': False, 'error': 'No gesture detected'}
        else:
            result['success'] = True
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


class WebSlideshow:
    """Web-based slideshow server."""

    def __init__(self, image_paths: List[Path], config: Dict[str, Any], port: int = 8000, password: Optional[str] = None):
        """
        Initialize web slideshow server.

        Args:
            image_paths: List of image paths to serve
            config: Configuration dictionary
            port: Port to run server on
            password: Optional password for web authentication
        """
        self.image_paths = image_paths
        self.original_image_paths = image_paths.copy()
        self.config = config if isinstance(config, ConfigManager) else ConfigManager()
        if isinstance(config, dict):
            # If we got a dict, update the config manager with it
            for key, value in config.items():
                self.config.set(f'slideshow.{key}', value)
        self.port = port if port else self.config.get('web.port', 8000)
        self.password = password  # Optional password for authentication
        self.sessions: Dict[str, SlideshowContext] = {}  # slideshow_session_id -> SlideshowContext
        self.authenticated_sessions: set = set()  # Set of authenticated auth_session_ids
        
        # Initialize action system components
        self._initialize_action_system()

        # Apply shuffle to the main list if requested
        if self.config.get('slideshow.shuffle', False):
            random.shuffle(self.image_paths)

        # Create handler with reference to this slideshow
        self.handler = lambda *args, **kwargs: WebSlideshowHandler(
            *args, web_slideshow=self, **kwargs
        )
    
    def _initialize_action_system(self):
        """Initialize action system components."""
        # Register external tools if configured
        external_tools = self.config.get('external_tools.base_name', 'tool')
        if external_tools:
            from pathlib import Path
            tool_manager = ExternalToolManager(external_tools, Path.cwd())
            tool_manager.register_tool_actions(action_registry)
        
        # Create action history
        history = ActionHistory(self.config.get('file_operations.max_undo_history', 50))
        action_registry.register(UndoAction(history))
        action_registry.register(RedoAction(history))
        
        # Initialize trash manager if enabled
        if self.config.get('file_operations.enable_trash', True) and self.image_paths:
            trash_dir = self.config.get('file_operations.trash_dir', '.trash')
            base_path = self.image_paths[0].parent
            self.trash_manager = TrashManager(base_path, trash_dir)
        else:
            self.trash_manager = None

    def create_session(self, session_id: str):
        """Create a new session for a client."""
        # Each session gets its own context
        session = SlideshowContext(
            image_paths=self.image_paths,  # Share the same image list
            speed=self.config.get('slideshow.speed', 3.0),
            repeat=self.config.get('slideshow.repeat', False),
            fit_mode=self.config.get('slideshow.fit_mode', 'shrink'),
            status_format=self.config.get('slideshow.status_format'),
            always_on_top=self.config.get('slideshow.always_on_top', False),
            shuffle=False,  # prevent mutation of shared image list
            paused=self.config.get('slideshow.paused_on_start', False)
        )
        session.current_index = 0  # Each client starts at image 0
        # Set current_image to None as we don't load images in web mode
        session.current_image = None
        # Per-session order (list of indices into self.image_paths)
        n = len(self.image_paths)
        session.image_order = list(range(n))
        if self.config.get('slideshow.shuffle', False):
            # Each session gets a fresh shuffle using the global random state
            # The global random module maintains good entropy across calls
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