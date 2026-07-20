try:
    import pefile
except ImportError:
    import sys
    print("pefile is not installed. Please run 'pip install pefile' to install it.")
    sys.exit(1)

import datetime
from typing import List, Optional, Tuple
import os
import argparse

GENERATOR_NAME = "dll2proj"
GENERATOR_VERSION = "1.0"

TEMPLATE_FILES = {
    "CMakeLists.templ.cmake": "CMakeLists.txt",
    "main.templ.cpp": "main.cpp",
    "mylib.templ.h": "mylib.h",
    "mylib.templ.cpp": "mylib.cpp",
    "prep-cmake.bat": "prep-cmake.bat"
}

class DLLFile:
    def __init__(self, dll_path):
        self.dll_path = dll_path
        self.dll_name = os.path.basename(dll_path)
        self.pe = pefile.PE(dll_path)
        self.exports = self.extract_exports()
        self.machine = self.extract_machine()


    def extract_machine(self) -> str:
        machine = self.pe.FILE_HEADER.Machine

        if machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_AMD64']:
            return "X64"
        elif machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_I386']:
            return "X86"
        else:
            raise ValueError(f"Unsupported DLL architecture: {machine:#x}")

    def extract_exports(self) -> List[Tuple[str, str]]:
        """Extracts exported symbols as (stub_name, def_line) pairs.

        stub_name is always a valid C identifier used for the generated stubs;
        def_line is the matching EXPORTS entry for the DEF file. Decorated
        names (containing '@') are not valid C identifiers, so they are
        exported under their original name but implemented by a renamed stub
        via the DEF file's 'exportname=internalname' syntax.
        """
        if not hasattr(self.pe, 'DIRECTORY_ENTRY_EXPORT'):
            return []

        exports = []
        for exp in self.pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if exp.name is not None:
                symbol = exp.name.decode('utf-8')
                # Check for mangled names (simplified check)
                if '@' in symbol:
                    stub = f"_{symbol.replace('@', '_at_')}"
                    exports.append((stub, f"{symbol}={stub}"))
                else:
                    exports.append((symbol, symbol))

        return exports


def create_def_file(dll_path, output_dir=".") -> Tuple[str, Optional[DLLFile]]:
    """Creates a DEF file for the given DLL using pefile.

    Returns (def_path, dllfile) on success, or (error_message, None) on failure.
    """
    dll_name = os.path.basename(dll_path)
    def_filename = os.path.splitext(dll_name)[0] + ".def"

    try:
        # Load the DLL using pefile
        dllfile = DLLFile(dll_path)
    except Exception as e:
        return (f'Failed to load DLL: {e!s}', None)

    # Write the DEF file
    def_path = os.path.join(output_dir, def_filename)
    with open(def_path, 'w') as def_file:
        def_file.write(f"LIBRARY {os.path.splitext(dll_name)[0]}\n")
        def_file.write("EXPORTS\n")
        for _stub, def_line in dllfile.exports:
            def_file.write(f"    {def_line}\n")

    return def_path, dllfile

def generate_mock_project(dll_path, output_dir):
    """Generates a mock C++ project based on the exports of the given DLL."""
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Create a DEF file for the DLL
    def_path, dllfile = create_def_file(dll_path, output_dir)
    if not dllfile:
        print(def_path)
        return

    if not dllfile.exports:
        print(f"Warning: '{dllfile.dll_name}' has no named exports; the generated project will have no stubs.")

    stubs = [stub for stub, _def_line in dllfile.exports]

    # Define the expansion dictionary
    expansion_dict = {
        "project_name": os.path.splitext(dllfile.dll_name)[0],
        "dll_name": dllfile.dll_name,
        "dll_machine": dllfile.machine,
        "function_calls": "\n".join([f"    {stub}();" for stub in stubs]),
        # usually goes to 'mylib.h'
        "function_declarations": "\n".join([f"EXPORT_IT({stub});" for stub in stubs]),
        # usually goes to 'mylib.cpp'
        "dummy_function_definitions": "\n".join([f"void {stub}(void) {{ }}" for stub in stubs]),
        #// Generated on {generation_date} with {generator_name} {generator_version}
        "generation_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "generator_name": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "cmake_arch": "x64" if dllfile.machine == "X64" else "Win32"
    }

    # Generate files using the expansion dictionary
    for template_name, output_file in TEMPLATE_FILES.items():
        template_path = os.path.join(os.path.dirname(__file__), template_name)
        with open(template_path, "r") as template, \
             open(os.path.join(output_dir, output_file), "w") as output:

            template_content = template.read()
            for key, value in expansion_dict.items():
                template_content = template_content.replace(f"{{{key}}}", value)
            output.write(template_content)

    # Done
    print(f"Mock project generated in '{output_dir}'. Use 'prep-cmake.bat' to prepare the project for building.")

def main():
    """Main entry point for the dll2proj CLI tool."""
    parser = argparse.ArgumentParser(description="Generates a mock C++ DLL project based on DLL exports.")
    parser.add_argument("-d", "--dll", required=True, help="Path to the DLL file.")
    parser.add_argument("-p", "--project", required=True, help="Output directory for the mock project.")

    args = parser.parse_args()

    generate_mock_project(args.dll, args.project)

if __name__ == "__main__":
    main()
