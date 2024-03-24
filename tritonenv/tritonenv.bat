@echo off

for /f "delims=" %%a in (%~dp0\triton.env) DO ( 
  set %%a
)

:: Additional expansions
call set TRITON_INCLUDES=%TRITON_INCLUDES%
call set TRITON_LIB=%TRITON_LIB%
call set Z3_LIBRARIES=%Z3_LIBRARIES%
call set Z3_VERSION_HEADER=%Z3_VERSION_HEADER%

if not defined TRITON_ENV_INITED set PATH=%PATH%;%TRITON_LIB_DIR%;%Z3_LIBRARIES_DIR%
if not defined TRITON_ENV_INITED set TRITON_ENV_INITED=1

if "%1"=="init" (
  setlocal enabledelayedexpansion
  if "%2"=="" (set _blddir=build64) else (set _blddir=%2)

  if not exist !_blddir! mkdir !_blddir!
  cd !_blddir!

  cmake .. -A x64 -DBOOST_ROOT="%BOOST_ROOT%" -DPYTHON_INCLUDE_DIRS="%PYTHON_INCLUDE_DIRS%" -DPYTHON_LIBRARIES="%PYTHON_LIBRARIES%" -DZ3_INCLUDE_DIRS="%Z3_INCLUDE_DIRS%" -DZ3_LIBRARIES="%Z3_LIBRARIES%" -DCAPSTONE_INCLUDE_DIR="%CAPSTONE_INCLUDE_DIR%" -DCAPSTONE_LIBRARY="%CAPSTONE_LIBRARY%" -DZ3_INTERFACE=YES -DZ3_VERSION_HEADER=%Z3_VERSION_HEADER% -DPYTHON_BINDINGS=YES -DBUILD_EXAMPLES=YES %3 %4 %5 %6

  endlocal
)

goto :eof
