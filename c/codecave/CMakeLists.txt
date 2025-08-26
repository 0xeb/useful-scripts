cmake_minimum_required(VERSION 3.20)
project(cave C)

add_executable(cave cave.c)

# For MSVC, force the .codecave section to be mapped as RWX.
if (NOT MSVC)
  message(FATAL_ERROR "This project is only supported on MSVC.")
endif()

target_link_options(cave PRIVATE "/SECTION:.codecave,RWE")
