"""
upyscripts - A collection of useful Python utility scripts and tools.

This package provides various command-line utilities for:
- Text processing and templating
- File operations and searching
- Markdown rendering and parsing
- Image and PDF manipulation
- Code analysis and AST parsing
- Web-based tools and services
"""

__version__ = "0.1.0"
__author__ = "Elias Bachaalany"
__email__ = "elias.bachaalany@gmail.com"

# Note: We don't import modules here to avoid circular import issues
# and the RuntimeWarning when running modules with python -m
# The CLI tools are accessible through the console_scripts entry points

__all__ = [
    '__version__',
    '__author__',
    '__email__',
]