# Windows release build

Version comes from `pyproject.toml`. The same value is written into the application
EXE, Inno Setup metadata and installer filename. Stable upgrade identity:
`electblake.FastVideoCropper`.

Prerequisites: Windows x64, uv, Python 3.13.12, and Inno Setup 6.7.3.
Supply the actual installed compiler path; the build never searches alternate
compiler locations.

From the repository root in PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".build-venv"
uv sync --locked --no-dev --group build --python 3.13.12
.build-venv\Scripts\python.exe packaging\fetch_vendor.py
.build-venv\Scripts\python.exe packaging\build.py --iscc "C:\Users\shoji\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
```

The build uses the pinned, checksum-verified Gyan FFmpeg 8.1.2 x64 essentials
archive recorded in `vendor.json`. FFmpeg and FFprobe are private executables
inside the application; no PATH edits, Python installation, package-manager
bootstrap, or installer-time downloads occur.

The installer is per-user and requires no administrator privileges. Start Menu
and optional desktop shortcuts launch the installed application. QSettings data
is stored outside the installation directory and is preserved on uninstall.
Installers use the same AppId for upgrades.

Artifacts:

- `dist/FastVideoCropper/`: portable application payload.
- `dist/installer/FastVideoCropper-0.2.0-windows-amd64-Setup.exe`.
- Adjacent `.exe.sha256`: installer SHA-256.
- `dist/frozen-smoke.json`: relocated-bundle playback/crop/export verification.

The separate frozen smoke executable is a build-only verification harness. It
uses the same application source, dependencies, media tools and PyInstaller spec,
but is excluded from Setup. It generates a video, decodes it with Qt Multimedia,
rotates and crops a selected interval, exports HEVC/AAC, and verifies the output.
Both freezing and verification use PATH restricted to Windows System32 and omit
PYTHONPATH/PYTHONHOME, preventing unrelated developer DLLs from entering the
bundle. Verification runs outside the source checkout.

Generated binaries, vendor archives, environments and build intermediates are
ignored by Git. Source, lock file, compiler recipe and input checksum manifest
are committed. The installer is unsigned; no release has been published.

Clean-VM interactive/silent install, upgrade and uninstall validation must be
completed before public distribution. The current host is not a disposable
Windows test environment. Third-party notices are bundled; see `THIRD-PARTY.md`
for source-redistribution requirements.
