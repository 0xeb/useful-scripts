# eval_cpp

`eval_cpp` is a streamlined C++ code evaluator designed to process C++ code snippets interactively or from a Markdown-style file containing expressions.

## Usage

To utilize this tool, use the following command-line syntax:

```plaintext
usage: eval_cpp.py [-h] [-i] [-t TEMPL] [--expr EXPR]

Expression Evaluator

options:
  -h, --help            Show this help message and exit.
  -i, --interactive     Run the evaluator in interactive mode.
  -t TEMPL, --templ TEMPL
                        Specify the path to the C++ template file.
  -e EXPR, --expr EXPR  Specify the path to the file containing expressions to evaluate.
```

## Expression File Format

Expressions should be written in a Markdown file as demonstrated below:

```markdown
# * Active Expression

1 + 1

# Inactive Expression

2 + 2

# * Active Expression 2

3 + 3
```

- **Active Expressions:** Begin with a heading marked by a `#` character followed by an asterisk (`*`). These expressions will be evaluated.
- **Inactive Expressions:** Start with a plain heading and will be skipped. 

Expressions are processed in the order they appear in the file, allowing for structured input and selective execution.