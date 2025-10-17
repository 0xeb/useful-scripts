# pip install markdown2 pygments

import http.server
import socketserver
import markdown2
import os
import requests
import argparse
import socket
import signal
import sys

# Default port
DEFAULT_PORT = 8000

# HTML header with UTF-8 charset and CSS styles
HTML_HEADER = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    pre {
        white-space: pre-wrap;       /* Since CSS 2.1 */
        white-space: -moz-pre-wrap;  /* Mozilla, since 1999 */
        white-space: -pre-wrap;      /* Opera 4-6 */
        white-space: -o-pre-wrap;    /* Opera 7 */
        word-wrap: break-word;       /* Internet Explorer 5.5+ */
    }
</style>
</head>
<body>
"""

HTML_FOOTER = """
</body>
</html>
"""

def render_markdown_to_html_github(markdown_content):
    # GitHub API URL for rendering Markdown
    url = 'https://api.github.com/markdown'

    # Prepare the data for the API request
    data = {
        'text': markdown_content,
        'mode': 'markdown'  # You can change this to 'gfm' for GitHub-flavored Markdown
    }

    # Make the API request
    response = requests.post(url, json=data)

    # Check for successful response
    if response.status_code == 200:
        return response.text
    else:
        print(f"Error: {response.status_code}")
        return None

def get_local_ip():
    """Get the local IP address of the machine."""
    try:
        # Create a socket to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a remote address (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def serve_markdown(use_github=False, port=None):
    if port is None:
        port = DEFAULT_PORT

    # Signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down server...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    class MarkdownHTTPHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            file_path = self.path.strip("/")
            if file_path.endswith(".md"):
                if os.path.isfile(file_path):
                    with open(file_path, 'r', encoding='utf-8') as file:
                        markdown_text = file.read()
                        if use_github:
                            html_content = render_markdown_to_html_github(markdown_text)
                        else:
                            html_content = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "code-friendly", "tables", "pygments"])
                        full_html_content = f"{HTML_HEADER}{html_content}{HTML_FOOTER}"

                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(full_html_content.encode('utf-8'))
                else:
                    self.send_error(404, f"File not found: {self.path}")
            else:
                super().do_GET()

    if use_github:
        print("Using GitHub API for rendering")

    # Get local IP address
    local_ip = get_local_ip()

    with socketserver.TCPServer(("", port), MarkdownHTTPHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"Serving at port {port}")
        print(f"Local:   http://localhost:{port}")
        print(f"Network: http://{local_ip}:{port}")
        print("Press Ctrl+C to stop the server")
        httpd.serve_forever()

def main():
    parser = argparse.ArgumentParser(description='Markdown Renderer - Serves markdown files as HTML via HTTP')
    parser.add_argument('-g', '--github', action='store_true', help='Use GitHub API for rendering')
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_PORT, help=f'Port number to serve on (default: {DEFAULT_PORT})')
    parser.add_argument('--serve', action='store_true', help='Start the server (default action when no arguments given)')
    
    args = parser.parse_args()
    
    # Start the server
    serve_markdown(args.github, args.port)

if __name__ == "__main__":
    main()