cmake_minimum_required(VERSION 3.20)
project(rrepl_cpp_examples LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(rrepl_client
  examples/rrepl_client.cpp
)

if(WIN32)
  target_link_libraries(rrepl_client PRIVATE ws2_32)
endif()
