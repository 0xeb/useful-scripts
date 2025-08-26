#include <stdio.h>
#include <string.h>

#pragma section(".codecave", read, execute)
__declspec(allocate(".codecave")) char code[1024 * 1024 * 2];

int main(void) 
{
	memcpy(code, "\x90\x90\x90\x90\x90\x90\x90\xC3", 8);

    printf("Code cave is located at: %p\n", (void*)code);

    void (*func)(void) = (void (*)(void))code;
    func();

    return 0;
}
