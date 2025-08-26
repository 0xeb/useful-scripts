# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a collection of utility scripts and tools, primarily in Python and C. The repository contains standalone tools for various development tasks including binary patching, markdown processing, DLL analysis, image slideshow viewing, and code evaluation.

## Installation and Setup

### Python Scripts (upyscripts)
The Python scripts are installable as a package from the upyscripts directory:
```bash
pip install -e ./upyscripts
```

This installs the following command-line tools with `upy.` prefix:
- `upy.applydiff` - Apply binary patch DIF files
- `upy.asm_emit` - Convert binary to Visual C++ __asm __emit statements
- `upy.dll2proj` - Convert DLL to Visual Studio project with function stubs (requires pefile)
- `upy.file_upload` - File upload utility
- `upy.html_entities` - Escape HTML entities
- `upy.jsontree` - Display JSON structure as tree
- `upy.markdown_render` - Render Markdown to HTML on localhost
- `upy.mdcomdec` - Decompose/recompose Markdown files
- `upy.parse_vcf` - Parse VCF contact files
- `upy.pdf3img` - Convert PDF pages to images
- `upy.preprocess` - Preprocessing utility
- `upy.pyast` - Analyze Python AST (functions, classes, imports)
- `upy.qslideshow` - Cross-platform image slideshow viewer with web server
- `upy.src2llm` - Convert codebase to LLM-friendly Markdown

### Legacy Tools (python/)
The `python/` directory contains standalone tools not integrated into upyscripts:
- `eval_cpp/` - Evaluate C/C++ expression snippets using CMake compilation

### C Projects
The C projects use CMake and are Windows/MSVC-specific:
- **codecave**: Demonstrates static code cave with RWX attributes
- **shellcode_loader**: Shellcode loading demonstration

Build with:
```bash
cmake -B build
cmake --build build
```

### Triton Environment (Windows)
For building and using the Triton DBA framework:
1. Edit `tritonenv/triton.env` with dependency paths
2. Run `tritonenv.bat init-triton build64` from Triton source
3. For standalone apps: `tritonenv.bat init build64`

## Project Structure

- `/upyscripts/` - Main Python package with installable CLI tools
  - `upyscripts/` - Source code for all Python utilities
  - `upyscripts/lib/` - Reusable library modules (files, markdown)
  - `upyscripts/dll2proj/` - DLL to Visual Studio project converter
  - `upyscripts/qslideshow/` - Image slideshow viewer with PWA web interface
  - `upyscripts/tests/` - Unit tests for library modules
- `/python/` - Legacy standalone Python tools
  - `eval_cpp/` - C++ expression evaluator using CMake
- `/c/` - C language projects (Windows/MSVC specific)
  - `codecave/` - Static code cave demonstration
  - `shellcode_loader/` - Shellcode loading example
- `/batch/` - Windows batch scripts (jsonbeauty.bat)
- `/tritonenv/` - Triton DBA framework environment setup (Windows)

## Common Commands

### Installation
```bash
# Install the upyscripts package (from repository root)
pip install -e ./upyscripts

# Install with development dependencies
pip install -e ./upyscripts[dev]
```

### Testing
```bash
# Run tests from upyscripts directory
cd upyscripts
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_mdparser.py
python -m pytest tests/test_find_latest.py
```

### Development
```bash
# Format code with black (if installed)
black upyscripts/

# Run linting
flake8 upyscripts/

# Type checking
mypy upyscripts/
```

## Code Architecture

### Python Package Structure
The `upyscripts` package uses setuptools with `pyproject.toml` configuration. All CLI tools are defined as console script entry points with the `upy.` prefix. The package follows this architecture:
- Each tool is a standalone module in `upyscripts/` with a `main()` function
- Shared functionality is in `upyscripts/lib/` with proper submodules
- The qslideshow tool has a complex architecture with GUI (tkinter), web server (Flask), and PWA components

### Key Technical Details
- Python dependencies: markdown2, flask, werkzeug, Pillow, PyMuPDF, requests, pefile
- The C projects require Windows/MSVC and use low-level system programming techniques
- The dll2proj tool (now integrated as upy.dll2proj) requires Windows and the pefile library
- The eval_cpp tool generates and compiles C++ code dynamically using CMake
- The qslideshow web interface is a Progressive Web App with offline support
- All Python tools are Python 3.7+ compatible