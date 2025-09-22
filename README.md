# Stpa Remuxer v2.0

A powerful and user-friendly desktop application for remuxing video files, built with **Python** and **Tkinter**. This tool efficiently converts MKV files to MP4 or MOV containers without re-encoding, preserving video and audio quality. It's designed to fix common issues with **Variable Frame Rate (VFR)** videos, making them compatible with video editors like DaVinci Resolve and Adobe Premiere Pro.

### Key Features 🚀
- **Lossless Remuxing**: Change video container formats (e.g., MKV to MP4) without re-encoding, maintaining 100% of the original quality.
- **VFR (Variable Frame Rate) Fix**: Automatically detects and applies a Constant Frame Rate (CFR) to videos, resolving common sync and playback issues in video editing software.
- **Batch Processing**: Remux multiple files at once with a simple and intuitive interface.
- **Flexible Output**: Choose between MP4 (for maximum compatibility) and MOV output formats.
- **Advanced File Management**: Safely move original files to a subfolder, keep them in place, or delete them after a successful remux.
- **Customizable Settings**: Control audio stream inclusion, file validation, timestamp preservation, and more.
- **Parallel Processing**: Uses multiple CPU cores for faster file scanning.
- **Real-time Progress & Logging**: Monitor the progress of individual files and the entire batch, with a detailed log to track all operations.
