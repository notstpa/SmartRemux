@echo off
title SmartRemux Build Menu
color 0A

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..\..") do set ROOT_DIR=%%~fI
pushd "%ROOT_DIR%"

REM ========================================
REM Version file management
REM ========================================
set VERSION_FILE=build_version.txt

REM Read or create version file
if exist "%VERSION_FILE%" (
    set /p APP_VERSION=<"%VERSION_FILE%"
) else (
    set APP_VERSION=1.0.0
    echo 1.0.0>"%VERSION_FILE%"
)

REM ========================================
REM Main menu
REM ========================================
:menu
cls
echo ========================================
echo   SmartRemux Build Menu
echo   Last Built Version: %APP_VERSION%
echo ========================================
echo.
echo   1. Build Lite EXE
echo   2. Build App EXE
echo   3. Build Installer
echo   4. Build All Three
echo   5. Clean Build Folders
echo   6. Exit
echo.
echo ========================================
set /p choice="Enter your choice (1-6): "

if "%choice%"=="1" goto build_lite
if "%choice%"=="2" goto build_app
if "%choice%"=="3" goto build_installer
if "%choice%"=="4" goto build_all
if "%choice%"=="5" goto clean_folders
if "%choice%"=="6" goto exit_script
echo Invalid choice! Please try again.
timeout /t 2 >nul
goto menu

REM ========================================
REM Prompt for version (shared by build targets)
REM ========================================
:prompt_version
echo.
set /p BUILD_VERSION="Enter version [last: %APP_VERSION%]: "
if "%BUILD_VERSION%"=="" set BUILD_VERSION=%APP_VERSION%
exit /b 0

REM ========================================
REM Build Lite EXE only
REM ========================================
:build_lite
cls
echo ========================================
echo   Build Lite EXE
echo ========================================
echo.
call :prompt_version

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
echo [3/4] Building Lite version...
pyinstaller packaging\pyinstaller\SmartRemux.spec --clean

if errorlevel 1 (
    echo Build failed!
    pause
    goto menu
)
echo Lite version built!

echo.
echo [4/4] Creating release package...
if not exist releases mkdir releases
copy "dist\SmartRemux.exe" "releases\SmartRemux.v%BUILD_VERSION%-Lite.exe" >nul

echo.
echo Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
echo Cleanup complete!

REM Update version file after successful build
echo %BUILD_VERSION%>"%VERSION_FILE%"
set APP_VERSION=%BUILD_VERSION%

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Output: releases\SmartRemux.v%BUILD_VERSION%-Lite.exe
echo.
set /p open_releases="Open releases folder? (Y/N): "
if /i "%open_releases%"=="Y" start "" "releases"
pause
goto menu

REM ========================================
REM Build App EXE (Full version with FFmpeg)
REM ========================================
:build_app
cls
echo ========================================
echo   Build App EXE
echo ========================================
echo.
call :prompt_version

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
echo [3/4] Building Full version (with FFmpeg)...
pyinstaller packaging\pyinstaller\SmartRemux_Full.spec --clean

if errorlevel 1 (
    echo Build failed!
    pause
    goto menu
)
echo Full version built!

echo.
echo [4/4] Creating release package...
if not exist releases mkdir releases
copy "dist\SmartRemux.exe" "releases\SmartRemux.v%BUILD_VERSION%.exe" >nul

echo.
echo Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
echo Cleanup complete!

REM Update version file after successful build
echo %BUILD_VERSION%>"%VERSION_FILE%"
set APP_VERSION=%BUILD_VERSION%

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Output: releases\SmartRemux.v%BUILD_VERSION%.exe
echo.
set /p open_releases="Open releases folder? (Y/N): "
if /i "%open_releases%"=="Y" start "" "releases"
pause
goto menu

REM ========================================
REM Build Installer Only
REM ========================================
:build_installer
cls
echo ========================================
echo   Build Installer
echo ========================================
echo.
call :prompt_version

echo [1/5] Checking if dist\SmartRemux.exe exists...
if not exist "dist\SmartRemux.exe" (
    echo dist\SmartRemux.exe not found. Attempting Full build now...
    if exist build rmdir /s /q build 2>nul
    if exist dist rmdir /s /q dist 2>nul
    pyinstaller packaging\pyinstaller\SmartRemux_Full.spec --clean
    if errorlevel 1 (
        echo ERROR: Full build failed during installer creation.
        pause
        goto menu
    )
    if not exist "dist\SmartRemux.exe" (
        echo ERROR: dist\SmartRemux.exe still missing after Full build.
        pause
        goto menu
    )
)
echo Found dist\SmartRemux.exe

echo.
echo [2/5] Checking Inno Setup...
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
echo [3/5] Creating installer...

REM Update installer version
powershell -Command "(Get-Content 'packaging\\installer\\installer.iss') -replace '#define MyAppVersion \".*\"', '#define MyAppVersion \"%BUILD_VERSION%\"' | Set-Content 'packaging\\installer\\installer.iss'"

if not exist installer_output mkdir installer_output
"%ISCC_PATH%" "packaging\installer\installer.iss"

if errorlevel 1 (
    echo Installer creation failed!
    pause
    goto menu
)

REM Move to releases folder and rename
if not exist releases mkdir releases
move "installer_output\SmartRemux_Setup_v%BUILD_VERSION%.exe" "releases\SmartRemux.v%BUILD_VERSION%-Installer.exe" >nul 2>nul

echo.
echo [4/5] Creating release packages...
if not exist releases mkdir releases
copy "dist\SmartRemux.exe" "releases\SmartRemux.v%BUILD_VERSION%.exe" >nul
echo Release packages created!

echo.
echo [5/5] Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
if exist installer_output rmdir /s /q installer_output 2>nul
echo Cleanup complete!

REM Update version file after successful build
echo %BUILD_VERSION%>"%VERSION_FILE%"
set APP_VERSION=%BUILD_VERSION%

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Outputs:
echo   - releases\SmartRemux.v%BUILD_VERSION%.exe
echo   - releases\SmartRemux.v%BUILD_VERSION%-Installer.exe
echo.
set /p open_releases="Open releases folder? (Y/N): "
if /i "%open_releases%"=="Y" start "" "releases"
pause
goto menu

REM ========================================
REM Build All Three (Lite + App + Installer)
REM ========================================
:build_all
cls
echo ========================================
echo   Build All Three
echo ========================================
echo.
call :prompt_version

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
echo [4/6] Building Lite version...
pyinstaller packaging\pyinstaller\SmartRemux.spec --clean

if errorlevel 1 (
    echo Lite build failed!
    pause
    goto menu
)
echo Lite version built!

copy "dist\SmartRemux.exe" "releases\SmartRemux.v%BUILD_VERSION%-Lite.exe" >nul
echo Lite EXE created!

echo.
echo [5/6] Building Full version (with FFmpeg)...
pyinstaller packaging\pyinstaller\SmartRemux_Full.spec --clean

if errorlevel 1 (
    echo Full build failed!
    pause
    goto menu
)
echo Full version built!

copy "dist\SmartRemux.exe" "releases\SmartRemux.v%BUILD_VERSION%.exe" >nul
echo Full EXE created!

echo.
echo [6/6] Creating installer...

REM Check Inno Setup
set ISCC_PATH=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe" set ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 5\ISCC.exe" set ISCC_PATH=%ProgramFiles%\Inno Setup 5\ISCC.exe

if "%ISCC_PATH%"=="" (
    echo WARNING: Inno Setup not found - Skipping installer
) else (
    echo Inno Setup found!

    REM Update installer version
    powershell -Command "(Get-Content 'packaging\\installer\\installer.iss') -replace '#define MyAppVersion \".*\"', '#define MyAppVersion \"%BUILD_VERSION%\"' | Set-Content 'packaging\\installer\\installer.iss'"

    if not exist installer_output mkdir installer_output
    "%ISCC_PATH%" "packaging\installer\installer.iss"

    if errorlevel 1 (
        echo WARNING: Installer creation failed
    ) else (
        move "installer_output\SmartRemux_Setup_v%BUILD_VERSION%.exe" "releases\SmartRemux.v%BUILD_VERSION%-Installer.exe" >nul 2>nul
        echo Installer created!
    )
)

echo.
echo Cleaning up temporary folders...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul
if exist installer_output rmdir /s /q installer_output 2>nul
echo Cleanup complete!

REM Update version file after successful build
echo %BUILD_VERSION%>"%VERSION_FILE%"
set APP_VERSION=%BUILD_VERSION%

echo.
echo ========================================
echo   BUILD COMPLETE!
echo ========================================
echo.
echo Output files in releases\:
if exist "releases\SmartRemux.v%BUILD_VERSION%-Lite.exe" (
    echo   1. SmartRemux.v%BUILD_VERSION%-Lite.exe
)
if exist "releases\SmartRemux.v%BUILD_VERSION%.exe" (
    echo   2. SmartRemux.v%BUILD_VERSION%.exe
)
if exist "releases\SmartRemux.v%BUILD_VERSION%-Installer.exe" (
    echo   3. SmartRemux.v%BUILD_VERSION%-Installer.exe
)
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
REM Exit
REM ========================================
:exit_script
cls
echo Thanks for using SmartRemux Build Menu!
timeout /t 1 >nul
popd
exit
