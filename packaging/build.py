"""Build the locked, self-contained Windows release; supply the compiler path."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--iscc", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
environment = {
    key: value
    for key, value in os.environ.items()
    if key not in ("PYTHONPATH", "PYTHONHOME")
}
# Resolve Windows libraries from the OS, never unrelated developer tool bundles.
environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        str(root / "packaging/FastVideoCropper.spec"),
        "--noconfirm",
        "--clean",
    ],
    cwd=root,
    env=environment,
    check=True,
)
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        str(root / "packaging/FastVideoCropper.spec"),
        "--noconfirm",
        "--clean",
        "--",
        "--smoke",
    ],
    cwd=root,
    env=environment,
    check=True,
)
stage = (
    Path(tempfile.mkdtemp(prefix=f"FastVideoCropper-verification-{version}-"))
    / "bundle"
)
shutil.copytree(root / "dist/FastVideoCropperSmoke", stage)
environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
subprocess.run(
    [str(stage / "FastVideoCropperSmoke.exe"), str(root / "dist/frozen-smoke.json")],
    cwd=stage,
    env=environment,
    check=True,
    timeout=90,
)
subprocess.run(
    [
        str(args.iscc),
        f"/DMyAppVersion={version}",
        str(root / "packaging/installer.iss"),
    ],
    cwd=root,
    check=True,
)
installer = root / f"dist/installer/FastVideoCropper-{version}-windows-amd64-Setup.exe"
with installer.open("rb") as stream:
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
installer.with_suffix(".exe.sha256").write_text(f"{digest}  {installer.name}\n")
print(installer)
