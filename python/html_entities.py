import html
import argparse
import sys
import os

def escape_html_entities(file_path):
    if not os.path.exists(file_path):
        sys.stderr.write(f"Error: The file {file_path} does not exist.\n")
        sys.exit(1)

    with open(file_path, 'r') as f:
        raw_code = f.read()

    return html.escape(raw_code)

def main():
    parser = argparse.ArgumentParser(description="Escape the entities in the source code file for HTML.")
    parser.add_argument('file', type=str, help="The path to the source file.")

    args = parser.parse_args()

    escaped_code = escape_html_entities(args.file)
    sys.stdout.write(escaped_code)

if __name__ == "__main__":
    main()
