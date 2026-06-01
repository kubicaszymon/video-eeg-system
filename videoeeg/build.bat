@echo off
REM ===========================================================================
REM  Portable build script for the NeuroSync VEEG C++/Qt app (MSVC + vcpkg).
REM
REM  Prerequisites (set once, e.g. via `setx`):
REM    QTDIR       -> Qt MSVC kit prefix,  e.g.  C:\Qt\6.9.1\msvc2022_64
REM    VCPKG_ROOT  -> vcpkg clone,         e.g.  C:\vcpkg
REM  Plus Visual Studio 2022/2026 with the "Desktop development with C++" workload.
REM
REM  Usage:   build.bat            (Release, default)
REM           build.bat Debug      (Debug)
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CONFIG=%~1"
if "%CONFIG%"=="" set "CONFIG=Release"

if not defined QTDIR (
  echo [ERROR] QTDIR not set.  Example:  setx QTDIR C:\Qt\6.9.1\msvc2022_64
  exit /b 1
)
if not defined VCPKG_ROOT (
  echo [ERROR] VCPKG_ROOT not set.  Example:  setx VCPKG_ROOT C:\vcpkg
  exit /b 1
)

REM --- Enter the MSVC developer environment (cl.exe, headers, CRT, Ninja) ---
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo [ERROR] vswhere.exe not found - is Visual Studio installed?
  exit /b 1
)
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -prerelease -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
if not defined VSPATH (
  echo [ERROR] No Visual Studio with the C++ toolset found.
  exit /b 1
)
call "%VSPATH%\VC\Auxiliary\Build\vcvars64.bat" || exit /b 1

set "BUILDDIR=out\build\%CONFIG%"

cmake -S . -B "%BUILDDIR%" -G Ninja ^
  -DCMAKE_BUILD_TYPE=%CONFIG% ^
  -DCMAKE_PREFIX_PATH="%QTDIR%" ^
  -DCMAKE_TOOLCHAIN_FILE="%VCPKG_ROOT%/scripts/buildsystems/vcpkg.cmake"
if errorlevel 1 exit /b 1

cmake --build "%BUILDDIR%" --parallel
if errorlevel 1 exit /b 1

echo BUILD_OK (%CONFIG%) -^> %BUILDDIR%
