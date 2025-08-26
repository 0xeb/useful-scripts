#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

// Define a function pointer type for our shellcode.
typedef void (*shellcode_func_t)(void);

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Usage: %s <shellcode file>\n", argv[0]);
        return 1;
    }

    // Open the shellcode file in binary mode.
    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        perror("fopen");
        return 1;
    }

    // Determine the file size.
    fseek(f, 0, SEEK_END);
    long filesize = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (filesize <= 0) {
        printf("Empty file or error determining file size.\n");
        fclose(f);
        return 1;
    }

    // Allocate a buffer and read the shellcode.
    unsigned char *sc_buffer = (unsigned char*)malloc(filesize);
    if (!sc_buffer) {
        perror("malloc");
        fclose(f);
        return 1;
    }

    if (fread(sc_buffer, 1, filesize, f) != filesize) {
        printf("Error reading shellcode file.\n");
        free(sc_buffer);
        fclose(f);
        return 1;
    }
    fclose(f);

    // Allocate executable memory (R/W/X) for the shellcode.
    void *exec_mem = VirtualAlloc(NULL, filesize, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!exec_mem) {
        printf("VirtualAlloc failed: Error %lu\n", GetLastError());
        free(sc_buffer);
        return 1;
    }

    // Copy the shellcode into the allocated memory.
    memcpy(exec_mem, sc_buffer, filesize);
    free(sc_buffer);

    // Call DebugBreak() so you can attach a debugger if needed.
    DebugBreak();

    // Jump to the shellcode.
    shellcode_func_t shellcode = (shellcode_func_t)exec_mem;
    shellcode();

    return 0;
}
