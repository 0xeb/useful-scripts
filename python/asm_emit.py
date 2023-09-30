#!/usr/bin/python

import sys, os

# Optional maximum bytes per line
MAX_LINE = 4

def main():
    # Check if the filename exists
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print("asm_emit.py filename.bin [items_perline=%d]" % MAX_LINE)
        sys.exit(1)

    # Read the whole file
    with open(sys.argv[1], 'rb') as f:
        d = f.read()

    # Optionally update the items per line
    if len(sys.argv) > 2:
        MAX_LINE = int(sys.argv[2]) 

    # Emit the lines
    lines = []
    while len(d) > 0:
        p, d = d[0 : MAX_LINE], d[MAX_LINE:]
        lines.append(' '.join(["__asm __emit 0x%02x" % ord(x) for x in p]))

    print(' \\\n'.join(lines))

if __name__ == '__main__':
    main()