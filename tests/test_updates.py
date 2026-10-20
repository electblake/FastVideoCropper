import io
import json
import runpy
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings, Qt, QThread
from PySide6.QtWidgets import QApplication

from fastvideocropper import app, updates


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(app, "QSettings", lambda *args: settings)
    c = app.Application()
    qtbot.addWidget(c.window)
    c.window.show()
    yield c
    c.window.close()


@pytest.mark.parametrize(
    "latest,available",
    [("0.10.0", True), ("0.2.1", True), ("0.2.0", False), ("0.1.99", False)],
)
def test_versions(controller, latest, available):
    dialog = controller.update_dialog
    dialog.checked({"tag_name": f"v{latest}", "assets": []})
    assert dialog.available is available
    assert dialog.download_button.isEnabled() is available
    assert dialog.status.text() == (
        f"Installed: {updates.APP_VERSION} · Latest: {latest}\n"
        + ("Update available" if available else "Up to date")
    )


def test_exact_asset_required(monkeypatch):
    monkeypatch.setattr(updates.platform, "system", lambda: "Windows")
    monkeypatch.setattr(updates.platform, "machine", lambda: "AMD64")
    with pytest.raises(StopIteration):
        updates.installer_asset(
            {
                "tag_name": "v0.10.0",
                "assets": [{"name": "FastVideoCropper-0.10.0-Windows-x64-Setup.exe"}],
            }
        )


def test_releases_link_and_competing_operation(controller, monkeypatch):
    urls = []
    monkeypatch.setattr(app.QDesktopServices, "openUrl", urls.append)
    controller.view_releases()
    assert urls[0].toString() == (
        f"https://github.com/{updates.GITHUB_REPOSITORY}/releases"
    )
    controller.running = True
    controller.update_enabled()
    assert not controller.check_update_action.isEnabled()
    assert not controller.check_update_button.isEnabled()
    controller.running = False


def test_manual_update_flow(controller, qtbot, monkeypatch, tmp_path):
    c = controller
    dialog = c.update_dialog
    monkeypatch.setattr(updates.platform, "system", lambda: "Windows")
    monkeypatch.setattr(updates.platform, "machine", lambda: "AMD64")
    payload = b"x" * (256 * 1024 + 100)
    asset = {
        "name": "FastVideoCropper-0.10.0-windows-amd64-Setup.exe",
        "size": len(payload),
        "browser_download_url": "https://example.test/installer",
    }
    release = {
        "tag_name": "v0.10.0",
        "assets": [{"name": "wrong-Setup.exe"}, asset],
    }
    assert updates.installer_asset(release) is asset
    gate = threading.Event()
    requests = []
    reads = []

    class Download(io.BytesIO):
        def read(self, size):
            reads.append(size)
            return super().read(size)

    def open_url(request, timeout):
        assert QThread.currentThread() != QApplication.instance().thread()
        assert timeout == 30
        requests.append(request)
        gate.wait()
        if isinstance(request, str):
            return Download(payload)
        return io.BytesIO(json.dumps(release).encode())

    def cache(name, appauthor):
        assert name == updates.APP_NAME
        assert appauthor is False
        return tmp_path

    monkeypatch.setattr(updates, "urlopen", open_url)
    monkeypatch.setattr(updates, "user_cache_path", cache)
    c.countdown("quit", 30)
    c.check_updates()
    assert not c.count_timer.isActive()
    assert dialog.windowModality() == Qt.WindowModality.WindowModal
    assert dialog.minimumWidth() == 460
    assert dialog.status.wordWrap()
    assert dialog.progress.maximum() == 0
    assert not c.window.centralWidget().isEnabled()
    for button in (dialog.download_button, dialog.install_button, dialog.close_button):
        assert not button.isEnabled()
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.close()
    assert not c.window.close()
    assert dialog.isVisible()
    qtbot.waitUntil(lambda: len(requests) == 1)
    request = requests[0]
    assert request.full_url == (
        f"https://api.github.com/repos/{updates.GITHUB_REPOSITORY}/releases/latest"
    )
    assert dict(request.header_items()) == {
        "Accept": "application/vnd.github+json",
        "User-agent": f"{updates.APP_NAME}/{updates.APP_VERSION}",
        "X-github-api-version": updates.GITHUB_API_VERSION,
    }
    gate.set()
    qtbot.waitUntil(lambda: not dialog.busy and not dialog.workers)
    assert dialog.download_button.isEnabled()
    assert not dialog.install_button.isEnabled()
    gate.clear()
    dialog.download_button.click()
    assert dialog.progress.maximum() == 0
    assert not dialog.close_button.isEnabled()
    dialog.download_progress(1, 4)
    assert dialog.progress.maximum() == 1000
    assert dialog.progress.value() == 250
    assert not dialog.close()
    gate.set()
    qtbot.waitUntil(lambda: not dialog.busy and not dialog.workers)
    assert reads == [256 * 1024] * 3
    assert dialog.installer_path == tmp_path / "updates" / asset["name"]
    assert dialog.installer_path.read_bytes() == payload
    assert dialog.progress.value() == 1000
    assert dialog.status.text() == "Download complete. Quit and install when ready."
    assert not dialog.download_button.isEnabled()
    assert dialog.install_button.isEnabled()
    dialog.close_button.click()
    assert not dialog.isVisible()
    assert c.window.pending_installer is None
    gate.clear()
    c.check_updates()
    assert dialog.installer_path is None
    assert not dialog.ready
    assert not dialog.available
    gate.set()
    qtbot.waitUntil(lambda: not dialog.busy and not dialog.workers)
    dialog.downloaded(tmp_path / asset["name"])
    dialog.install_button.click()
    assert c.window.pending_installer == tmp_path / asset["name"]
    assert not c.window.isVisible()


@pytest.mark.parametrize("install", [False, True])
@pytest.mark.parametrize("packaged", [False, True])
def test_launch_after_event_loop(monkeypatch, tmp_path, install, packaged):
    events = []
    path = tmp_path / "Setup.exe"
    window = SimpleNamespace(pending_installer=None, show=lambda: events.append("show"))

    class FakeApp:
        def __init__(self, args):
            pass

        def setApplicationName(self, name):
            pass

        def setApplicationVersion(self, version):
            pass

        def setOrganizationName(self, name):
            pass

        def exec(self):
            events.append("exec")
            window.pending_installer = path if install else None
            return 7

    def launch(installer):
        assert installer == path
        events.append("launch")

    monkeypatch.setattr(
        app, "Application", lambda *a, **kw: SimpleNamespace(window=window)
    )
    monkeypatch.setattr(app, "QApplication", FakeApp)
    monkeypatch.setattr(app.os, "startfile", launch)
    monkeypatch.setattr(app.sys, "argv", ["fastvideocropper"])
    if packaged:
        with monkeypatch.context() as patch:
            patch.setattr("PySide6.QtWidgets.QApplication", FakeApp)
            with pytest.raises(SystemExit) as result:
                runpy.run_path(str(Path(__file__).parents[1] / "packaging/launch.py"))
        assert result.value.code == 7
    else:
        assert app.main() == 7
    assert events == ["show", "exec"] + (["launch"] if install else [])
