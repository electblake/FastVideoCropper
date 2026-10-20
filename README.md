# FastVideoCropper

Native PySide6 desktop video cropper. Uses Qt Multimedia for playback, Qt Widgets
with the system style, PyQtGraph's existing ROI component for crop manipulation,
and FFmpeg for HEVC export with copied audio.

## Run

Install Python 3.12+, uv, and FFmpeg (including ffprobe) on PATH.

```powershell
uv sync
uv run fastvideocropper
```

Open multiple videos with Ctrl+O or drop files on the window. Drag the crop or
its eight handles; use the numeric fields for keyboard editing. Set In and Out
at the playhead or enter seconds directly. Export writes `name_CROPPED.ext`
beside the source and overwrites that output. The source is never overwritten.

Choose common aspect ratios directly from the 12-button preset grid. The selected
button stays checked; independent edits that change the ratio clear it to Custom.
Use Lock aspect ratio to lock or unlock resizing independently of preset selection.

Under Help → Install in File Explorer, click Install in File Explorer to add
“Open in FastVideoCropper” to folder, folder-background, and drive context menus
for the current user. No administrator access is needed; installing again
overwrites the same entries. Explorer fills the Folder field without loading
videos or starting an export. Open videos uses this folder as its starting location.
Source installations use the current interpreter with `-I -m fastvideocropper`,
so the package must remain installed in that interpreter. Setup installations
use their private Python interpreter and the installed application icon.

```powershell
uv run pytest
uv run ruff check .
```

The native platform controls retain system fonts, palette, focus indicators,
and DPI scaling. No stylesheets, custom painting, or custom crop widgets.
Desktop defaults: resizable rectangular window, English labels, system locale
for numbers, mouse and keyboard input, normal desk viewing distance.

See [component decisions](docs/components.md) and [coverage](docs/coverage.md).

## Windows installer

Release 0.3.1 provides a small per-user Windows x64 online Setup executable.
It downloads uv, Python, the locked Qt/Python dependencies, FFmpeg and FFprobe.
Installation requires Internet access; the installed app runs offline.
See [release build instructions](packaging/README.md)
and [changelog](CHANGELOG.md).
