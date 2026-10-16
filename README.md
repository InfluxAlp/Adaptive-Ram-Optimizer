# Adaptive RAM Optimizer

A Windows 10/11 desktop application that learns each user's own process habits and safely trims eligible background working sets with Windows APIs.

## For users

Download `AdaptiveRamOptimizer.exe` from GitHub Releases and run it. No installer is required.

Every user starts with a clean, personal data store. Telemetry and the trained Random Forest model are saved locally at:

`%LOCALAPPDATA%\AdaptiveRamOptimizer`

Personal telemetry, databases, and model files are never bundled into the EXE and should not be committed to GitHub.

Windows may deny access to protected or elevated processes. This is expected. The application does not terminate processes and never trims the foreground process.

## Build the EXE

1. Install Python 3.10 or newer on Windows.
2. Install Visual Studio 2022 Build Tools with the Desktop C++ workload and CMake.
3. Run `build_exe.bat` from the project directory.
4. The result is `dist\AdaptiveRamOptimizer.exe`.

Command-line alternative:

```powershell
py -3 -m pip install -r requirements.txt
call build_optimizer_core.bat
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --add-binary "optimizer_core.dll;." ^
    --name AdaptiveRamOptimizer app_gui.py
```

## Event-driven telemetry core

`optimizer_core.dll` listens to `EVENT_SYSTEM_FOREGROUND` with
`SetWinEventHook(WINEVENT_OUTOFCONTEXT)`. It owns a message-pump thread and
does not scan processes or sleep on a timer. `optimizer_core.py` keeps the
callback alive and exposes the `TelemetryData` structure through `ctypes`.
The GUI worker blocks on the callback queue and only reads process/system
metrics after a foreground event. Build the DLL separately with
`build_optimizer_core.bat` when testing the Python bridge.

## GitHub Releases

Upload `dist\AdaptiveRamOptimizer.exe` as an asset in a GitHub Release. The included GitHub Actions workflow also builds a Windows artifact when manually dispatched or when a `v*` tag is pushed.

Do not upload `ml_dataset_telemetry.db`, its WAL/SHM files, or `ram_optimizer_model.pkl`. These files are excluded by `.gitignore` and contain user-specific data.

## Safety

Foreground applications, critical Windows processes, and low-confidence predictions are protected. `Test (10% RAM)` is experimental and aggressive; `Balanced` is recommended for normal use.
