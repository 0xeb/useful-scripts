
# dll2proj

dll2proj converts a DLL file into a Visual Studio project (via a CMake generator) by extracting all exported symbols and generating function stubs with dummy signatures and implementations. This tool is especially useful when you have a third-party DLL but no corresponding LIB file: it allows you to generate a static import library so you can link against the DLL in your own projects. dll2proj is also helpful when your DLL needs to reference a third-party DLL from places where LoadLibrary is not allowed, such as inside DllMain or TLS callbacks. By generating a mock project with function stubs for all exports, you can build a compatible LIB file and develop or test code that depends on the original DLL's interface, even if the DLL itself is not present at build time.

## Usage

`dll2proj` takes two arguments: the path to the DLL file and the output directory for the mock project. It parses all the exported symbols, then create a complete Visual Studio project with a header file containing the function stubs and a source file with the dummy implementation.

```
usage: dll2proj.py [-h] -d DLL_FILE -p PROJECT

Generates a mock C++ DLL project based on DLL exports.

options:
  -h, --help            show this help message and exit
  -d DLL, --dll DLL     Path to the DLL file.
  -p PROJECT, --project PROJECT
                        Output directory for the mock project.
```

After successfully running the script, you will find a Visual Studio project in the specified output directory to be used as a starting point for writing another DLL that will be compatible with the original one.

In the output directory, run the `prep-cmake.bat` script to generate the Visual Studio project files.

After building the project, you will have a header file and a library file that can be used to link against the original DLL from your other projects.
Feel free to clean up the header file and keep at least one symbol that will be used to link/refer to the original DLL.
Please refer to 'main.cpp' for an example of how to use the generated library.
