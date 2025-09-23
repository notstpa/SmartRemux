@echo off
setlocal enabledelayedexpansion
echo Building REMUX UI executable...
echo.

rem Check if Python is available
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python and ensure it's accessible from command line.
    pause
    exit /b 1
)

rem Check if required files exist
if not exist "video_remuxer_gui.py" (
    echo ERROR: video_remuxer_gui.py not found in current directory.
    pause
    exit /b 1
)

if not exist "ffmpeg.exe" (
    echo WARNING: ffmpeg.exe not found in current directory.
    echo The application will be built without ffmpeg support.
    set "HAS_FFMPEG=0"
) else (
    set "HAS_FFMPEG=1"
)

if not exist "ffprobe.exe" (
    echo WARNING: ffprobe.exe not found in current directory.
    echo The application will be built without ffprobe support.
    set "HAS_FFPROBE=0"
) else (
    set "HAS_FFPROBE=1"
)


rem Install PyInstaller if not already installed
py -m pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    py -m pip install pyinstaller
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

rem Clean up old files
if exist "Remuxer V2.0.exe" del "Remuxer V2.0.exe"
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

rem Build the executable
echo Building executable...
set "PYINSTALLER_CMD=py -m PyInstaller --onefile --windowed --icon "ICOtrans.ico" --add-data "ICOtrans.ico;." --name "Remuxer V2.0" video_remuxer_gui.py"

if %HAS_FFMPEG%==1 (
    set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --add-data "ffmpeg.exe;.""
)

if %HAS_FFPROBE%==1 (
    set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --add-data "ffprobe.exe;.""
)

!PYINSTALLER_CMD!

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

rem Clean up build folder (keep dist folder with executable)
if exist "build" rmdir /s /q "build"

if exist "dist\Remuxer V2.0.exe" (
    echo.
    echo SUCCESS: Remuxer V2.0.exe created in dist folder!
    for %%A in ("dist\Remuxer V2.0.exe") do echo Size: %%~zA bytes
    echo.
    echo You can find your executable at: dist\Remuxer V2.0.exe
) else (
    echo ERROR: Executable not found!
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
pause
endlocal