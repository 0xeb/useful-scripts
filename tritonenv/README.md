# Introduction

`tritonenv.bat` is a script to setup all the environment variables needed to build and use [Triton](https://github.com/jonathansalwan/Triton).

# Building Triton

1. Prepare all of the dependencies and build them ([z3](https://github.com/Z3Prover/z3),[capstone (tag: 5.0)](https://github.com/capstone-engine/capstone), [boost](https://github.com/boostorg/boost))
2. Edit [triton.env](triton.env) accordingly or make a copy and edit it in the Triton source folder
3. From Triton's source code directory, run `tritonenv.bat init-triton build64`

This will create the `build64` folder and run's CMake to generate the Visual Studio solution.
Feel free to edit `tritonenv.bat` as well.

# Building standalone apps that use Triton

Create a `CMakeLists.txt` file with the following contents:

```
cmake_minimum_required(VERSION 3.12)

project(triton_example)

add_executable(triton_example main.cpp)
set_property(TARGET triton_example PROPERTY CXX_STANDARD 14)
target_link_libraries(triton_example $ENV{TRITON_LIB})
target_include_directories(triton_example PRIVATE $ENV{TRITON_INCLUDES})
```

Notice the `TRITON_LIB` and `TRITON_INCLUDES` environment variables use. Replace `triton_example` with your project name and source file.

Next, run `tritonenv.bat init build64`. This will set all the proper environment variables, create the build directory and runs CMake automatically. If you don't pass any arguments, then only the environment variables will be set up.
Finally, the `PATH` will now also point to both `libz3.dll` and `triton.dll`.

Check the [cmake](cmake) example.
