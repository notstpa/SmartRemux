# -*- mode: python ; coding: utf-8 -*-
import os

# Read the app name from an environment variable, with a fallback default.
app_name = os.environ.get('PYINSTALLER_APP_NAME', 'StpaRemuxer')

datas = [('ICOtrans.ico', '.')]
if os.path.exists('ffmpeg.exe'):
    datas.append(('ffmpeg.exe', '.'))
if os.path.exists('ffprobe.exe'):
    datas.append(('ffprobe.exe', '.'))

a = Analysis(
    ['video_remuxer_gui.py'],
    pathex=[],
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
    icon='ICOtrans.ico',
)
