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

Open multiple videos with Ctrl+O or drop files on the window. Detect segments,
select one, then drag its crop or its eight handles; use the numeric fields for
keyboard editing. Export requires segments. The source is never overwritten.

Use **Segment → Detect segments…** (or the button above the crop controls) to
split the video at scene changes. Adjust the scene threshold (lower detects more
cuts), minimum segment length, frame step, and decoder threads in the dialog. These preferences are saved in
QSettings and restored when the dialog is reopened, including after restarting
the app. Detection replaces existing segments and copies the current crop
settings into each new segment.
The progress display reports video time scanned and cuts found. **Cancel detection**
stops the scan and retains the existing segments. FFmpeg diagnostics appear in
the Process log.

Application preferences use QSettings in `settings.ini` under platformdirs' user
config directory (`%LOCALAPPDATA%\FastVideoCropper` on Windows). Detection options,
mute, preview and zoom preferences, encoder/device, completion actions and delays,
folder, window geometry, panel sizes, and selected tab are restored on startup.
Crop geometry, rotation, preset, and aspect lock belong to each video's segments
and are retained only during the session.

Select a segment in the right-hand list or click its timeline region to edit its
crop, rotation, aspect preset, and aspect lock independently.
**Export segments** writes separate `name_SEGMENT_001_CROPPED.ext`,
`name_SEGMENT_002_CROPPED.ext`, etc. beside the source, overwriting matching outputs.
Stop or cancel ends the queue; earlier completed files remain. Cancel deletes the
current output. **Segment → Clear segments** removes all segments and disables
export until detection creates new segments. Segment settings remain
available when navigating between videos during the session.
Export saves the selected crop before starting, selects and scrolls to each segment
as it is processed, and loads its crop overlay and settings. The preview identifies
the segment, time range, crop dimensions and position, rotation, and aspect lock.
Crop editing stays locked during export so the displayed settings match the output.
Turning off preview updates still loads the starting frame for each segment.

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
