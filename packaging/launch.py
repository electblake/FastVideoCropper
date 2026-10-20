"""Installed entry point: use only application-private media tools."""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from fastvideocropper import APP_NAME, APP_VERSION, integrations
from fastvideocropper.app import Application

if sys.argv[1:] == ["--install-explorer"]:
    sys.exit(integrations.install())
app = QApplication(sys.argv)
app.setApplicationName(APP_NAME)
app.setApplicationVersion(APP_VERSION)
app.setOrganizationName("FastVideoCropper")
tools = Path(__file__).resolve().parent / "tools/ffmpeg"
controller = Application(
    str(tools / "ffmpeg.exe"),
    str(tools / "ffprobe.exe"),
    folder=sys.argv[1] if len(sys.argv) > 1 else None,
)
controller.window.show()
result = app.exec()
if controller.window.pending_installer is not None:
    os.startfile(controller.window.pending_installer)
sys.exit(result)
