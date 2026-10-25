# Development

## Run from source

- Install Python 3.12+, uv, and FFmpeg with ffprobe on PATH.
- Install dependencies: `uv sync --locked`.
- Launch: `uv run fastvideocropper`.
- Launch without reading or saving preferences: `uv run fastvideocropper -NoProfile`. Add `-Minimize` to start minimized.
- Pass files or folders as arguments: `uv run fastvideocropper "C:\Videos" "C:\Clips\clip.mp4"`.
- Run tests: `uv run pytest`.
- Pytest uses Qt's offscreen platform and Windows Vista widget style so widget tests do not interrupt the desktop and retain Windows sizing. Launch/restart checks use `-NoProfile -Minimize`; controller-based integration checks use `no_profile=True` and `showMinimized()`. Persistence tests use isolated temporary profiles, and rendering/keyboard tests restore their offscreen windows. Packaging smoke tests exercise native minimized Windows startup with both flags.
- Run lint checks: `uv run ruff check .`.

## Implementation

- PySide6 supplies Qt Widgets and Qt Multimedia playback; PyQtGraph provides the crop ROI; FFmpeg handles export.
- QSettings stores preferences in the platformdirs user configuration directory. Window geometry, dock layout, and splitter sizes use the `mainWindow` group; appearance uses `appearance/theme` and `appearance/icon`.
- `src/fastvideocropper/styles/components.qss` defines component spacing and typography. The selected theme supplies colours.
- Button properties select styles: `variant="primary"` for primary-action spacing and typography; `buttonSize="medium"`, `"large"`, or `"xlarge"` for height multipliers of 1.5, 2, or 3 and font multipliers of 1.25, 1.5, or 2.5. Sizes derive from the system font and native button height at startup.
- Packaged icons in `src/fastvideocropper/icons/` mirror the `assets/` colour groups.
- Source Explorer integration uses the current interpreter with `-I -m fastvideocropper`; the package must remain installed in that interpreter. Setup installations use their private interpreter and application icon.

## References

- [Component decisions](components.md)
- [Feature coverage and verification](coverage.md)
- [Windows installer build instructions](../packaging/README.md)
- [Changelog](../CHANGELOG.md)
