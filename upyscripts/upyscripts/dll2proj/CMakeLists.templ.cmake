#
# Generated on {generation_date} with {generator_name} {generator_version}
#

cmake_minimum_required(VERSION 3.17)
project({project_name})

add_library({project_name} SHARED mylib.cpp mylib.h {project_name}.def)

# Add the DEF file
target_sources({project_name} PRIVATE {project_name}.def)

# Set the include directory
target_include_directories({project_name} PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

# Define the export macro for the header
target_compile_definitions({project_name} PRIVATE MYLIB_EXPORTS)

# Add the test project
add_executable(test main.cpp)

# Link the test project to the mylib library
target_link_libraries(test {project_name})
