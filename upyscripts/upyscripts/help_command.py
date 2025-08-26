#!/usr/bin/env python3
"""
UPY Help Command - Discover and list all available upy.* commands
"""

import argparse
import importlib
import importlib.metadata
import subprocess
import sys
import inspect
from typing import List, Tuple


def get_command_description(module_path: str, command_name: str) -> str:
    """
    Try to extract description from a module.
    First tries module docstring, then ArgumentParser description.
    """
    # Special case for upy.help itself
    if command_name == 'upy.help':
        return "Show available upy commands and their descriptions"
    
    try:
        # Try to import the module and get its docstring
        module = importlib.import_module(module_path)
        if module.__doc__:
            # Get first non-empty line of docstring
            lines = [line.strip() for line in module.__doc__.strip().split('\n') if line.strip()]
            if lines:
                return lines[0]
        
        # Try to extract ArgumentParser description from main function
        if hasattr(module, 'main'):
            try:
                source = inspect.getsource(module.main)
                # Look for ArgumentParser description
                if 'ArgumentParser' in source and 'description=' in source:
                    # Simple regex to extract description
                    import re
                    match = re.search(r"description=['\"]([^'\"]+)['\"]", source)
                    if match:
                        return match.group(1)
            except:
                pass
                
    except Exception:
        # If import fails or any error occurs, return generic message
        pass
    
    return "No description available"


def get_available_commands() -> List[Tuple[str, str, str]]:
    """
    Get all available upy.* commands from the installed package.
    Returns a list of tuples: (command_name, module_path, description)
    """
    commands = []
    
    try:
        dist = importlib.metadata.distribution('upyscripts')
        for ep in dist.entry_points:
            if ep.group == 'console_scripts' and ep.name.startswith('upy.'):
                module_path = ep.value.split(':')[0]
                description = get_command_description(module_path, ep.name)
                commands.append((ep.name, module_path, description))
    except importlib.metadata.PackageNotFoundError:
        print("Error: upyscripts package not found. Please install it first.")
        sys.exit(1)
    
    return sorted(commands, key=lambda x: x[0])


def display_commands(verbose: bool = False):
    """Display all available commands in a formatted table."""
    commands = get_available_commands()
    
    if not commands:
        print("No upy commands found.")
        return
    
    print("\nUPY Scripts Collection - Available Commands")
    print("=" * 60)
    print()
    
    # Calculate column widths
    max_cmd_len = max(len(cmd[0]) for cmd in commands)
    
    for cmd_name, module_path, description in commands:
        if verbose:
            print(f"  {cmd_name:<{max_cmd_len}}  {description}")
            print(f"  {'':>{max_cmd_len}}  Module: {module_path}")
            print()
        else:
            print(f"  {cmd_name:<{max_cmd_len}}  {description}")
    
    print("\nFor detailed help on any command, run: <command> --help")
    print("Example: upy.pdf3img --help")
    
    if not verbose:
        print("\nTip: Use 'upy.help --verbose' to see module paths")


def show_command_help(command: str):
    """Show detailed help for a specific command."""
    # Ensure command starts with 'upy.'
    if not command.startswith('upy.'):
        command = f'upy.{command}'
    
    # Check if command exists
    commands = get_available_commands()
    command_names = [cmd[0] for cmd in commands]
    
    if command not in command_names:
        print(f"Error: Command '{command}' not found.")
        print("\nAvailable commands:")
        for cmd_name, _, _ in commands:
            print(f"  {cmd_name}")
        sys.exit(1)
    
    # Run the command with --help
    try:
        print(f"Showing help for: {command}\n")
        subprocess.run([command, '--help'])
    except FileNotFoundError:
        print(f"Error: Could not execute '{command}'. Make sure it's properly installed.")
        sys.exit(1)
    except Exception as e:
        print(f"Error running '{command} --help': {e}")
        sys.exit(1)


def main():
    """Main entry point for upy.help command."""
    parser = argparse.ArgumentParser(
        description='UPY Help - Discover and get help for upy.* commands',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  upy.help              # List all available commands
  upy.help --verbose    # List commands with module paths
  upy.help pdf3img      # Show help for upy.pdf3img
  upy.help upy.pdf3img  # Also works with full command name
        """
    )
    
    parser.add_argument(
        'command',
        nargs='?',
        help='Specific command to get help for (e.g., pdf3img or upy.pdf3img)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show verbose output including module paths'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available commands (default behavior when no command specified)'
    )
    
    args = parser.parse_args()
    
    # If a specific command is requested, show its help
    if args.command:
        show_command_help(args.command)
    else:
        # Otherwise, list all commands
        display_commands(verbose=args.verbose)


if __name__ == '__main__':
    main()