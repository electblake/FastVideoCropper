"""Compile the small online installer from pinned download manifests."""

import argparse
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--iscc", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
(root / "build").mkdir(exist_ok=True)
definitions = []
for name, filename in (("Uv", "uv.json"), ("FFmpeg", "vendor.json")):
    manifest = json.loads((root / "packaging" / filename).read_text())
    for field, suffix in (
        ("url", "Url"),
        ("sha256", "Hash"),
        ("download_size", "DownloadSize"),
        ("extracted_size", "Size"),
    ):
        definitions.append(f'#define {name}{suffix} "{manifest[field]}"')
(root / "build/downloads.iss").write_text("\n".join(definitions) + "\n")
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
