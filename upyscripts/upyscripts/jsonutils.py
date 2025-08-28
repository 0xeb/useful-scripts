#!/usr/bin/env python3
import json
import sys
import argparse
from typing import Any, Optional, TextIO

def print_tree(node: Any, prefix: str = '/', max_depth: Optional[int] = None, current_depth: int = 0) -> None:
    if max_depth is not None and current_depth >= max_depth:
        return
    
    if isinstance(node, dict):
        for k, v in node.items():
            print(f"{prefix}{k}/")
            print_tree(v, prefix + k + '/', max_depth, current_depth + 1)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            print(f"{prefix}[{i}]/")
            print_tree(item, prefix + f'[{i}]/', max_depth, current_depth + 1)

def tree_mode(data: Any, args: argparse.Namespace) -> None:
    print_tree(data, max_depth=args.max_depth)

def beautify_mode(data: Any, args: argparse.Namespace, output_file: Optional[TextIO] = None) -> None:
    output = json.dumps(data, 
                        indent=args.indent, 
                        sort_keys=args.sort_keys,
                        ensure_ascii=False)
    
    if output_file:
        output_file.write(output)
        output_file.write('\n')
    else:
        print(output)

def minify_mode(data: Any, args: argparse.Namespace, output_file: Optional[TextIO] = None) -> None:
    output = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    
    if output_file:
        output_file.write(output)
        output_file.write('\n')
    else:
        print(output)

def validate_mode(data: Any, args: argparse.Namespace) -> None:
    print("Valid JSON")
    if args.verbose:
        stats = get_json_stats(data)
        print(f"Statistics:")
        print(f"  Type: {stats['type']}")
        print(f"  Size: {stats['size']}")
        if stats['type'] == 'object':
            print(f"  Keys: {stats['keys']}")
        print(f"  Depth: {stats['depth']}")

def query_mode(data: Any, args: argparse.Namespace) -> None:
    path_parts = args.path.split('.')
    current = data
    
    try:
        for part in path_parts:
            if part.startswith('[') and part.endswith(']'):
                # Array index
                index = int(part[1:-1])
                current = current[index]
            elif isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                raise KeyError(f"Cannot access '{part}' on {type(current).__name__}")
        
        if isinstance(current, (dict, list)):
            print(json.dumps(current, indent=2, ensure_ascii=False))
        else:
            print(current)
    except (KeyError, IndexError, ValueError) as e:
        print(f"Error: Path '{args.path}' not found - {e}", file=sys.stderr)
        sys.exit(1)

def get_json_stats(data: Any, depth: int = 0) -> dict:
    stats = {'type': type(data).__name__, 'depth': depth}
    
    if isinstance(data, dict):
        stats['type'] = 'object'
        stats['size'] = len(data)
        stats['keys'] = list(data.keys())
        max_depth = depth
        for value in data.values():
            child_stats = get_json_stats(value, depth + 1)
            max_depth = max(max_depth, child_stats['depth'])
        stats['depth'] = max_depth
    elif isinstance(data, list):
        stats['type'] = 'array'
        stats['size'] = len(data)
        max_depth = depth
        for item in data:
            child_stats = get_json_stats(item, depth + 1)
            max_depth = max(max_depth, child_stats['depth'])
        stats['depth'] = max_depth
    else:
        stats['size'] = 1
        
    return stats

def load_json(source: TextIO) -> Any:
    try:
        return json.load(source)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading JSON: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description='JSON utility tool for various JSON operations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s data.json --tree              # Display JSON structure as tree
  %(prog)s data.json --beautify          # Pretty-print JSON
  %(prog)s data.json --minify            # Compact JSON
  %(prog)s data.json --validate          # Validate JSON
  %(prog)s data.json --query users.0.name # Query specific path
  cat data.json | %(prog)s --beautify    # Read from stdin
        """
    )
    
    # Input source
    parser.add_argument('json_file', nargs='?', type=str, 
                       help='Path to JSON file (omit to read from stdin)')
    
    # Operation modes (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--tree', action='store_true', default=False,
                           help='Display JSON structure as tree (default if no mode specified)')
    mode_group.add_argument('--beautify', '--format', action='store_true',
                           help='Pretty-print JSON with indentation')
    mode_group.add_argument('--minify', '--compact', action='store_true',
                           help='Minify JSON (remove unnecessary whitespace)')
    mode_group.add_argument('--validate', action='store_true',
                           help='Validate JSON and show statistics')
    mode_group.add_argument('--query', type=str, metavar='PATH',
                           help='Query JSON using dot notation (e.g., "users.0.name")')
    
    # Options for beautify mode
    parser.add_argument('--indent', type=int, default=2, metavar='N',
                       help='Indentation spaces for beautify mode (default: 2)')
    parser.add_argument('--sort-keys', action='store_true',
                       help='Sort object keys alphabetically')
    
    # Options for tree mode
    parser.add_argument('--max-depth', type=int, metavar='N',
                       help='Maximum depth for tree display')
    
    # Output options
    parser.add_argument('-o', '--output', type=str, metavar='FILE',
                       help='Output file (default: stdout)')
    
    # Validation options
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output for validate mode')
    
    args = parser.parse_args()
    
    # Load JSON data
    if args.json_file:
        try:
            with open(args.json_file, 'r', encoding='utf-8') as f:
                data = load_json(f)
        except FileNotFoundError:
            print(f"Error: File '{args.json_file}' not found", file=sys.stderr)
            sys.exit(1)
        except PermissionError:
            print(f"Error: Permission denied reading '{args.json_file}'", file=sys.stderr)
            sys.exit(1)
    else:
        # Read from stdin
        if sys.stdin.isatty():
            print("Error: No input provided. Provide a file or pipe JSON to stdin.", file=sys.stderr)
            sys.exit(1)
        data = load_json(sys.stdin)
    
    # Open output file if specified
    output_file = None
    if args.output:
        try:
            output_file = open(args.output, 'w', encoding='utf-8')
        except (PermissionError, OSError) as e:
            print(f"Error: Cannot open output file '{args.output}': {e}", file=sys.stderr)
            sys.exit(1)
    
    try:
        # Execute the selected mode
        if args.beautify:
            beautify_mode(data, args, output_file)
        elif args.minify:
            minify_mode(data, args, output_file)
        elif args.validate:
            validate_mode(data, args)
        elif args.query:
            args.path = args.query  # Store query path for query_mode
            query_mode(data, args)
        else:
            # Default to tree mode
            tree_mode(data, args)
    finally:
        if output_file:
            output_file.close()

if __name__ == "__main__":
    main()