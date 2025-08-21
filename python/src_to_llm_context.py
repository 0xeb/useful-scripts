
#!/usr/bin/env python3
"""
src_to_llm_context.py

Convert a codebase or file into a structured Markdown file for LLM context or documentation.

TODO: Replace print statements with logging for better flexibility.
"""

import argparse
import os
import glob

# Map common extensions to canonical language names for Markdown
EXTENSION_MAP = {
    'py': 'python',
    'cpp': 'cpp',
    'c': 'c',
    'h': 'cpp',
    'hpp': 'cpp',
    'js': 'javascript',
    'ts': 'typescript',
    'java': 'java',
    'md': 'markdown',
    'sh': 'bash',
    'bat': 'batch',
    'json': 'json',
    'html': 'html',
    'css': 'css',
    'xml': 'xml',
    'yml': 'yaml',
    'yaml': 'yaml',
    'txt': 'plaintext',
}

def get_language_from_extension(filename):
    """Return a language string for Markdown code blocks based on file extension."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return EXTENSION_MAP.get(ext, ext if ext else 'plaintext')

def get_files(base_path, recursive, include_mask):
    """Retrieve files from the specified directory, considering recursion and masks.
    If recursive=True, uses '**' in the glob pattern to match files in all subdirectories.
    """
    matched_files = []
    include_patterns = include_mask.split(';') if include_mask else ['*']

    for pattern in include_patterns:
        # If recursive, use '**' to match all subdirectories
        search_pattern = os.path.join(base_path, '**', pattern) if recursive else os.path.join(base_path, pattern)
        matched_files.extend(glob.glob(search_pattern, recursive=recursive))

    return sorted(set(matched_files))

def generate_markdown(files, base_path, output_file):
    """Generate a structured Markdown file with code sections."""
    with open(output_file, 'w', encoding='utf-8') as md_file:
        # General Instructions
        md_file.write("# General Instructions\n\n")
        md_file.write("Please enter your context here.\n\n")
        md_file.write("Please refer to the following code base annotated below.\n\n")
        
        # Project Source Files
        md_file.write("## Project Source Files\n\n")
        md_file.write("The following section contains multiple subsections of all the files in the repo.\n\n")

        for file_path in files:
            rel_path = os.path.relpath(file_path, base_path)
            heading = f"### {rel_path}\n\n"
            md_file.write(heading)

            language = get_language_from_extension(file_path)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    md_file.write(f"```{language}\n{content}\n```\n\n")
            except UnicodeDecodeError:
                md_file.write(f"**Error reading file:** Unicode decode error (not UTF-8).\n\n")
            except Exception as e:
                md_file.write(f"**Error reading file:** {e}\n\n")
    print(f"Markdown file '{output_file}' generated successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a codebase into a structured Markdown file.")
    parser.add_argument('--file', help="Specify a single file to include.")
    parser.add_argument('--path', help="Specify a directory to scan for files.")
    parser.add_argument('--output', '-o', required=True, help="Output Markdown filename (must end in .md).")
    parser.add_argument('--recursive', '-r', action='store_true', help="Scan directories recursively.")
    parser.add_argument('--imask', help="Include mask for file extensions (e.g., '*.cpp;*.java').")

    args = parser.parse_args()

    if not args.file and not args.path:
        print("Error: You must specify either --file or --path.")
        exit(1)

    if not args.output.endswith('.md'):
        print("Error: The output file must have a .md extension.")
        exit(1)

    # Check if output file exists and prompt before overwriting
    if os.path.exists(args.output):
        confirm = input(f"Output file '{args.output}' already exists. Overwrite? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("Aborted by user.")
            exit(0)

    base_path = args.path if args.path else os.path.dirname(args.file)
    files = [args.file] if args.file else get_files(base_path, args.recursive, args.imask)

    if not files:
        print("No matching files found.")
        exit(1)

    generate_markdown(files, base_path, args.output)
