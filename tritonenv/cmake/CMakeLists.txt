cmake_minimum_required(VERSION 3.12)

project(triton_example)

add_executable(triton_example main.cpp)
set_property(TARGET triton_example PROPERTY CXX_STANDARD 17)
target_link_libraries(triton_example $ENV{TRITON_LIB})
target_include_directories(triton_example PUBLIC $ENV{TRITON_INCLUDES})
