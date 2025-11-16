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
- **Included:** Python app with FFmpeg (ffmpeg.exe & ffprobe.exe)
- **File Size:** Larger due to built in FFmpeg executables

SmartRemux-Lite
- **Included:** Compiled Python app (no FFmpeg binaries)
- **Best For:** Users with FFmpeg installed in path or apps directory.
- **File Size:** Small

# Build from Source
1. Clone the repo and install dependencies.
   ```shell
   pip install -r requirements.txt
   ```
2. Download `ffmpeg.exe` and `ffprobe.exe` from FFmpeg Download.
   - **Note:** The app will not function unless `ffmpeg.exe` and `ffprobe.exe` are either placed in the root directory or added to your system's PATH.
3. Run `build_app.bat`.
4. The app will be in the `dist` folder.
