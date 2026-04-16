# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

ROOT_DIR = Path.cwd()

# Read the app name from an environment variable, with a fallback default.
app_name = os.environ.get('PYINSTALLER_APP_NAME', 'StpaRemuxer')

datas = [(str(ROOT_DIR / 'ICOtrans.ico'), '.')]
if (ROOT_DIR / 'ffmpeg.exe').exists():
    datas.append((str(ROOT_DIR / 'ffmpeg.exe'), '.'))
if (ROOT_DIR / 'ffprobe.exe').exists():
    datas.append((str(ROOT_DIR / 'ffprobe.exe'), '.'))

a = Analysis(
    [str(ROOT_DIR / 'main.py')],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT_DIR / 'ICOtrans.ico'),
)
