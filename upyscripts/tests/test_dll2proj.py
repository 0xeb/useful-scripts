"""
Tests for dll2proj - DLL to mock Visual Studio project converter.
"""

import os
from types import SimpleNamespace

import pytest

import upyscripts.dll2proj
from upyscripts.dll2proj import DLLFile, create_def_file, generate_mock_project
from upyscripts.dll2proj.dll2proj import TEMPLATE_FILES

SAMPLE_DLL = os.path.join(
    os.path.dirname(upyscripts.dll2proj.__file__), "test", "lz4.dll"
)


def fake_dllfile():
    """Builds a DLLFile without invoking pefile, for unit-testing methods."""
    return DLLFile.__new__(DLLFile)


class TestDLLFile:
    def test_sample_dll_loads(self):
        dll = DLLFile(SAMPLE_DLL)
        assert dll.dll_name == "lz4.dll"
        assert dll.machine in ("X64", "X86")
        assert dll.exports

    def test_exports_are_pairs(self):
        dll = DLLFile(SAMPLE_DLL)
        for stub, def_line in dll.exports:
            assert stub
            assert def_line

    def test_plain_symbol(self):
        dll = fake_dllfile()
        dll.pe = SimpleNamespace(
            DIRECTORY_ENTRY_EXPORT=SimpleNamespace(
                symbols=[SimpleNamespace(name=b"LZ4_compress")]
            )
        )
        assert dll.extract_exports() == [("LZ4_compress", "LZ4_compress")]

    def test_decorated_symbol_gets_valid_stub(self):
        dll = fake_dllfile()
        dll.pe = SimpleNamespace(
            DIRECTORY_ENTRY_EXPORT=SimpleNamespace(
                symbols=[SimpleNamespace(name=b"Func@8")]
            )
        )
        assert dll.extract_exports() == [("_Func_at_8", "Func@8=_Func_at_8")]

    def test_no_export_directory(self):
        dll = fake_dllfile()
        dll.pe = SimpleNamespace()
        assert dll.extract_exports() == []

    def test_unsupported_machine_raises(self):
        dll = fake_dllfile()
        dll.pe = SimpleNamespace(FILE_HEADER=SimpleNamespace(Machine=0x1C0))
        with pytest.raises(ValueError, match="Unsupported DLL architecture"):
            dll.extract_machine()


class TestCreateDefFile:
    def test_def_written_to_output_dir(self, tmp_path):
        def_path, dllfile = create_def_file(SAMPLE_DLL, str(tmp_path))
        assert dllfile is not None
        assert os.path.dirname(def_path) == str(tmp_path)
        content = (tmp_path / "lz4.def").read_text()
        assert content.startswith("LIBRARY lz4\nEXPORTS\n")

    def test_bad_dll_returns_error(self, tmp_path):
        bad = tmp_path / "bad.dll"
        bad.write_bytes(b"not a dll")
        message, dllfile = create_def_file(str(bad), str(tmp_path))
        assert dllfile is None
        assert "Failed to load DLL" in message


class TestGenerateMockProject:
    def test_all_files_in_output_dir(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        out = tmp_path / "project"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        generate_mock_project(SAMPLE_DLL, str(out))

        for output_file in TEMPLATE_FILES.values():
            assert (out / output_file).is_file()
        assert (out / "lz4.def").is_file()
        # Nothing (e.g. the .def) may leak into the working directory
        assert not list(cwd.iterdir())

    def test_generated_stubs_are_valid(self, tmp_path):
        out = tmp_path / "project"
        generate_mock_project(SAMPLE_DLL, str(out))

        header = (out / "mylib.h").read_text()
        source = (out / "mylib.cpp").read_text()
        for line in header.splitlines():
            if line.startswith("EXPORT_IT("):
                assert "=" not in line
        for line in source.splitlines():
            if line.startswith("void "):
                assert "=" not in line

        cmake = (out / "CMakeLists.txt").read_text()
        assert "project(lz4)" in cmake
        assert "{" not in cmake.replace("${CMAKE_CURRENT_SOURCE_DIR}", "")
