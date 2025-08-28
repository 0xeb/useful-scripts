# Useful Scripts Collection

A comprehensive collection of utility scripts and tools for various development tasks, including binary patching, markdown processing, DLL analysis, image slideshow viewing, and code evaluation.

## Quick Start

### Install Python Tools

There's a set of Python tools that are polished and offered as tiny command line tools.

The package name is `upyscripts` (which stands for useful Python scripts).

```bash
# Install the upyscripts package with all CLI tools
pip install -e ./upyscripts
```

This installs command-line tools with the `upy.` prefix:
- `upy.applydiff` - Apply binary patch DIF files
- `upy.asm_emit` - Convert binary to Visual C++ __asm __emit statements  
- `upy.dll2proj` - Convert DLL to Visual Studio project with function stubs
- `upy.file_upload` - File upload utility
- `upy.html_entities` - Escape HTML entities
- `upy.jsonutils` - JSON utility tool (beautify, minify, validate, tree view, query)
- `upy.markdown_render` - Render Markdown to HTML on localhost
- `upy.mdcomdec` - Decompose/recompose Markdown files
- `upy.parse_vcf` - Parse VCF contact files
- `upy.pdf3img` - Convert PDF pages to images
- `upy.preprocess` - Preprocessing utility
- `upy.pyast` - Analyze Python AST
- `upy.qslideshow` - Cross-platform image slideshow viewer with web server
- `upy.src2llm` - Convert codebase to LLM-friendly Markdown
- `upy.dlcalc` - Calculate and visualize daylight hours and sunset times for any location

## Repository Structure

- **[upyscripts/](upyscripts/)** - Main Python package with installable CLI tools
- **[python/](python/)** - Legacy standalone Python tools (eval_cpp)
- **[c/](c/)** - C language projects (Windows/MSVC specific)
- **[batch/](batch/)** - Windows batch scripts
- **[tritonenv/](tritonenv/)** - Triton DBA framework environment setup (Windows)

## Documentation

- [Python scripts documentation](python/README.md)
- [Triton DBA environment setup](tritonenv/README.md)

## License

MIT License - see [LICENSE](LICENSE) file for details.