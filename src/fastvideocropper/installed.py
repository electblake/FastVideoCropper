"""Entry point for the private environment created by Windows Setup."""

import os
import subprocess
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
        paths=[arg for arg in sys.argv[1:] if arg not in ("-NoProfile", "-Minimize")],
        launcher_module=MODULE,
        no_profile="-NoProfile" in sys.argv[1:],
    )
    if "-Minimize" in sys.argv[1:]:
        controller.window.showMinimized()
    else:
        controller.window.show()
    result = app.exec()
    if controller.restart_requested:
        subprocess.Popen(
            [sys.executable, "-m", MODULE, *sys.argv[1:]],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    if controller.window.pending_installer is not None:
        os.startfile(controller.window.pending_installer)
    return result


if __name__ == "__main__":
    sys.exit(main())
