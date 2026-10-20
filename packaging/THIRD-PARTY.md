# Third-party components

FastVideoCropper packages Python, PySide6/Qt, Shiboken, NumPy, PyQtGraph,
psutil, and their native dependencies. Their available distribution license
files are included in this directory, along with Python's license and the
PyInstaller bootloader license and exception. Qt libraries remain dynamically linked.

FFmpeg and FFprobe are separate executables from Gyan Doshi's Windows x64
8.1.2 essentials build, licensed under GPLv3. The distributor's README, license,
download URL, and SHA-256 are included in `ffmpeg/`.

- Distributor, build details and component source references:
  https://www.gyan.dev/ffmpeg/builds/
- FFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/n8.1.2
- Qt source and licensing: https://www.qt.io/licensing/
- PyQtGraph: https://github.com/pyqtgraph/pyqtgraph
- NumPy: https://numpy.org/
- psutil: https://github.com/giampaolo/psutil

This local installer is unsigned. Public redistribution must include the
corresponding source and notices required by the bundled component licenses;
this file is not a substitute for those obligations.
