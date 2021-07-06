# asm_emit.py

This script is used to convert a binary file into a series of `__asm __emit` statements that can be compiled with Visual C++ / x86

# ApplyDiff.py

A simple script to apply binary patch DIF information file.
Usually, a DIF file has this format:

```
Title of this DIF file

file.bin
0000000000002B54: B0 EB
0000000000002C76: 01 17
```

Basically, seaks to `2B54` and patchs the new byte value `EB` (overriding the `B0`).
