# Copilot Instructions

## Repository Overview

A collection of standalone Python CLI tools (installed as a package called `upyscripts`) plus some legacy C and Python tools. Each CLI tool is a self-contained module with a `main()` function, exposed via console script entry points with the `upy.` prefix.

## Build & Test Commands

```bash
# Install (from repo root)
pip install -e ./upyscripts

# Install with dev dependencies (pytest, playwright, black, flake8, mypy)
pip install -e ./upyscripts[dev]

# Run all tests (from upyscripts/ directory)
cd upyscripts
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_mdparser.py -v

# Run a single test by name
python -m pytest tests/test_qslideshow_actions.py -v -k "test_next_navigation"

# Run backend tests only (skip Playwright browser tests)
python -m pytest tests/test_qslideshow*.py -v --ignore=tests/test_qslideshow_playwright*

# Playwright UI tests require: playwright install chromium
python -m pytest tests/test_qslideshow_playwright*.py -v

# Linting & formatting
black upyscripts/
flake8 upyscripts/
mypy upyscripts/
```

## Architecture

- **Entry points**: All CLI tools are defined in `upyscripts/pyproject.toml` under `[project.scripts]` with the `upy.` prefix (e.g., `upy.jsonutils`, `upy.ghview`). Each maps to a `module:main` function.
- **Tool modules**: Each tool is a standalone `.py` file in `upyscripts/upyscripts/` with a `main()` function that uses `argparse` for CLI argument parsing.
- **Shared libraries**: Reusable code lives in `upyscripts/upyscripts/lib/` (submodules for files and markdown utilities).
- **Complex tools**: `qslideshow/` and `dll2proj/` are sub-packages with their own internal structure. `qslideshow` has GUI (tkinter), web server (Flask), and PWA components.
- **Tests**: Located in `upyscripts/upyscripts/tests/` (unit tests imported by package) and `upyscripts/tests/` (pytest test files). Tests use pytest fixtures and mock platform-specific behavior.

## Key Conventions

- Python 3.7+ compatibility is required.
- New CLI tools must follow the existing pattern: standalone module with `main()` function, registered as a `upy.*` console script entry point in `pyproject.toml`.
- The `__init__.py` at the package root deliberately avoids importing modules to prevent circular imports and RuntimeWarnings.
- C projects under `c/` are Windows/MSVC-specific and use CMake (`cmake -B build && cmake --build build`).
