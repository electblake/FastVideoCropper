"""Manual GitHub release checks and installer downloads."""

import json
import platform
from urllib.request import Request, urlopen

from platformdirs import user_cache_path
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from . import APP_NAME, APP_VERSION, GITHUB_API_VERSION, GITHUB_REPOSITORY

RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"


def version_tuple(value):
    return tuple(int(part) for part in value.split("."))


def installer_asset(release):
    version = release["tag_name"].removeprefix("v")
    name = (
        f"{APP_NAME}-{version}-{platform.system().lower()}-"
        f"{platform.machine().lower()}-Setup.exe"
    )
    return next(a for a in release["assets"] if a["name"] == name)


class UpdateWorker(QThread):
    progress = Signal(int, int)
    checked = Signal(dict)
    downloaded = Signal(object)

    def __init__(self, parent, asset=None):
        super().__init__(parent)
        self.asset = asset

    def run(self):
        if self.asset is None:
            request = Request(
                f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"{APP_NAME}/{APP_VERSION}",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                },
            )
            with urlopen(request, timeout=30) as response:
                release = json.load(response)
            self.checked.emit(release)
        else:
            directory = user_cache_path(APP_NAME, appauthor=False) / "updates"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / self.asset["name"]
            current = 0
            with (
                urlopen(self.asset["browser_download_url"], timeout=30) as response,
                path.open("wb") as output,
            ):
                while chunk := response.read(256 * 1024):
                    output.write(chunk)
                    current += len(chunk)
                    self.progress.emit(current, self.asset["size"])
            self.downloaded.emit(path)


class UpdateDialog(QDialog):
    busy_changed = Signal(bool)
    install_requested = Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Software Update")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(460)
        self.busy = False
        self.available = False
        self.ready = False
        self.installer_path = None
        self.workers = []
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.download_button = QPushButton("Download Update")
        self.install_button = QPushButton("Quit and Install")
        self.close_button = QPushButton("Close")
        for button in (self.download_button, self.install_button, self.close_button):
            button.setAutoDefault(False)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.download_button.clicked.connect(self.download)
        self.install_button.clicked.connect(self.install)
        self.close_button.clicked.connect(self.reject)

    def set_busy(self, busy):
        self.busy = busy
        self.download_button.setEnabled(not busy and self.available and not self.ready)
        self.install_button.setEnabled(not busy and self.ready)
        self.close_button.setEnabled(not busy)
        self.busy_changed.emit(busy)

    def start_worker(self, worker):
        self.workers.append(worker)
        worker.finished.connect(self.worker_finished)
        worker.start()

    @Slot()
    def worker_finished(self):
        worker = self.sender()
        self.workers.remove(worker)
        worker.deleteLater()

    def check(self):
        self.available = False
        self.ready = False
        self.installer_path = None
        self.release = None
        self.status.setText("Checking for updates…")
        self.progress.setRange(0, 0)
        self.set_busy(True)
        self.show()
        worker = UpdateWorker(self)
        worker.checked.connect(self.checked)
        self.start_worker(worker)

    @Slot(dict)
    def checked(self, release):
        self.release = release
        version = release["tag_name"].removeprefix("v")
        self.available = version_tuple(version) > version_tuple(APP_VERSION)
        self.status.setText(
            f"Installed: {APP_VERSION} · Latest: {version}\n"
            + ("Update available" if self.available else "Up to date")
        )
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.set_busy(False)

    def download(self):
        asset = installer_asset(self.release)
        self.status.setText(f"Downloading {asset['name']}…")
        self.progress.setRange(0, 0)
        self.set_busy(True)
        worker = UpdateWorker(self, asset)
        worker.progress.connect(self.download_progress)
        worker.downloaded.connect(self.downloaded)
        self.start_worker(worker)

    @Slot(int, int)
    def download_progress(self, current, total):
        self.progress.setRange(0, 0 if current == 0 else 1000)
        self.progress.setValue(round(current / total * 1000))

    @Slot(object)
    def downloaded(self, path):
        self.installer_path = path
        self.ready = True
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        self.status.setText("Download complete. Quit and install when ready.")
        self.set_busy(False)

    def install(self):
        self.install_requested.emit(self.installer_path)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)
