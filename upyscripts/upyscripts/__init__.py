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

# Export commonly used modules
from . import applydiff
from . import asm_emit
from . import file_upload
from . import html_entities
from . import jsontree
from . import markdown_render
from . import mdcomdec
from . import parse_vcf
from . import pdf3img
from . import preprocess
from . import pyast
from . import src_to_llm_context

__all__ = [
    'applydiff',
    'asm_emit',
    'file_upload',
    'html_entities',
    'jsontree',
    'markdown_render',
    'mdcomdec',
    'parse_vcf',
    'pdf3img',
    'preprocess',
    'pyast',
    'src_to_llm_context',
]