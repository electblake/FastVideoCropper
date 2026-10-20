# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
