# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added a dockable Segments panel with a View menu visibility toggle and Reset Layout action.
- Added a Split segment menu action and button that split at the scrubber position in place, preserving crop settings and segment order.
- Added FFmpeg scene detection with adjustable scene threshold and minimum segment length.
- Added frame-step and decoder-thread controls for scene detection, persisted in QSettings.
- Added live scene-detection progress showing percentage, video time scanned, cut count, and a completion summary.
- Added a Segment menu, selectable segment list, timeline markers, and independent crop, rotation, and aspect settings for each segment.
- Added separate numbered exports for cropped segments and a Clear segments action to restart detection.

### Changed

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

- Repainted timeline selection immediately and kept the selected segment row distinct after focus changes.
- Refreshed cached segment dimensions after loading each video's metadata.
- Linked scrubber seeking to segment selection and crop settings without moving away from the chosen frame.
- Displayed each segment's crop, rotation, aspect settings, and time range in the preview as the export queue advances.
- Prevented queued video frames from marking a new source ready before metadata and duration loaded.
- Allowed scene detection to be canceled without deleting previous exports or replacing existing segments.
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
