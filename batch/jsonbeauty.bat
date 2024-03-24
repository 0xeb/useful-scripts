@echo off

REM Check if no arguments are passed
if "%~1"=="" (
    echo Usage: %0 [input_json_file] [output_json_file]
    exit /b
)

REM Check if the input file exists
if not exist "%~1" (
    echo Input file not found: %~1
    exit /b
)

REM Set default output file if not provided
if "%~2"=="" (
    set "output_file=%~dpn1.new.json"
) else (
    set "output_file=%~2"
)

REM Run the Python command
python -m json.tool "%~1" > "%output_file%"
