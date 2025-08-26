cmake_minimum_required(VERSION 3.10)
project(shellcode_loader C)

# Set C standard to C99.
set(CMAKE_C_STANDARD 99)

add_link_options("/DYNAMICBASE:NO")
add_executable(shellcode_loader main.c)
