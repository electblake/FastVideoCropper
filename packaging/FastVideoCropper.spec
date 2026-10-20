import argparse
import importlib.metadata
import sys
import tomllib
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

root = Path(SPECPATH).parent
parser = argparse.ArgumentParser()
parser.add_argument("--smoke", action="store_true")
options = parser.parse_args()
name = "FastVideoCropperSmoke" if options.smoke else "FastVideoCropper"
entry = "smoke.py" if options.smoke else "launch.py"
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
numbers = tuple(map(int, version.split("."))) + (0,)
vendor = root / "vendor/ffmpeg/8.1.2/win64/ffmpeg-8.1.2-essentials_build"
datas = [
    (str(root / "src/fastvideocropper/FastVideoCropper.ico"), "."),
    (str(vendor / "bin/ffmpeg.exe"), "tools/ffmpeg"),
    (str(vendor / "bin/ffprobe.exe"), "tools/ffmpeg"),
    (str(vendor / "LICENSE"), "licenses/ffmpeg"),
    (str(vendor / "README.txt"), "licenses/ffmpeg"),
    (str(root / "packaging/vendor.json"), "licenses/ffmpeg"),
    (str(root / "packaging/THIRD-PARTY.md"), "licenses"),
    (str(root / "CHANGELOG.md"), "."),
    (str(Path(sys.base_prefix) / "LICENSE.txt"), "licenses/python"),
]
datas += copy_metadata("fastvideocropper")
for distribution_name in ("PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6",
             "numpy", "pyqtgraph", "psutil", "platformdirs", "pyinstaller"):
    distribution = importlib.metadata.distribution(distribution_name)
    for file in distribution.files:
        if "license" in str(file).lower() or "copying" in str(file).lower():
            datas.append((str(distribution.locate_file(file)), f"licenses/{distribution_name}/{file.parent}"))
info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3f, flags=0,
                      OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", "FastVideoCropper"),
            StringStruct("FileVersion", version),
            StringStruct("ProductName", "FastVideoCropper"),
            StringStruct("ProductVersion", version),
            StringStruct("OriginalFilename", "FastVideoCropper.exe"),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
a = Analysis([str(root / "packaging" / entry)], pathex=[str(root / "src")],
             binaries=[], datas=datas, hiddenimports=[], hookspath=[],
             excludes=["pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name,
          icon=str(root / "src/fastvideocropper/FastVideoCropper.ico"),
          debug=False, strip=False, upx=False, console=options.smoke, version=info)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=name)
