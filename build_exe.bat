@echo off
setlocal

cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    exit /b 1
)

if not exist optimizer_core.dll (
    echo optimizer_core.dll was not found.
    echo Put the already-built DLL next to this script or build it with build_optimizer_core.bat.
    exit /b 1
)

py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --add-binary "optimizer_core.dll;." ^
    --name AdaptiveRamOptimizer app_gui.py
if errorlevel 1 (
    echo EXE build failed.
    exit /b 1
)

echo Build complete: dist\AdaptiveRamOptimizer.exe
endlocal
