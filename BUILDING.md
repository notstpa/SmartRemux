# Building SmartRemux

SmartRemux keeps the app source in the repository root and groups packaging files under `packaging/`:

- `packaging/pyinstaller/`: PyInstaller spec files
- `packaging/installer/`: Inno Setup script
- `packaging/scripts/`: local build scripts
- `main.py`: main application entry point

## Prerequisites

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

If you want the Full build or installer package, place these files in the repository root:

- `ffmpeg.exe`
- `ffprobe.exe`

Install PyInstaller if it is not already available:

```powershell
pip install pyinstaller
```

For installer builds, install Inno Setup.

## Main Build Entry Point

Run:

```powershell
packaging\scripts\BUILD_MENU.bat
```

The script changes into the repository root before building, so it can be launched from anywhere.

## Outputs

- `dist/`: temporary PyInstaller output
- `releases/`: renamed release artifacts
- `installer_output/`: temporary Inno Setup output

`dist/`, `releases/`, and `installer_output/` are generated folders and should not be committed.
