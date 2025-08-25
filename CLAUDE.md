# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a collection of utility scripts and tools, primarily in Python and C. The repository contains standalone tools for various development tasks including binary patching, markdown processing, DLL analysis, image slideshow viewing, and code evaluation.

## Installation and Setup

### Python Scripts
The Python scripts are installable as a package:
```bash
pip install -e ./python
```

This installs the following command-line tools:
- `ApplyDiff` - Apply binary patch DIF files
- `asm_emit` - Convert binary to Visual C++ __asm __emit statements
- `dll2proj` - Convert DLL to Visual Studio project with function stubs
- `eval_cpp` - Evaluate C/C++ expression snippets
- `file_upload` - File upload utility
- `html_entities` - Escape HTML entities
- `jsontree` - Display JSON structure as tree
- `markdown_render` - Render Markdown to HTML on localhost
- `mdcomdec` - Decompose/recompose Markdown files
- `parse_vcf` - Parse VCF contact files
- `preprocess` - Preprocessing utility
- `pyast` - Analyze Python AST (functions, classes, imports)
- `qslideshow` - Cross-platform image slideshow viewer with web server
- `src_to_llm_context` - Convert codebase to LLM-friendly Markdown

### Python Libraries (useful_libs)
The `python/useful_libs/` package provides reusable Python libraries:
```bash
pip install -e ./python/useful_libs
```

Available modules:
- `useful_libs.files.find` - File finding utilities with type hints
- `useful_libs.markdown.heading_parser` - Markdown heading parsing

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

- `/python/` - Main Python scripts and utilities
  - `useful_libs/` - Reusable Python library modules with tests
  - `dll2proj/` - DLL to Visual Studio project converter
  - `eval_cpp/` - C++ expression evaluator
  - `qslideshow/` - Image slideshow viewer with web interface
- `/c/` - C language projects (Windows/MSVC specific)
- `/batch/` - Windows batch scripts (jsonbeauty.bat)
- `/tritonenv/` - Triton DBA environment setup for Windows

## Testing

### Python useful_libs
Run tests from the `python/useful_libs/` directory:
```bash
python -m pytest tests/
```

## Key Development Notes

- The C projects are Windows/MSVC-only and involve low-level system programming
- Python scripts are standalone CLI tools installed via setuptools entry points
- The `useful_libs` package uses type hints with `.pyi` stub files for type checking
- The qslideshow tool includes a Progressive Web App (PWA) interface in `qslideshow/web/`
- Dependencies: markdown2 for Python scripts, toml for useful_libs