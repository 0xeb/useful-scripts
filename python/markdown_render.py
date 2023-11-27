# pip install markdown2 pygments

import http.server
import socketserver
import markdown2
import os
import requests
import argparse

# Default port
DEFAULT_PORT = 8000

# CSS to make code blocks wrap text
CSS_STYLES = """
<style>
    pre {
        white-space: pre-wrap;       /* Since CSS 2.1 */
        white-space: -moz-pre-wrap;  /* Mozilla, since 1999 */
        white-space: -pre-wrap;      /* Opera 4-6 */
        white-space: -o-pre-wrap;    /* Opera 7 */
        word-wrap: break-word;       /* Internet Explorer 5.5+ */
    }
</style>
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

def main(use_github, port):
    class MarkdownHTTPHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            file_path = self.path.strip("/")
            if file_path.endswith(".md"):
                if os.path.isfile(file_path):
                    with open(file_path, 'r') as file:
                        markdown_text = file.read()
                        if use_github:
                            html_content = render_markdown_to_html_github(markdown_text)
                        else:
                            html_content = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "code-friendly", "tables", "pygments"])
                        full_html_content = f"{CSS_STYLES}\n{html_content}"

                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(full_html_content.encode())
                else:
                    self.send_error(404, f"File not found: {self.path}")
            else:
                super().do_GET()

    if use_github:
        print("Using GitHub API for rendering")

    with socketserver.TCPServer(("", port), MarkdownHTTPHandler) as httpd:
        print(f"Serving at port {port}")
        httpd.serve_forever()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Markdown Renderer')
    parser.add_argument('-g', '--github', action='store_true', help='Use GitHub API for rendering')
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_PORT, help='Port number to serve on (default: 8080)')
    args = parser.parse_args()

    main(args.github, args.port)