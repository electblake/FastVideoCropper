"""Fetch the pinned private FFmpeg release input before building."""

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "packaging/vendor.json").read_text())
destination = root / "vendor/ffmpeg" / manifest["version"] / manifest["architecture"]
destination.mkdir(parents=True, exist_ok=True)
archive = destination / "ffmpeg.zip"
urllib.request.urlretrieve(manifest["url"], archive)
assert (
    hashlib.file_digest(archive.open("rb"), "sha256").hexdigest() == manifest["sha256"]
)
with zipfile.ZipFile(archive) as package:
    package.extractall(destination)
print(destination)
