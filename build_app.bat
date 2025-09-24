@echo off
setlocal enabledelayedexpansion

:: --- Configuration ---
set /p "VERSION=Enter version (e.g., 2.1): "
if not defined VERSION set "VERSION=2.1"

set "APP_NAME=Remuxer V%VERSION%"
set "SPEC_FILE=remuxer.spec"
set "DIST_PATH=dist"
set "BUILD_PATH=build"
set "EXECUTABLE_PATH=%DIST_PATH%\%APP_NAME%.exe"

:: Set environment variable for the spec file
set "REMUXER_VERSION=%VERSION%"

:: --- Pre-build Checks ---
echo Building %APP_NAME% executable...
echo.

rem Check for Python
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    pause
    exit /b 1
)

rem Check for PyInstaller
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

:: --- Cleanup ---
echo Cleaning up old build directory...
if exist "%BUILD_PATH%" rmdir /s /q "%BUILD_PATH%"
echo.

:: --- Build ---
echo Building executable from %SPEC_FILE%...
py -m PyInstaller %SPEC_FILE% --distpath "%DIST_PATH%" --clean

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

:: --- Post-build ---
rem Clean up build folder
if exist "%BUILD_PATH%" rmdir /s /q "%BUILD_PATH%"

if exist "%EXECUTABLE_PATH%" (
    echo.
    echo SUCCESS: %EXECUTABLE_PATH% created!
    for %%A in ("%EXECUTABLE_PATH%") do echo Size: %%~zA bytes
    echo.
) else (
    echo ERROR: Executable not found!
    pause
    exit /b 1
)

echo Build completed successfully!
pause
endlocal