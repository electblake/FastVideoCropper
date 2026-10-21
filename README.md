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

Use **Segment → Detect segments…** (or the button in the Segments panel) to
split the video at scene changes. Adjust the scene threshold (lower detects more
cuts), minimum segment length, frame step, and decoder threads in the dialog. These preferences are saved in
QSettings and restored when the dialog is reopened, including after restarting
the app. Detection asks before clearing existing segments and copies the current crop
settings into each new segment.
The progress display reports video time scanned and cuts found. **Cancel detection**
stops the scan; segments cleared by a confirmed replacement remain cleared. FFmpeg diagnostics appear in
the Process log.

Application preferences use QSettings in `settings.ini` under platformdirs' user
config directory (`%LOCALAPPDATA%\FastVideoCropper` on Windows). Detection options,
mute, preview and zoom preferences, encoder/device, completion actions and delays,
folder, window geometry, panel sizes, and selected tab are restored on startup.
Window geometry, dock layout, and splitter sizes use the `mainWindow` settings group.
Crop geometry, pixel padding, rotation, preset, and aspect lock belong to each video's segments
and are retained only during the session.

**Padding X/Y** adjusts both sides of each axis in whole source pixels: positive
values expand the crop, negative values inset it. Expansion stops at source edges.
The dashed outline and shaded mask show the output crop; the original frame remains
editable. Padding is saved independently per segment, inherited on split, and swaps
axes with rotation. Insets must leave a positive crop width and height.

The **Segments** panel docks on the right by default. Drag its title bar to move
it to another dock area or float it in a separate window. **View → Segments**
shows or hides it. **View → Reset Layout** restores the default dock arrangement
and splitter sizes without changing the main window's size or position.
Panel position, size, floating state, and visibility are restored on startup.

Select a segment in the Segments list or click its timeline region to edit its
crop, rotation, aspect preset, and aspect lock independently.
**Segment → Merge similar segments** combines consecutive touching segments with
identical crop geometry and X/Y padding. Preset, aspect lock, and rotation do not
affect matching; the merged segment retains the first segment's settings. The
action is enabled when a matching pair exists and the app is idle.
**Export segments** writes separate `name_SEGMENT_001_CROPPED.ext`,
`name_SEGMENT_002_CROPPED.ext`, etc. beside the source, overwriting matching outputs.
If FFmpeg reports that the source container cannot store HEVC (including 3GP and
WebM), export retries that segment as MKV and uses MKV for the remaining segments.
The Process log reports the fallback, removed failed output, and new filename.
The video encoder and copied audio stay unchanged; other failures are not retried.
Stop or cancel ends the queue; earlier completed files remain. Cancel deletes the
current output. **Segment → Clear segments** removes all segments and disables
export until detection creates new segments. Segment settings remain
available when navigating between videos during the session.
Export saves the selected crop before starting, selects and scrolls to each segment
as it is processed, and loads its crop overlay and settings. The status bar shows
the processing segment, progress, speed, and estimated time remaining.
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

Release 0.7.0 provides a small per-user Windows x64 online Setup executable.
It downloads uv, Python, the locked Qt/Python dependencies, FFmpeg and FFprobe.
Installation requires Internet access; the installed app runs offline.
See [release build instructions](packaging/README.md)
and [changelog](CHANGELOG.md).
