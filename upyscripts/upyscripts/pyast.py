"""
Analyze Python AST - Extract functions, classes, imports from Python source files
"""

import ast
import argparse
import json

def get_global_functions(tree):
    return [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]

def get_global_variables(tree):
    return [node.targets[0].id for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)]

def get_global_classes(tree):
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef)]

def get_imports(tree):
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module if node.module else ''
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)
    return imports

def parse_args():
    parser = argparse.ArgumentParser(description="Dump functions, variables, classes, or imports from a Python file.")
    parser.add_argument("filename", help="The Python file to parse")
    parser.add_argument("--dump-functions", action="store_true", help="Dump function names")
    parser.add_argument("--dump-variables", action="store_true", help="Dump variable names")
    parser.add_argument("--dump-classes", action="store_true", help="Dump class names")
    parser.add_argument("--dump-imports", action="store_true", help="Dump import statements")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    return parser.parse_args()

def main():
    args = parse_args()

    with open(args.filename, "r") as file:
        tree = ast.parse(file.read(), filename=args.filename)

    dump_functions = args.dump_functions or not (args.dump_variables or args.dump_classes or args.dump_imports)
    dump_variables = args.dump_variables
    dump_classes = args.dump_classes
    dump_imports = args.dump_imports
    verbose = args.verbose
    output_json = args.json

    if verbose:
        print(f"Parsing file: {args.filename}")

    result = {}

    if dump_functions:
        functions = get_global_functions(tree)
        if output_json:
            result['functions'] = functions
        else:
            if verbose:
                print("\nFunctions:")
            for func in functions:
                print(func)
            if verbose:
                print(f"Total functions: {len(functions)}")

    if dump_variables:
        variables = get_global_variables(tree)
        if output_json:
            result['variables'] = variables
        else:
            if verbose:
                print("\nVariables:")
            for var in variables:
                print(var)
            if verbose:
                print(f"Total variables: {len(variables)}")

    if dump_classes:
        classes = get_global_classes(tree)
        if output_json:
            result['classes'] = classes
        else:
            if verbose:
                print("\nClasses:")
            for cls in classes:
                print(cls)
            if verbose:
                print(f"Total classes: {len(classes)}")

    if dump_imports:
        imports = get_imports(tree)
        if output_json:
            result['imports'] = imports
        else:
            if verbose:
                print("\nImports:")
            for imp in imports:
                print(imp)
            if verbose:
                print(f"Total imports: {len(imports)}")

    if output_json:
        print(json.dumps(result, indent=4))

if __name__ == "__main__":
    main()
