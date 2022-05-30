cmake_minimum_required(VERSION 3.12)

project(triton_example)

add_executable(triton_example main.cpp)
set_property(TARGET triton_example PROPERTY CXX_STANDARD 14)
target_link_libraries(triton_example $ENV{TRITON_LIB})
target_include_directories(triton_example PRIVATE $ENV{TRITON_INCLUDES})
