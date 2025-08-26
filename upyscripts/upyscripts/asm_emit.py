#!/usr/bin/env python3

import sys, os
import argparse

def main():
    parser = argparse.ArgumentParser(description='Convert binary file to Visual C++ __asm __emit statements')
    parser.add_argument('filename', help='Binary file to convert')
    parser.add_argument('--items-per-line', type=int, default=4, help='Number of bytes per line (default: 4)')
    
    args = parser.parse_args()
    
    # Check if the filename exists
    if not os.path.exists(args.filename):
        print(f"Error: File '{args.filename}' not found")
        sys.exit(1)

    # Read the whole file
    with open(args.filename, 'rb') as f:
        d = f.read()

    # Emit the lines
    lines = []
    max_line = args.items_per_line
    while len(d) > 0:
        p, d = d[0 : max_line], d[max_line:]
        lines.append(' '.join(["__asm __emit 0x%02x" % x for x in p]))

    print(' \\\n'.join(lines))

if __name__ == '__main__':
    main()