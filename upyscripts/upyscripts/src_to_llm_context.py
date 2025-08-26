"""
Convert codebase to LLM-friendly Markdown format

This tool converts a codebase or file into a structured Markdown file for LLM context or documentation.
It can process single files or entire directories, automatically detecting and handling binary files.

TODO: Replace print statements with logging for better flexibility.
"""

import argparse
import os
import glob
import mimetypes

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

# Maximum file size in bytes (10MB default)
MAX_FILE_SIZE = 10 * 1024 * 1024

def is_binary_file(file_path):
    """Check if a file is binary by examining its mime type and content."""
    mime_type, _ = mimetypes.guess_type(file_path)
    
    # Known text mime types
    if mime_type and mime_type.startswith('text/'):
        return False
    
    # Check first 8192 bytes for null bytes (common in binary files)
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            return b'\x00' in chunk
    except Exception:
        return True

def get_language_from_extension(filename):
    """Return a language string for Markdown code blocks based on file extension."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return EXTENSION_MAP.get(ext, ext if ext else 'plaintext')

def is_safe_path(file_path, base_path):
    """Check if a file path is within the base directory (prevent path traversal)."""
    try:
        real_base = os.path.realpath(base_path)
        real_file = os.path.realpath(file_path)
        return real_file.startswith(real_base)
    except Exception:
        return False

def get_files(base_path, recursive, include_mask):
    """Retrieve files from the specified directory, considering recursion and masks.
    If recursive=True, uses '**' in the glob pattern to match files in all subdirectories.
    """
    matched_files = []
    
    # Filter out empty patterns and default to '*' if no patterns
    include_patterns = []
    if include_mask:
        include_patterns = [p.strip() for p in include_mask.split(';') if p.strip()]
    
    if not include_patterns:
        include_patterns = ['*']

    for pattern in include_patterns:
        # If recursive, use '**' to match all subdirectories
        search_pattern = os.path.join(base_path, '**', pattern) if recursive else os.path.join(base_path, pattern)
        potential_files = glob.glob(search_pattern, recursive=recursive)
        
        # Filter for safe paths and regular files
        for file_path in potential_files:
            if os.path.isfile(file_path) and is_safe_path(file_path, base_path):
                matched_files.append(file_path)

    return sorted(set(matched_files))

def generate_markdown(files, base_path, output_file, skip_binary=True, max_size=MAX_FILE_SIZE):
    """Generate a structured Markdown file with code sections."""
    skipped_files = []
    
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

            # Check file size
            try:
                file_size = os.path.getsize(file_path)
                if file_size > max_size:
                    md_file.write(f"**File skipped:** Too large ({file_size:,} bytes, max: {max_size:,} bytes)\n\n")
                    skipped_files.append((rel_path, "too large"))
                    continue
            except Exception as e:
                md_file.write(f"**Error checking file size:** {e}\n\n")
                continue

            # Check if binary
            if skip_binary and is_binary_file(file_path):
                md_file.write(f"**File skipped:** Binary file detected\n\n")
                skipped_files.append((rel_path, "binary"))
                continue

            language = get_language_from_extension(file_path)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    md_file.write(f"```{language}\n{content}\n```\n\n")
            except UnicodeDecodeError:
                md_file.write(f"**Error reading file:** Unable to decode as UTF-8 text\n\n")
                skipped_files.append((rel_path, "decode error"))
            except Exception as e:
                md_file.write(f"**Error reading file:** {e}\n\n")
                skipped_files.append((rel_path, str(e)))
    
    print(f"Markdown file '{output_file}' generated successfully.")
    
    if skipped_files:
        print(f"\nSkipped {len(skipped_files)} file(s):")
        for file_path, reason in skipped_files[:10]:  # Show first 10
            print(f"  - {file_path}: {reason}")
        if len(skipped_files) > 10:
            print(f"  ... and {len(skipped_files) - 10} more")

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Convert a codebase into a structured Markdown file.")
    parser.add_argument('--file', help="Specify a single file to include.")
    parser.add_argument('--path', help="Specify a directory to scan for files.")
    parser.add_argument('--output', '-o', required=True, help="Output Markdown filename (must end in .md).")
    parser.add_argument('--recursive', '-r', action='store_true', help="Scan directories recursively.")
    parser.add_argument('--imask', help="Include mask for file extensions (e.g., '*.cpp;*.java').")
    parser.add_argument('--include-binary', action='store_true', help="Include binary files (default: skip).")
    parser.add_argument('--max-size', type=int, default=MAX_FILE_SIZE, 
                       help=f"Maximum file size in bytes (default: {MAX_FILE_SIZE:,})")

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

    # Fix base_path handling
    if args.file:
        base_path = os.path.dirname(args.file) or '.'
    else:
        base_path = args.path
    
    # Validate base_path exists
    if not os.path.exists(base_path):
        print(f"Error: Base path '{base_path}' does not exist.")
        exit(1)

    files = [args.file] if args.file else get_files(base_path, args.recursive, args.imask)

    if not files:
        print("No matching files found.")
        exit(1)

    generate_markdown(files, base_path, args.output, 
                     skip_binary=not args.include_binary, 
                     max_size=args.max_size)

if __name__ == "__main__":
    main()