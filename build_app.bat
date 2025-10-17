@echo off
setlocal enabledelayedexpansion

:: --- Configuration ---
set /p "VERSION=Enter version (e.g., 2.1): "
if not defined VERSION set "VERSION=2.1"

set "APP_NAME_FULL=SmartRemux.v%VERSION%"
set "APP_NAME_LITE=SmartRemux.v%VERSION%-Lite"
set "SPEC_FILE=remuxer.spec"
set "DIST_PATH=dist"
set "BUILD_PATH=build"
set "PYTHON_EXE=C:/Users/stopa/AppData/Local/Programs/Python/Python314/python.exe"

:: --- Pre-build Checks ---
echo Building executables for version %VERSION%...
echo.

rem Check for Python
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not accessible.
    pause
    exit /b 1
)

rem Check for PyInstaller
"%PYTHON_EXE%" -m pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    "%PYTHON_EXE%" -m pip install pyinstaller
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

rem Check for PyQt5
"%PYTHON_EXE%" -m pip show PyQt5 >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyQt5...
    "%PYTHON_EXE%" -m pip install PyQt5
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install PyQt5.
        pause
        exit /b 1
    )
)

:: --- Cleanup ---
echo Cleaning up old build and dist directories...
if exist "%BUILD_PATH%" rmdir /s /q "%BUILD_PATH%"
if exist "%DIST_PATH%" rmdir /s /q "%DIST_PATH%"
echo.

:: =================================================
:: --- Build Full Version (with FFmpeg) ---
:: =================================================
echo Building %APP_NAME_FULL%...

set "PYINSTALLER_APP_NAME=%APP_NAME_FULL%"
"%PYTHON_EXE%" -m PyInstaller %SPEC_FILE% --distpath "%DIST_PATH%" --clean

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed for %APP_NAME_FULL%!
    pause
    exit /b 1
)

echo.
echo SUCCESS: %APP_NAME_FULL% created!
echo.

:: =================================================
:: --- Build Lite Version (without FFmpeg) ---
:: =================================================
echo Building %APP_NAME_LITE%...

rem To build the Lite version, we temporarily hide ffmpeg and ffprobe.
rem The spec file will then automatically exclude them.
if exist "ffmpeg.exe" ren "ffmpeg.exe" "ffmpeg.bak"
if exist "ffprobe.exe" ren "ffprobe.exe" "ffprobe.bak"

set "PYINSTALLER_APP_NAME=%APP_NAME_LITE%"
"%PYTHON_EXE%" -m PyInstaller %SPEC_FILE% --distpath "%DIST_PATH%" --clean

rem Rename the files back immediately after the build.
if exist "ffmpeg.bak" ren "ffmpeg.bak" "ffmpeg.exe"
if exist "ffprobe.bak" ren "ffprobe.bak" "ffprobe.exe"

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed for %APP_NAME_LITE%!
    rem Ensure we rename the files back even if the build fails
    if exist "ffmpeg.bak" ren "ffmpeg.bak" "ffmpeg.exe"
    if exist "ffprobe.bak" ren "ffprobe.bak" "ffprobe.exe"
    pause
    exit /b 1
)

echo.
echo SUCCESS: %APP_NAME_LITE% created!
echo.

:: --- Post-build Cleanup and Consolidation ---
echo Consolidating builds...

rem Move the Lite executable and its dependencies into the main build folder
xcopy "%DIST_PATH%\%APP_NAME_LITE%\*" "%DIST_PATH%\%APP_NAME_FULL%\" /E /I /Y /Q

rem Clean up the now-empty Lite build folder and the main build folder
if exist "%DIST_PATH%\%APP_NAME_LITE%" rmdir /s /q "%DIST_PATH%\%APP_NAME_LITE%"
if exist "%BUILD_PATH%" rmdir /s /q "%BUILD_PATH%"

rem Rename the final output folder to be clean and simple
ren "%DIST_PATH%\%APP_NAME_FULL%" "StpaRemuxer.v%VERSION%"

echo Build completed successfully!
echo Executables are in the '%DIST_PATH%\StpaRemuxer.v%VERSION%' folder.
pause
endlocal