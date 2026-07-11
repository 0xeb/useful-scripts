import subprocess
import sys


def run_preprocess(*args):
    return subprocess.run(
        [sys.executable, "-m", "upyscripts.preprocess", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_preprocess_cli_writes_literal_input_to_stdout(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("hello\n", encoding="utf-8")

    result = run_preprocess(source)

    assert result.returncode == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""


def test_preprocess_cli_writes_output_file_and_expands_variables(tmp_path):
    source = tmp_path / "input.txt"
    output = tmp_path / "output.txt"
    source.write_text("Hello $NAME$\n", encoding="utf-8")

    result = run_preprocess(source, "-D", "NAME=Codex", "-o", output)

    assert result.returncode == 0
    assert result.stdout == ""
    assert output.read_text(encoding="utf-8") == "Hello Codex\n"


def test_preprocess_cli_reports_missing_input(tmp_path):
    result = run_preprocess(tmp_path / "missing.txt")

    assert result.returncode != 0
    assert "FileNotFoundError" in result.stderr
