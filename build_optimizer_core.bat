@echo off
setlocal
cd /d "%~dp0"

if exist build_core\CMakeCache.txt (
    echo Removing previous CMake generator cache...
    rmdir /s /q build_core
)
if not exist build_core mkdir build_core
cmake -S . -B build_core -G "Visual Studio 17 2022" -A x64
if errorlevel 1 exit /b 1
cmake --build build_core --config Release
if errorlevel 1 exit /b 1

copy /y build_core\Release\optimizer_core.dll optimizer_core.dll >nul
echo Built optimizer_core.dll
endlocal
