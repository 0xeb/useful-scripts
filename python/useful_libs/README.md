# useful_libs

A collection of Python utility modules for file operations and Markdown parsing.

## Features

- **files/find.py**: Functions for finding files and directories.
- **markdown/heading_parser.py**: Utilities for parsing Markdown headings.

## Installation

You can install the package (if published) using pip:

```bash
pip install useful_libs
```

Or use it directly by adding the `useful_libs` directory to your `PYTHONPATH`.

## Usage

Example usage for finding files:

```python
from useful_libs.files.find import find_files

files = find_files('/path/to/search', pattern='*.py')
print(files)
```

Example usage for parsing Markdown headings:

```python
from useful_libs.markdown.heading_parser import parse_headings

with open('README.md') as f:
    content = f.read()
headings = parse_headings(content)
print(headings)
```

## Tests

Unit tests are located in `useful_libs/tests/`. Run them with:

```bash
python -m unittest discover useful_libs/tests
```

## License

See the main repository LICENSE file.
