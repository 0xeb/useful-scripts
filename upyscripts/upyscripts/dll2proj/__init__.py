"""
dll2proj - Convert DLL exports to Visual Studio project with function stubs.

This module provides functionality to extract exported symbols from Windows DLL files
and generate complete Visual Studio projects with stub implementations.
"""

from .dll2proj import generate_mock_project, DLLFile, create_def_file

__all__ = ['generate_mock_project', 'DLLFile', 'create_def_file']