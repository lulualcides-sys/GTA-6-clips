# Third-party distribution notices — GTA VI Clips Windows app

**GTA VI Clips** desktop packager uses these third-party components:

- **FFmpeg and ffprobe**: bundled as separate unmodified CLI executables. FFmpeg's applicable license can be LGPL or GPL, depending on build flags and binary distribution. See https://ffmpeg.org/legal.html, https://ffmpeg.org/download.html and the binary supplier for exact version, licenses and corresponding source.
- **pywebview**: Python/native WebView wrapper, distributed as package dependencies. Project: https://github.com/r0x0r/pywebview. Check installed package license.
- **PyInstaller**: used to freeze the Windows desktop distribution. Project: https://pyinstaller.org.
- **Microsoft Edge WebView2 Runtime**: provided by Microsoft and **not** redistributed in this portable ZIP. Runtime license and requirements: https://developer.microsoft.com/microsoft-edge/webview2/.

Redistribution of FFmpeg binaries must comply with the license **of the exact compiled build**, including applicable notices and corresponding source availability. An unsigned executable does not provide proof of safe content.

Do not copy footage, music or streamer likeness into builds, docs or GitHub artifacts without authorization. The CI test uses generated synthetic media only.