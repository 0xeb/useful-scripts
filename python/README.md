# Python Legacy Tools

This directory contains standalone Python tools that are not part of the main `upyscripts` package. These tools have specific use cases and additional dependencies.

## Available Tools

### eval_cpp
An interactive C++ expression evaluator that compiles and runs C++ code snippets using CMake.

**Usage:**
```bash
# Interactive mode
python eval_cpp/eval_cpp.py -i

# Evaluate expressions from file
python eval_cpp/eval_cpp.py -e expressions.md
```

**Features:**
- Interactive REPL for C++ expressions
- Markdown-based expression files
- Selective expression evaluation (active/inactive)
- CMake-based compilation
- Custom template support

[Full documentation](eval_cpp/README.md)

## Requirements

- Python 3.7+
- CMake (for eval_cpp)
- Visual Studio or MSVC compiler

## Note

These tools are maintained separately from the main `upyscripts` package due to their specialized dependencies and platform requirements. For general-purpose Python utilities, see the [upyscripts package](../upyscripts/).