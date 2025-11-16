@echo off
title SmartRemux Build Menu
color 0A

REM Set default version if not already set
if not defined APP_VERSION (
    set APP_VERSION=2.2.0
)

:menu
cls
echo ========================================
echo   SmartRemux Build Menu
echo   Current Version: %APP_VERSION%
echo ========================================
echo.
echo Choose what to build:
echo.
echo   1. Build All 3 Versions (Full + Lite + Installer)
echo   2. Build Full Version Only (with FFmpeg)
echo   3. Build Lite Version Only (without FFmpeg)
echo   4. Build Installer Only
echo   5. Clean Build Folders
echo   6. Change Version Number
echo   7. Exit
echo.
echo ========================================
set /p choice="Enter your choice (1-7): "

if "%choice%"=="1" goto build_all
if "%choice%"=="2" goto build_full
if "%choice%"=="3" goto build_lite
if "%choice%"=="4" goto installer_only
if "%choice%"=="5" goto clean_folders
if "%choice%"=="6" goto change_version
if "%choice%"=="7" goto exit_script
echo Invalid choice! Please try again.
timeout /t 2 >nul
goto menu

REM ========================================
REM Build All - Everything
REM ========================================
:build_all
cls
echo ========================================
echo   Build All 3 Versions
echo ========================================
echo.

echo [1/6] Checking PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not installed! Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller!
        pause
        goto menu
    )
)
echo PyInstaller found!

echo.
echo [2/6] Cleaning previous builds...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
if exist releases rmdir /s /q releases 2>nul
echo Cleaned!

echo.
echo [3/6] Creating release packages folder...
mkdir releases 2>nul

echo.
echo [4/6] Building Full version (with FFmpeg bundled)...
if not exist "ffmpeg.exe" (
    echo WARNING: ffmpeg.exe not found in current directory!
    echo Skipping Full version build.
    echo.
    goto skip_full_build
)
if not exist "ffprobe.exe" (
    echo WARNING: ffprobe.exe not found in current directory!
    echo Skipping Full version build.
    echo.
    goto skip_full_build
)

pyinstaller SmartRemux_Full.spec --clean

if errorlevel 1 (
    echo Full version build failed!
    goto skip_full_build
)

copy "dist\SmartRemux.exe" "releases\SmartRemux.v%APP_VERSION%.exe" >nul
echo Full version created!

:skip_full_build
echo.
echo [5/6] Building Lite version (without FFmpeg)...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul

pyinstaller SmartRemux.spec --clean

if errorlevel 1 (
    echo Lite version build failed!
) else (
    copy "dist\SmartRemux.exe" "releases\SmartRemux.v%APP_VERSION%-Lite.exe" >nul
    echo Lite version created!
)

echo.
echo [5/6] Checking for Inno Setup...
set ISCC_PATH=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe" set ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 5\ISCC.exe" set ISCC_PATH=%ProgramFiles%\Inno Setup 5\ISCC.exe

if "%ISCC_PATH%"=="" (
    echo WARNING: Inno Setup not found - Skipping installer
) else (
    echo Inno Setup found!
    echo.
    echo [6/6] Creating installer...
    
    REM Update installer version
    powershell -Command "(Get-Content 'installer.iss') -replace '#define MyAppVersion \".*\"', '#define MyAppVersion \"%APP_VERSION%\"' | Set-Content 'installer.iss'"
    
    if not exist installer_output mkdir installer_output
    "%ISCC_PATH%" "installer.iss" >nul
    
    if errorlevel 1 (
        echo WARNING: Installer creation failed
    ) else (
        REM Move installer to releases folder and rename
        move "installer_output\SmartRemux_Setup_v%APP_VERSION%.exe" "releases\SmartRemux.v%APP_VERSION%-Installer.exe" >nul 2>nul
        echo Installer created!
    )
)

echo.
echo [7/7] Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
if exist installer_output rmdir /s /q installer_output 2>nul
echo Cleanup complete!

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Output files in releases\:
if exist "releases\SmartRemux.v%APP_VERSION%.exe" (
    echo   1. SmartRemux.v%APP_VERSION%.exe (Full - FFmpeg bundled)
)
if exist "releases\SmartRemux.v%APP_VERSION%-Lite.exe" (
    echo   2. SmartRemux.v%APP_VERSION%-Lite.exe (Lite - requires FFmpeg)
)
if exist "releases\SmartRemux.v%APP_VERSION%-Installer.exe" (
    echo   3. SmartRemux.v%APP_VERSION%-Installer.exe (Installer)
)
echo.
set /p open_releases="Open releases folder? (Y/N): "
if /i "%open_releases%"=="Y" start "" "releases"
pause
goto menu

REM ========================================
REM Build Full Version Only
REM ========================================
:build_full
cls
echo ========================================
echo   Build Full Version (with FFmpeg)
echo ========================================
echo.

echo [1/4] Checking PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not installed! Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller!
        pause
        goto menu
    )
)
echo PyInstaller found!

echo.
echo [2/4] Cleaning previous builds...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
echo Cleaned!

echo.
echo [3/4] Building Full version with FFmpeg bundled...
if not exist "ffmpeg.exe" (
    echo ERROR: ffmpeg.exe not found in current directory!
    echo Please place ffmpeg.exe and ffprobe.exe in the project folder.
    pause
    goto menu
)
if not exist "ffprobe.exe" (
    echo ERROR: ffprobe.exe not found in current directory!
    echo Please place ffmpeg.exe and ffprobe.exe in the project folder.
    pause
    goto menu
)

pyinstaller SmartRemux_Full.spec --clean

if errorlevel 1 (
    echo Build failed!
    pause
    goto menu
)
echo Application built!

echo.
echo [4/4] Creating Full version...
if not exist releases mkdir releases
copy "dist\SmartRemux.exe" "releases\SmartRemux.v%APP_VERSION%.exe" >nul

echo.
echo [5/5] Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
echo Cleanup complete!

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Output: releases\SmartRemux.v%APP_VERSION%.exe
echo Note: FFmpeg and FFprobe are bundled inside the exe.
echo.
set /p open_releases="Open releases folder? (Y/N): "
if /i "%open_releases%"=="Y" start "" "releases"
pause
goto menu

REM ========================================
REM Build Lite Version Only
REM ========================================
:build_lite
cls
echo ========================================
echo   Build Lite Version (without FFmpeg)
echo ========================================
echo.

echo [1/4] Checking PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not installed! Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller!
        pause
        goto menu
    )
)
echo PyInstaller found!

echo.
echo [2/4] Cleaning previous builds...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
echo Cleaned!

echo.
echo [3/4] Building application...
pyinstaller SmartRemux.spec --clean

if errorlevel 1 (
    echo Build failed!
    pause
    goto menu
)
echo Application built!

echo.
echo [4/4] Creating Lite version...
if not exist releases mkdir releases
copy "dist\SmartRemux.exe" "releases\SmartRemux.v%APP_VERSION%-Lite.exe" >nul

echo.
echo [5/5] Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
echo Cleanup complete!

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Output: releases\SmartRemux.v%APP_VERSION%-Lite.exe
echo Note: This version requires FFmpeg to be installed on the system.
echo.
set /p open_releases="Open releases folder? (Y/N): "
if /i "%open_releases%"=="Y" start "" "releases"
pause
goto menu

REM ========================================
REM Installer Only - Create installer
REM ========================================
:installer_only
cls
echo ========================================
echo   Create Installer
echo ========================================
echo.

echo [1/3] Checking if dist\SmartRemux.exe exists...
if not exist "dist\SmartRemux.exe" (
    echo ERROR: dist\SmartRemux.exe not found!
    echo Please build the application first (Option 1, 2, or 3)
    pause
    goto menu
)
echo Found dist\SmartRemux.exe

echo.
echo [2/3] Checking Inno Setup...
set ISCC_PATH=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe" set ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 5\ISCC.exe" set ISCC_PATH=%ProgramFiles%\Inno Setup 5\ISCC.exe

if "%ISCC_PATH%"=="" (
    echo ERROR: Inno Setup not found!
    echo Download from: https://jrsoftware.org/isdl.php
    pause
    goto menu
)
echo Inno Setup found!

echo.
echo [3/3] Creating installer...

REM Update installer version
powershell -Command "(Get-Content 'installer.iss') -replace '#define MyAppVersion \".*\"', '#define MyAppVersion \"%APP_VERSION%\"' | Set-Content 'installer.iss'"

if not exist installer_output mkdir installer_output
"%ISCC_PATH%" "installer.iss"

if errorlevel 1 (
    echo Installer creation failed!
    pause
    goto menu
)

REM Move to releases folder and rename
if not exist releases mkdir releases
move "installer_output\SmartRemux_Setup_v%APP_VERSION%.exe" "releases\SmartRemux.v%APP_VERSION%-Installer.exe" >nul 2>nul

echo.
echo [4/4] Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
if exist installer_output rmdir /s /q installer_output 2>nul
echo Cleanup complete!

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Output: releases\SmartRemux.v%APP_VERSION%-Installer.exe
echo.
set /p open_releases="Open releases folder? (Y/N): "
if /i "%open_releases%"=="Y" start "" "releases"
pause
goto menu

REM ========================================
REM Clean Build Folders
REM ========================================
:clean_folders
cls
echo ========================================
echo   Clean Build Folders
echo ========================================
echo.
echo This will delete:
echo   - build\
echo   - dist\
echo   - releases\
echo   - installer_output\
echo   - __pycache__\
echo.
set /p confirm="Are you sure? (Y/N): "
if /i not "%confirm%"=="Y" goto menu

echo.
echo Cleaning...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
if exist releases rmdir /s /q releases 2>nul
if exist installer_output rmdir /s /q installer_output 2>nul
if exist __pycache__ rmdir /s /q __pycache__ 2>nul

echo.
echo All build folders cleaned!
echo.
pause
goto menu

REM ========================================
REM Change Version Number
REM ========================================
:change_version
cls
echo ========================================
echo   Change Version Number
echo ========================================
echo.
echo Current version: %APP_VERSION%
echo.
set /p NEW_VERSION="Enter new version number (e.g., 2.3): "

if "%NEW_VERSION%"=="" (
    echo No version entered. Keeping current version.
    timeout /t 2 >nul
    goto menu
)

REM Update version in memory
set APP_VERSION=%NEW_VERSION%

REM Update version in installer.iss file
powershell -Command "(Get-Content 'installer.iss') -replace '#define MyAppVersion \".*\"', '#define MyAppVersion \"%NEW_VERSION%\"' | Set-Content 'installer.iss'"

echo.
echo Version updated to: %APP_VERSION%
echo.
echo The version has been updated in:
echo   - Build menu (this session)
echo   - installer.iss (for installer builds)
echo.
echo Note: You may also want to update the version in video_remuxer_gui.py
echo       Line 69: self.setWindowTitle("SmartRemux v%APP_VERSION%")
echo.
pause
goto menu

REM ========================================
REM Exit
REM ========================================
:exit_script
cls
echo Thanks for using SmartRemux Build Menu!
timeout /t 1 >nul
exit
