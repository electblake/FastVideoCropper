# Third-party components

Setup downloads uv from Astral's GitHub release and FFmpeg/FFprobe from Gyan
Doshi. Their pinned versions, URLs and checksums are recorded in `uv.json` and
`vendor.json`. The Setup executable does not redistribute their binaries.

uv installs Python from Astral's python-build-standalone distribution and the
runtime wheels recorded in `uv.lock`: PySide6/Qt, Shiboken, NumPy, PyQtGraph,
psutil and platformdirs. Their licenses are retained in the installed Python
and package distributions. Qt libraries remain dynamically linked.

FFmpeg 8.1.2 essentials is licensed under GPLv3. Its extracted archive retains
the distributor's LICENSE and README, including build and source references.

- uv (MIT or Apache-2.0): https://github.com/astral-sh/uv
- Python distributions: https://github.com/astral-sh/python-build-standalone
- FFmpeg distributor: https://www.gyan.dev/ffmpeg/builds/
- FFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/n8.1.2
- Qt licensing: https://www.qt.io/licensing/
- PyQtGraph: https://github.com/pyqtgraph/pyqtgraph
- NumPy: https://numpy.org/
- psutil: https://github.com/giampaolo/psutil
- platformdirs: https://github.com/tox-dev/platformdirs
