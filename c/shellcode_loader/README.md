A very basic shellcode loader.

You provide a binary file and it VirtualAlloc() it then calls DebugBreak() before it jumps to offset 0.
You can then directly, under a debugger, change the IP to any offset in that shellcode and start single stepping from there.

In x64, most instructions are code segment relative. That means, if you dump a PE image from memory (SizeOfImage size), then you should be able to step into some snippets!

Limitations:
- no imports
- if the shellcode refers anything outside its SizeOfImage boundaries, then you get an exception
