# SmartRemux v2.2.1

![Stpa Remuxer Screenshot](https://i.imgur.com/qSW0mps.png)

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
1. Clone the repo and install dependencies.
   ```shell
   pip install -r requirements.txt
   ```
2. Download `ffmpeg.exe` and `ffprobe.exe` from FFmpeg Download.
   - **Note:** The app will not function unless `ffmpeg.exe` and `ffprobe.exe` are either placed in the root directory or added to your system's PATH.
3. Run `build_app.bat`.
4. The app will be in the `dist` folder.
