"""Entry point for the private environment created by Windows Setup."""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from . import APP_NAME, APP_VERSION, integrations
from .app import Application

MODULE = "fastvideocropper.installed"


def main():
    if sys.argv[1:] == ["--install-explorer"]:
        return integrations.install(MODULE)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("FastVideoCropper")
    root = Path(sys.prefix).parents[1]
    tools = root / "tools/ffmpeg/ffmpeg-8.1.2-essentials_build/bin"
    controller = Application(
        str(tools / "ffmpeg.exe"),
        str(tools / "ffprobe.exe"),
        paths=sys.argv[1:],
        launcher_module=MODULE,
    )
    controller.window.show()
    result = app.exec()
    if controller.window.pending_installer is not None:
        os.startfile(controller.window.pending_installer)
    return result


if __name__ == "__main__":
    sys.exit(main())
