# UPyScripts

A collection of useful Python scripts for various development and file manipulation tasks.

## Installation

```bash
pip install -e .
```

To uninstall:
```bash
pip uninstall upyscripts
```

## Scripts

### asm_emit.py
Converts binary files into Visual C++ compatible `__asm __emit` statements for x86 assembly embedding.

```bash
upy.asm_emit input.bin > output.cpp
upy.asm_emit shellcode.bin --var-name my_shellcode
```

### applydiff.py
Applies binary patch files (DIF format) to target binaries. DIF files specify byte-level modifications with offset and replacement values.

```bash
upy.applydiff patch.dif target.exe
upy.applydiff --backup modifications.dif program.bin
```

Example DIF format:
```
Title of this DIF file

file.bin
0000000000002B54: B0 EB
0000000000002C76: 01 17
```

### dll2proj.py
Generates a Visual Studio project from a DLL file by extracting all exports and creating corresponding function stubs with dummy implementations.

```bash
upy.dll2proj library.dll --output MyProject
upy.dll2proj system32.dll --project-name SystemStubs
```

### eval_cpp.py
Evaluates C/C++ expression snippets by compiling and executing them in a temporary environment.

```bash
upy.eval_cpp "sizeof(int)"
upy.eval_cpp "std::numeric_limits<double>::max()" --std c++11
echo "2 + 2 * 3" | upy.eval_cpp
```

### html_entities.py
Escapes HTML entities in source files for safe HTML embedding.

```bash
upy.html_entities input.html > escaped.html
upy.html_entities raw_content.txt --output safe_content.txt
```

### jsontree.py
Visualizes JSON file structure in a tree format, displaying the hierarchy without values.

```bash
upy.jsontree config.json
upy.jsontree large_dataset.json --max-depth 3
cat data.json | upy.jsontree
```

### markdown_render.py
Renders Markdown files as HTML and serves them on localhost for preview.

```bash
upy.markdown_render README.md
upy.markdown_render docs/manual.md --port 8080
upy.markdown_render --watch document.md
```

### mdcomdec.py
Markdown file decomposer/composer with two modes:
- **Decompose**: Splits a single Markdown file into multiple organized files
- **Compose**: Combines multiple Markdown files from a folder into a single document

```bash
# Decompose a large markdown file
upy.mdcomdec --decompose book.md --output chapters/

# Compose multiple files into one
upy.mdcomdec --compose chapters/ --output book.md
```

### parse_vcf.py
Parses VCF (vCard) files containing multiple contacts and extracts them as individual contact entries.

```bash
upy.parse_vcf contacts.vcf --output individual_contacts/
upy.parse_vcf all_contacts.vcf --format json
```

### pdf3img.py
Bidirectional PDF-Image converter with two modes:
- **Extract**: Extracts unique images from PDFs with automatic deduplication
- **Compile**: Creates PDFs from image collections

```bash
# Extract images from PDF
upy.pdf3img --extract document.pdf --output images/
upy.pdf3img --extract-all *.pdf --dedupe

# Compile images into PDF
upy.pdf3img --compile images/*.jpg --output album.pdf
upy.pdf3img --compile photos/ --layout 2 --quality 85 --output contact_sheet.pdf
```

### preprocess.py
Text preprocessing utility for code and documentation preparation.

```bash
upy.preprocess source.cpp --strip-comments
upy.preprocess document.txt --normalize-whitespace
upy.preprocess *.py --remove-empty-lines
```

### pyast.py
Python AST analyzer that extracts and displays:
- Global functions and their signatures
- Variables and constants
- Class definitions
- Import statements

```bash
upy.pyast script.py
upy.pyast module.py --functions-only
upy.pyast package/*.py --classes --imports
```

### qslideshow.py
Feature-rich cross-platform image slideshow viewer:
- **Format support**: jpg, png, gif, bmp, tiff, webp, ico, svg
- **Navigation**: Keyboard shortcuts (arrows, space, F for fullscreen, R for repeat)
- **Display modes**: Fullscreen, always-on-top, shuffle, repeat

```bash
# Basic slideshow
upy.qslideshow images/

# Recursive with exclusions
upy.qslideshow photos/ -r -x "thumbs,temp"

# Advanced options
upy.qslideshow *.jpg --fullscreen --shuffle --delay 5
upy.qslideshow @playlist.txt --repeat --status "$i/$n - $f"

# Response file example (playlist.txt):
# image1.jpg
# folder/image2.png
# vacation/*.jpg
```

### src_to_llm_context.py
Converts codebases into structured Markdown documents optimized for LLM context:

```bash
# Single file
upy.src_to_llm_context main.py > context.md

# Directory with filters
upy.src_to_llm_context src/ --include "*.py,*.js" --output codebase.md

# Recursive with size limit
upy.src_to_llm_context . -r --max-size 100000 --skip-binary > project_context.md

# Multiple paths
upy.src_to_llm_context src/ tests/ docs/*.md --output full_context.md
```

## License

[Add license information here]

## Contributing

[Add contribution guidelines here]