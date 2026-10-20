# Windows online installer

Build requirements: Python 3.12+, uv, and Inno Setup 6.7.3. The compiler path is explicit:

```powershell
uv sync --locked
.venv\Scripts\python.exe packaging\build.py --iscc "C:\Users\shoji\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
```

The installer embeds only application source, lock file, metadata, icon, and
notices. Inno Setup downloads and verifies the SHA-256 of the pinned uv 0.13.4
and FFmpeg 8.1.2 ZIP archives before extracting them using its native archive
support. URLs, hashes and expanded sizes are in `uv.json` and `vendor.json`.
uv downloads Python 3.13.12 into the application's private `python` directory,
then installs the application and locked runtime packages into
`application/.venv`. It does not register Python or change PATH. Developer
packages are excluded. No Python, Qt or FFmpeg binaries are embedded in Setup.

An Internet connection is required during installation; downloads total several
hundred megabytes. Playback and export work offline afterward. This is a small
online Setup executable, not a relocatable installed environment: virtual
environments must remain at their installation path.

The stable upgrade AppId is `electblake.FastVideoCropper`. Upgrading removes the
old 0.2.0 frozen executable and `_internal` tree. Shortcuts use the installed
`pythonw.exe` and `fastvideocropper.installed` module. Explorer registration uses
the same module so private FFmpeg paths survive context-menu launches.
Uninstall removes downloaded tools and the generated private Python environment;
QSettings preferences remain outside the installation directory.

Inno's standard download and process logs record installation operations. The
native Run section waits for uv and logs its output; no retry or recovery
scripts are added. A successful Setup process alone is not proof that uv
installed every dependency: verify the installed application before release.

Outputs are `dist/installer/FastVideoCropper-<version>-windows-amd64-Setup.exe`
and its `.exe.sha256` file. Generated outputs are excluded from Git.

To verify an installation, run its `application/.venv/Scripts/python.exe` with
`-I packaging/smoke.py <absolute-report-path>`, using absolute paths to the smoke
script and report. The smoke test generates media with the installed FFmpeg,
decodes it with Qt Multimedia, crops/rotates/trims, exports HEVC with AAC audio,
and probes the resulting dimensions and frame count. Restrict PATH to Windows
System32 and remove PYTHONPATH/PYTHONHOME during this test.

The installer is unsigned. Host installation tests do not replace testing on a
clean Windows VM. Release notes state the actual validation performed.
