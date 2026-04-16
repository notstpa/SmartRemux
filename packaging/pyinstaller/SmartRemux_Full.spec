# -*- mode: python ; coding: utf-8 -*-
# SmartRemux.spec - Full version with FFmpeg bundled
from pathlib import Path

ROOT_DIR = Path.cwd()

block_cipher = None

a = Analysis(
    [str(ROOT_DIR / 'main.py')],
    pathex=[str(ROOT_DIR)],
    binaries=[
        (str(ROOT_DIR / 'ffmpeg.exe'), '.'),  # Bundle ffmpeg.exe
        (str(ROOT_DIR / 'ffprobe.exe'), '.'), # Bundle ffprobe.exe
    ],
    datas=[
        (str(ROOT_DIR / 'ICOtrans.ico'), '.'),  # Include icon file
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SmartRemux',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False for GUI application (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT_DIR / 'ICOtrans.ico'),  # Application icon
    manifest=str(ROOT_DIR / 'app.manifest'),  # Include the manifest file to fix drag and drop
)
