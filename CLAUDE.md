# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a collection of utility scripts and tools, primarily in Python and C. The repository contains standalone tools for various development tasks including binary patching, markdown processing, DLL analysis, and code evaluation.

## Installation and Setup

### Python Scripts
The Python scripts are installable as a package:
```bash
pip install -e ./python
```

This installs the following command-line tools:
- `ApplyDiff` - Apply binary patch DIF files
- `asm_emit` - Convert binary to Visual C++ __asm __emit statements
- `html_entities` - Escape HTML entities
- `pyast` - Analyze Python AST (functions, classes, imports)
- `mdcomdec` - Decompose/recompose Markdown files
- `parse_vcf` - Parse VCF contact files
- `jsontree` - Display JSON structure as tree
- `markdown_render` - Render Markdown to HTML on localhost

### Python Libraries (useful_libs)
The `python/useful_libs/` package provides reusable Python libraries:
```bash
pip install -e ./python/useful_libs
```

### C Projects
The C projects use CMake and are Windows/MSVC-specific:
- **codecave**: Requires MSVC, demonstrates code cave techniques
- **shellcode_loader**: Shellcode loading demonstration

Build with:
```bash
cmake -B build
cmake --build build
```

## Project Structure

- `/python/` - Main Python scripts and utilities
  - `useful_libs/` - Reusable Python library modules with tests
  - `dll2proj/` - DLL to Visual Studio project converter
  - `eval_cpp/` - C++ expression evaluator
- `/c/` - C language projects (Windows/MSVC specific)
- `/batch/` - Windows batch scripts
- `/tritonenv/` - Triton DBA environment setup for Windows

## Testing

Python tests are located in `/python/useful_libs/tests/` and can be run with:
```bash
cd python/useful_libs
python -m pytest tests/
```

To run a single test file:
```bash
python -m pytest tests/test_find_latest.py
python -m pytest tests/test_mdparser.py
```

## Key Development Notes

- The C projects are Windows/MSVC-only and involve low-level system programming
- Python scripts are standalone CLI tools installed via setuptools entry points
- The repository mixes utility scripts with experimental/educational code
- The `useful_libs` package uses type hints and has `.pyi` stub files for type checking