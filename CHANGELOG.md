# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.7] - 2026-10-21

### Added

- Added 1/2 Center below 1/3 Center, between 1/2 Left and 1/2 Right, to select the centered half of the frame.
- Added regression coverage for slice button placement, crop geometry, rotation, aspect locking, keyboard activation, and saved segment restoration.

## [0.7.6] - 2026-10-21

### Changed

- Renamed Locate output to Open Output Folder and moved it into the Files widget.
- Moved Export segments to the start of the center export controls, immediately before Pause.
- Applied the blue icon throughout the application and Windows shortcuts, and reserved the gray icon for Setup.

### Fixed

- Used a distinct blue icon filename for shortcuts and Explorer integration to avoid reusing cached artwork.
- Applied the application icon to all windows and dialogs.
- Updated layout regression checks for the relocated export and output-folder buttons.

## [0.7.5] - 2026-10-20

### Removed

- Removed the Folder label and input from the Files widget, preserving video opening, drag-and-drop loading, and the saved file-dialog starting location.

## [0.7.4] - 2026-10-20

### Fixed

- Removed the export preview's dependency on a video-frame callback to permit subsequent seeks, preventing a missing callback from stalling preview updates.

## [0.7.3] - 2026-10-20

### Fixed

- Calculated every aspect-ratio preset from the full, rotation-adjusted video dimensions and centered the crop, preventing repeated preset switching from shrinking the selection.
- Preserved manually adjusted crop geometry and position when restoring saved segments and videos.

## [0.7.2] - 2026-10-20

### Changed

- Applied the blue icon to the application window, shortcuts, and File Explorer integration.
- Applied the charcoal icon to the Setup executable.
- Added the blue logotype to the top of the README at a maximum width of 640 pixels.

## [0.7.1] - 2026-10-20

### Changed

- Organized source artwork into blue, charcoal, gray, and violet icon and logotype variants, and included the additional muted logo artwork.
- Removed superseded artwork files from the source tree.

## [0.7.0] - 2026-10-20

### Added

- Added Merge similar segments to the Segment menu and Segments panel, combining touching segments with matching crop geometry and padding while ignoring preset, aspect lock, and rotation.
- Preserved the first segment's settings, the selected merged segment, and playback position when merging.

### Fixed

- Fixed Python installation and upgrade junction failures by downloading, verifying, and extracting a pinned Python archive directly through Inno Setup; retained the default RedirectionGuard mitigation.
- Fixed countdown regression tests to wait for the deferred load-completion callback before checking the timer.

## [0.6.1] - 2026-10-20

### Added

- Added a dockable Files list with direct video selection, pending/completed status, and a View menu visibility toggle.
- Added Copy Logs to Clipboard and Clear Logs buttons beneath the Process log, with status-bar confirmation for both actions.

### Changed

- Cached pinned uv and FFmpeg download archives across installs, updates, and uninstalls, verifying their hashes before extraction.

### Removed

- Removed the Zoom into frame checkbox and automatic crop-focused preview fitting.

### Fixed

- Retried HEVC container rejections as MKV, reporting the fallback and output filename in the Process log and using MKV for remaining segments.
- Bounded fallback diagnostic memory while recognizing messages split across FFmpeg output chunks; kept canceled exports, crashes, and unrelated failures from retrying.
- Explicitly released displayed video frames when unloading completed videos, switching files, and closing the application.

## [0.5.1] - 2026-10-20

### Removed

- Removed the redundant crop and segment summary above the video, giving its space to the preview.

## [0.5.0] - 2026-10-20

### Added

- Added buttons to reset padding X, padding Y, or both to zero.

### Changed

- Displayed the application version in the window title.
- Moved processing, detection, loading, and completion messages into the bottom status bar.
- Unloaded the final completed video when automatic advancement was enabled, while preserving saved segment settings.

### Removed

- Removed redundant padding help and aspect-ratio status text from crop controls.

### Fixed

- Preserved crop resize handles when changing aspect locks.
- Kept failed and canceled exports loaded and treated crashed FFmpeg processes as failures.

## [0.4.0] - 2026-10-20

### Added

- Added an Add segment button and Segment menu action that created a full-timeline segment only when the segment list was empty, with native status-bar feedback.
- Added Remember crop settings with QSettings persistence for crop geometry, rotation, aspect preset, aspect lock, and pixel padding across files and sessions.
- Added Automatically create first segment after loading and restoring crop settings, while preserving existing segments.
- Added signed per-segment X/Y pixel padding with a dashed output outline, matching preview masks, and pixel-accurate exports.
- Added crop-border detection with persisted FFmpeg options and half/third frame presets.
- Added playback controls for video ends, adjacent segments, and one-second seeking.
- Added a dockable Segments panel with a View menu visibility toggle and Reset Layout action.
- Added a Split segment menu action and button that split at the scrubber position in place, preserving crop settings and segment order.
- Added FFmpeg scene detection with adjustable scene threshold and minimum segment length.
- Added frame-step and decoder-thread controls for scene detection, persisted in QSettings.
- Added live scene-detection progress showing percentage, video time scanned, cut count, and a completion summary.
- Added a Segment menu, selectable segment list, timeline markers, and independent crop, rotation, and aspect settings for each segment.
- Added separate numbered exports for cropped segments and a Clear segments action to restart detection.

### Changed

- Moved Export segments to the bottom of the Segments dock.
- Centered crops horizontally and vertically after selecting an X:Y aspect-ratio preset, while preserving saved crop positions when restored.
- Asked for confirmation before replacing existing segments with scene detection results.
- Advanced the video preview with scene-detection progress when Preview while processing was enabled.
- Saved window geometry, dock placement, floating state, visibility, and splitter sizes under the `mainWindow` QSettings group.
- Stored application preferences in a QSettings INI file under the platformdirs user config directory, including mute and window layout.
- Kept crop geometry, rotation, presets, and aspect locks specific to each video's segments.
- Displayed current position and total duration separately as `HH:MM:SS` in the playback row.
- Changed scene-threshold adjustments to increments of 0.01.
- Saved scene-detection threshold and minimum segment length in QSettings.
- Moved scene detection, video metadata probing, and GPU discovery onto Qt process signals.
- Bounded the process log to limit memory use during long operations.

### Removed

- Removed retired frozen-build launcher branches.
- Removed standalone In/Out controls, timeline labels, and the unsegmented export path.

### Fixed

- Updated the installed-app smoke test for segment-based trimming, export completion, and isolated configuration paths.
- Started Auto-run next countdowns after loading and automatic segment creation so new files continued through batch exports.
- Deferred automatic segment creation outside Qt video-frame callbacks and canceled queued load completion when switching files or closing.
- Disabled Segments dock controls during application updates.
- Restored crop detection controls after returning to videos with saved segments.
- Matched segment navigation, scrubber selection, and split controls to rounded player timestamps at fractional-millisecond boundaries.
- Reset pixel padding for newly opened videos while restoring saved segment padding when returning to a video.
- Refitted zoomed previews after padding edits and preserved unpadded export rounding.
- Repainted timeline selection immediately and kept the selected segment row distinct after focus changes.
- Refreshed cached segment dimensions after loading each video's metadata.
- Linked scrubber seeking to segment selection and crop settings without moving away from the chosen frame.
- Displayed each segment's crop, rotation, aspect settings, and time range in the preview as the export queue advances.
- Prevented queued video frames from marking a new source ready before metadata and duration loaded.
- Allowed scene detection to be canceled without deleting previous exports; confirmed segment replacements remained cleared.
- Released temporary dialogs and closed active scans without blocking the UI until detection completed.

## [0.3.1] - 2026-10-20

### Added

- Added the standard MIT license and displayed it as the Windows installer agreement.
- Included the license in the installed application and package metadata.

### Changed

- Documented the preselected launch-on-finish option; silent installations continued to skip launch.

## [0.3.0] - 2026-10-20

### Changed

- Replaced the bundled Windows installer with a small online Setup that downloaded pinned uv and FFmpeg archives and installed Python 3.13.12 and locked runtime packages with uv.
- Kept Python, media tools, and the virtual environment private to the selected installation directory.
- Removed PyInstaller and frozen-build scripts from the release toolchain.

### Fixed

- Preserved private media-tool paths when launching the installed app from File Explorer.
- Updated shortcuts to launch the installed Python environment without a console window.
- Removed the previous frozen payload during upgrades and generated Python environments during uninstall.
- Enabled native ZIP extraction for downloaded installation archives.
- Refreshed existing Explorer commands on upgrade and removed them on uninstall.
- Released the media source when closing the window so Windows could unlock the video file.

## [0.2.0] - 2026-10-20

### Added

- Created the initial PySide6 desktop application with native Qt controls.
- Added video playback, multi-file navigation, crop editing, rotation, and time selection.
- Added twelve aspect-ratio buttons and independent aspect locking.
- Added HEVC export with copied audio, progress, pause/resume, stop, and cancellation.
- Added saved preferences, processing previews, and completion countdowns.
- Added a self-contained Windows installer and reproducible packaging scripts.
- Added automated playback, crop, export, and process-lifecycle tests.
- Added an application icon, per-user File Explorer integration, and manual update checking.

### Fixed

- Preserved crop coordinates across source reloads, anamorphic video, and display rotation.
- Preserved arbitrary locked aspect ratios across all eight resize handles.
- Prevented numeric position edits from rounding unedited crop dimensions.
