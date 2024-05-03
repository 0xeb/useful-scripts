"""
eval_cpp (c) Elias Bachaalany.
"""
import json
import os
import subprocess
import sys
import time
import argparse

def load_cpp_template(template_path):
    with open(template_path, 'r') as file:
        return file.read()

def write_and_compile(expressions, titles, template_path):
    cpp_template = load_cpp_template(template_path)
    expressions_string = ', '.join(expressions)  # Convert list of expressions to a single string
    cpp_code = cpp_template.replace('<<expr>>', expressions_string) \
                           .replace('<<exprs_text>>', ', '.join([json.dumps(s) for s in expressions])) \
                           .replace('<<exprs_titles>>', ', '.join([json.dumps(s) for s in titles]))

    with open('eval_cpp.cpp', 'w') as file:
        file.write(cpp_code)

    just_initialized = False
    if not os.path.exists('build'):
        os.makedirs('build')
        just_initialized = True
    os.chdir('build')

    try:
        if just_initialized:
            subprocess.run(['cmake', '..'], check=True)
        subprocess.run(['cmake', '--build', '.'], check=True)
        output = subprocess.run(['./debug/eval_cpp'], capture_output=True, text=True)
        return output.stdout
    except subprocess.CalledProcessError as e:
        print("Compilation or execution failed.")
        return None
    finally:
        os.chdir('..')

def read_expressions(expr_file_path: str):
    expressions = []
    titles = []
    current_expression = []
    current_vars = {}
    capture = False  # Flag to determine whether to capture lines as part of an expression

    def flush_expression():
        nonlocal current_expression, current_vars
        expr_str = '\n'.join(current_expression)        
        # Replace all variables in the expression with their values
        for var_name, value in current_vars.items():
            expr_str = expr_str.replace(f'${var_name}', value)
        current_expression = []
        current_vars = {}
        return expr_str

    with open(expr_file_path, 'r') as file:
        for line in file:
            oline = line
            if not (line := line.strip()):
                continue
            if line.startswith(';') or line.startswith('//'):
                continue
            # New expression
            if line.startswith('#'):  # Any line that starts with '#' might be a header
                if current_expression and capture:
                    # Join all parts of the current expression into a single string and add it to the list
                    expressions.append(flush_expression())

                # Check if this header line should trigger capturing the next lines as part of an expression
                if capture := line.startswith('# *'):
                    titles.append(line[3:].strip())
            # Variables
            elif line.startswith('$'):
                # parse lines as such: $var_name=value
                var_name, value = line[1:].split('=')
                current_vars[var_name.strip()] = value.strip()
            # Capturing
            elif capture:
                current_expression.append(oline.rstrip())

    # Add the last expression if the file ended but there was an expression being captured
    if current_expression and capture:
        expressions.append(flush_expression())

    return (expressions, titles)

def monitor_mode(expr_file_path, template_path):
    last_mtime = None
    while True:
        try:
            mtime = os.path.getmtime(expr_file_path)
            if last_mtime is None or mtime > last_mtime:
                last_mtime = mtime
                expressions, titles = read_expressions(expr_file_path)
                if expressions:
                    if result := write_and_compile(expressions, titles, template_path):
                        print(result)
                    else:
                        print("No output due to compilation failure.")
            time.sleep(2) # Wait...

        except FileNotFoundError:
            print(f"{expr_file_path} not found, waiting for it to be created...")
            break

        except KeyboardInterrupt:
            print("\nExiting monitor mode.")
            break

def interactive_mode(template_path):
    iexpr = 0
    brk = False
    try:
        while True:
            print("Enter the expression (Ctrl-C/Ctrl-Z to finish):")
            input_lines = []
            while True:
                try:
                    line = input()
                    if not line:
                        break
                    input_lines.append(line)
                except EOFError:
                    brk = True
                    break
            if brk:
                break

            expression = ''.join(line.strip() for line in input_lines if line.strip())
            iexpr += 1
            if not expression:
                print(f"Expression {iexpr} is empty. Skipping...")
                continue

            if result := write_and_compile([expression], [f'Expression {iexpr}'], template_path):
                print(result)
    except KeyboardInterrupt:
        print("\nExiting interactive mode.")

def main():
    parser = argparse.ArgumentParser(description='Expression Evaluator')
    parser.add_argument('-i', '--interactive', action='store_true', help='Run in interactive mode', default=False)
    parser.add_argument('-t', '--templ', default='eval_cpp.templ.cpp', help='Path to the C++ template file')
    parser.add_argument('-e', '--expr', default='eval_cpp.md', help='Path to the expression file for monitoring')
    args = parser.parse_args()

    # Validate files existance
    if not os.path.exists(args.templ):
        print(f"Template file {args.templ} does not exist.")
        return 1

    if not args.interactive and not os.path.exists(args.expr):
        print(f"Expression file {args.expr} does not exist.")
        return 1

    if args.interactive:
        interactive_mode(args.templ)
    else:
        monitor_mode(args.expr, args.templ)

if __name__ == '__main__':
    main()
