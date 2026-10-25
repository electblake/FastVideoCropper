# User guide

## Open videos

- Use Ctrl+O or drop files and folders onto the window or Files panel.
- Folders add immediate `.mp4`, `.mkv`, `.mov`, `.avi`, and `.webm` files, without scanning subfolders or duplicating existing entries.
- Select none unloads the current video while retaining the list and segment edits. Clear files also removes the list, completion markers, and cached segments.
- Segment settings remain available when switching videos during the session.

## Segments and crops

- Use Segment → Detect segments to split a video at scene changes. Lower the threshold to detect more cuts; adjust minimum segment length, frame step, and decoder threads in the dialog.
- Detection replaces existing segments after confirmation and copies the current crop settings into each new segment. Cancel detection stops the scan.
- Select a segment in the list or timeline, then drag its crop or resize handles. Numeric fields support precise editing.
- Each segment stores its crop, rotation, aspect preset, aspect lock, and padding independently.
- Aspect presets center the largest matching crop within the source. Original restores the full frame; Lock aspect ratio controls resizing independently.
- Padding X/Y expands or insets both sides of an axis in source pixels. Expansion stops at source edges; insets must leave positive dimensions. The dashed outline shows the output crop.
- Merge similar segments combines adjacent segments with identical crop geometry and padding, retaining the first segment's other settings.
- Clear segments removes all segments. Export requires at least one segment.

## Export

- Export segments writes `name_SEGMENT_001_CROPPED.ext`, `name_SEGMENT_002_CROPPED.ext`, and subsequent files beside the source. Matching outputs are overwritten; the source is preserved.
- Video is encoded as HEVC and audio is copied. Choose a CPU or supported GPU encoder in Settings.
- If the source container rejects HEVC, export retries that segment as MKV and uses MKV for the remaining segments. The Process log records the change.
- Export displays each segment's crop, progress, speed, and estimated time remaining. Crop editing is disabled during export.
- Stop and keep retains completed segments and the current output. Cancel and delete removes completed and partial outputs from the current export. Both stop the queue without advancing to another video.
- Load next after completion advances through the list. After the final file, the video unloads while the list and segment edits remain available.

## Preferences and layout

- Launch with `-Minimize` to start minimized. Combine it with `-NoProfile` for isolated, less disruptive automation: `uv run fastvideocropper -NoProfile -Minimize "C:\Videos"`. Both flags are preserved on restart.

- Launch with `-NoProfile` to ignore saved preferences and keep all settings and window state in memory for that session. Nothing is saved to the user profile. This is useful for tests and headless/programmatic usage; it does not itself hide the window. Example: `uv run fastvideocropper -NoProfile "C:\Videos"`. Python callers can use `Application(no_profile=True)`.
- Preferences are stored in `%LOCALAPPDATA%\FastVideoCropper\settings.ini`. Detection, playback, encoding, completion actions, appearance, and window layout are restored on startup. Segment edits remain session-only.
- Settings → Appearance selects the theme and icon colour. Icon changes apply immediately; theme changes require a restart, which discards unsaved segment edits.
- Drag the Segments panel title bar to dock or float it. View → Segments toggles visibility; View → Reset Layout restores the default panels and splitter sizes.
- Help → Install in File Explorer adds Open in FastVideoCropper to supported video, folder, folder-background, and drive context menus for the current user. Reinstall these entries after changing the icon colour.
- Help → Check for Updates checks GitHub releases and downloads the matching Windows installer. Installation starts after the app exits.
