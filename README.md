# SmartRemux v3.0.0

![Stpa Remuxer Screenshot](https://i.imgur.com/0cjFdRk.png)

[Download Here](https://github.com/notstpa/stpa-remuxer/releases)
# Features 
- **Lossless Remuxing**: Convert containers without re-encoding.
- **VFR Fix**: Remuxes while keeping your footage CFR for editing software.
- **Flexible Output**: MP4 or MOV formats.
- **File Management**: Move, keep, or delete originals post-remux.
- **Custom Settings**: Control audio streams,timestamps, and more.
- **Parallel Processing**: Faster scans with multiple cores.
- **Real-time Progress & Logs**: Track progress and log details.

![Stpa Remuxer Screenshot](https://i.imgur.com/WCnPlPu.png)
# Versions

SmartRemux
- **Included:** App + FFmpeg (ffmpeg.exe & ffprobe.exe)
- **File Size:** Larger because FFmpeg is built in

SmartRemux-Lite
- **Included:** App only (no FFmpeg)
- **Best For:** Users who already have FFmpeg installed
- **File Size:** Small

SmartRemux-Installer
- **Included:** Installer that sets up SmartRemux with FFmpeg
- **Best For:** Users who want an easy, guided installation
- **File Size:** Largest due to full installer + FFmpeg

# Build from Source
See [BUILDING.md](BUILDING.md) for full build instructions.

Quick start:
```shell
pip install -r requirements.txt
packaging\scripts\BUILD_MENU.bat
```
