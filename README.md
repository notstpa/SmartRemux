# Stpa Remuxer v2.0

A Python and Tkinter app for remuxing MKV to MP4/MOV without re-encoding, preserving quality. It fixes VFR issues for editing compatibility with DaVinci Resolve and Adobe Premiere Pro.

![Stpa Remuxer Screenshot](https://i.imgur.com/IPKBSi1.png)

[Download v2.0.0](https://github.com/notstpa/stpa-remuxer/releases/tag/25.09.22)  
Support development: <a href="https://www.buymeacoffee.com/stpa" target="_blank">Buy me a coffee</a>

### Features 🚀
- **Lossless Remuxing**: Convert containers without re-encoding.
- **VFR Fix**: Converts VFR to CFR for editing software.
- **Batch Processing**: Remux multiple files at once.
- **Flexible Output**: MP4 or MOV formats.
- **File Management**: Move, keep, or delete originals post-remux.
- **Custom Settings**: Control audio streams, validation, timestamps.
- **Parallel Processing**: Faster scans with multiple cores.
- **Real-time Progress & Logs**: Track progress and log details.

## Versions 📁

### StpaRemuxer-Lite
- **Included:** Compiled Python app (no FFmpeg binaries)
- **Best For:** Users with FFmpeg installed in path or apps directory.
- **File Size:** Small

### StpaRemuxer
- **Included:** Python app with FFmpeg (ffmpeg.exe & ffprobe.exe)
- **File Size:** Larger due to built in FFmpeg executables

### Build from Source 🧑‍💻
1. Clone the repo and install dependencies from `requirements.txt`.
2. Download `ffmpeg.exe` and `ffprobe.exe` from [FFmpeg Download](https://www.ffmpeg.org/download.html).
   - **Note:** The app will notfunction unless `ffmpeg.exe` and `ffprobe.exe` are either placed in the root directory or added to your system's PATH.
3. Run `build_app.bat`.
4. The app will be in the `dist` folder.
