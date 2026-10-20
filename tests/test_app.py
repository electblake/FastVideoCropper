import json
import subprocess
import sys
from unittest.mock import MagicMock

import psutil
import pytest
from PySide6.QtCore import QMimeData, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from fastvideocropper import app


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(app, "QSettings", lambda *args: settings)
    controller = app.Application()
    qtbot.addWidget(controller.window)
    controller.window.show()
    yield controller
    controller.window.close()


def test_load_crop_rotate_export(controller, qtbot, source, tmp_path):
    c = controller
    c.paths = [source, source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.end.value() == 8, timeout=15000)
    assert (c.width, c.height) == (320, 240)
    assert c.start.value() == 0
    c.set_rect((20, 30, 160, 120))
    c.rotate(1)
    assert c.rect() == (90, 20, 120, 160)
    c.rotate(3)
    assert c.rect() == (20, 30, 160, 120)
    qtbot.mouseClick(c.preset_buttons["Square"], Qt.MouseButton.LeftButton)
    assert c.rect()[2:] == (120, 120)
    c.center()
    assert c.rect() == (100, 60, 120, 120)
    c.start.setValue(2.3)
    c.end.setValue(5.7)
    c.window.grab().save(str(tmp_path / "window.png"))
    c.export()
    assert not c.next.isEnabled()
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.progress_text.text() == "Complete — output saved"
    assert source in c.done
    assert c.output.exists()
    c.load(1)
    qtbot.waitUntil(lambda: c.ready and c.end.value() == 8, timeout=15000)
    assert c.start.value() == 0
    assert c.rect() == (100, 60, 120, 120)


def test_numeric_lock_and_preset(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.set_rect((0, 0, 160, 120))
    c.lock.setChecked(True)
    c.fields[2].setValue(80)
    assert c.rect()[2:] == (80, 60)
    c.fields[0].setValue(95)
    assert c.rect()[0] == 240
    c.wheel.setChecked(True)
    c.fit()


def test_all_stock_handles_preserve_locked_ratio(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.lock.setChecked(True)
    for handle in c.roi.getHandles():
        c.set_rect((50, 50, 160, 120))
        point = c.roi.mapToParent(handle.pos())
        c.roi.movePoint(handle, (point.x() + 8, point.y() + 4))
        x, y, width, height = c.rect()
        assert width / height == pytest.approx(4 / 3)
        assert (width, height) != (160, 120)
        assert 0 <= x <= 320 - width
        assert 0 <= y <= 240 - height


def test_preset_buttons_lock_rotation_and_restore(controller, qtbot, source, tmp_path):
    c = controller
    c.paths = [source, source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    for locked in (False, True):
        c.lock.setChecked(locked)
        for name, ratio in app.RATIOS.items():
            c.full_frame()
            qtbot.mouseClick(c.preset_buttons[name], Qt.MouseButton.LeftButton)
            assert c.selected_preset == name
            assert c.preset_buttons[name].isChecked()
            assert sum(b.isChecked() for b in c.preset_buttons.values()) == 1
            assert c.rect()[2] / c.rect()[3] == pytest.approx(
                320 / 240 if name == "Original" else ratio
            )
            assert c.lock.isChecked() == locked
    qtbot.mouseClick(c.preset_buttons["16:9"], Qt.MouseButton.LeftButton)
    c.rotate(1)
    assert c.selected_preset == "9:16"
    assert c.preset_buttons["9:16"].isChecked()
    c.rotate(3)
    assert c.selected_preset == "16:9"
    rect = c.rect()
    c.load(1)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rect() == pytest.approx(rect)
    assert c.preset_buttons["16:9"].isChecked()
    c.lock.setFocus()
    qtbot.keyClick(c.lock, Qt.Key.Key_Space)
    assert not c.lock.isChecked()
    c.fields[3].setValue(c.fields[3].value() + 2)
    assert c.selected_preset == "Custom"
    assert not any(b.isChecked() for b in c.preset_buttons.values())
    c.preset_buttons["Square"].setFocus()
    qtbot.keyClick(c.preset_buttons["Square"], Qt.Key.Key_Space)
    assert c.selected_preset == "Square"
    c.window.grab().save(str(tmp_path / "preset-buttons.png"))


def test_position_edits_preserve_fractional_crop(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.set_rect((10.12345, 20.12345, 123.45678, 67.89123))
    c.lock.setChecked(True)
    c.fields[0].setValue(10)
    assert c.rect() == pytest.approx((32, 20.12345, 123.45678, 67.89123))
    c.fields[3].setValue(60)
    assert c.rect()[2] / c.rect()[3] == pytest.approx(123.45678 / 67.89123)
    c.lock.setChecked(False)
    width = c.rect()[2]
    c.fields[3].setValue(50)
    assert c.rect()[2] == width


@pytest.mark.parametrize("finish", ["stop", "cancel"])
def test_pause_resume_and_interrupt(controller, qtbot, source, monkeypatch, finish):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.end.value() == 8, timeout=15000)
    original = app.Export.arguments
    monkeypatch.setattr(app.Export, "arguments", lambda self: ["-re", *original(self)])
    c.export()
    qtbot.waitUntil(lambda: c.processing_position > 0, timeout=15000)
    c.pause_export()
    processes = [psutil.Process(c.process.processId()), *c.suspended_children]
    assert all(p.status() == psutil.STATUS_STOPPED for p in processes)
    if finish == "stop":
        c.stop_export()
    else:
        c.cancel_export()
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert source not in c.done
    if finish == "stop":
        assert c.progress_text.text() == "Stopped — output saved"
        assert c.output.exists()
        result = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_format",
                    "-of",
                    "json",
                    str(c.output),
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        )
        assert 0 < float(result["format"]["duration"]) < 8
    else:
        assert c.progress_text.text() == "Canceled — output deleted"
        assert not c.job.output.exists()


def test_auto_advance_and_countdown(controller, qtbot, source):
    c = controller
    c.paths = [source, source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.end.value() == 8, timeout=15000)
    c.advance.setChecked(True)
    c.auto.setChecked(True)
    c.auto_delay.setValue(30)
    c.export()
    qtbot.waitUntil(lambda: c.index == 1 and c.ready, timeout=15000)
    assert c.count_timer.isActive()
    assert c.start.value() == 0
    assert c.end.value() == 8
    c.count_cancelled()
    assert not c.count_timer.isActive()
    c.countdown("export", 1)
    qtbot.waitUntil(lambda: c.running, timeout=5000)
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.progress_text.text() == "Complete — output saved"


@pytest.mark.parametrize(
    "turns,rect,size",
    [
        (0, (80, 0, 160, 240), (320, 240)),
        (1, (0, 80, 240, 160), (120, 160)),
    ],
)
def test_anamorphic_view_maps_to_source_pixels(
    controller, qtbot, source, tmp_path, turns, rect, size
):
    path = tmp_path / "wide-pixels.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-t",
            "1",
            "-vf",
            "setsar=2",
            "-c:v",
            "libx264",
            "-c:a",
            "copy",
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    c = controller
    c.paths = [path]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.end.value() >= 1, timeout=15000)
    c.end.setValue(1)
    assert c.width == 640
    assert c.fields[2].value() == 320
    c.set_rect((160, 0, 320, 240))
    c.rotate(turns)
    c.square.setChecked(True)
    c.export()
    assert c.job.rect == rect
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.progress_text.text() == "Complete — output saved"
    result = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_streams",
                "-of",
                "json",
                str(c.output),
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    )["streams"][0]
    assert (result["width"], result["height"]) == size
    assert result["sample_aspect_ratio"] == "1:1"


def test_embedded_rotation_coordinates(controller, qtbot, source, tmp_path):
    path = tmp_path / "rotated.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-display_rotation:v:0",
            "90",
            "-i",
            str(source),
            "-t",
            "1",
            "-c",
            "copy",
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    c = controller
    c.paths = [path]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.end.value() >= 1, timeout=15000)
    assert (c.width, c.height) == (240, 320)
    assert c.video.boundingRect().width() == 240
    assert c.video.boundingRect().height() == 320
    c.window.grab().save(str(tmp_path / "rotated-preview.png"))
    assert (c.fields[2].value(), c.fields[3].value()) == (240, 320)
    c.end.setValue(1)
    c.export()
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.progress_text.text() == "Complete — output saved"


def test_drop_on_video_viewport(controller, qtbot, source):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    enter = QDragEnterEvent(
        QPointF(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(controller.viewport, enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(20, 20),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(controller.viewport, drop)
    qtbot.waitUntil(lambda: controller.ready, timeout=15000)
    assert controller.paths == [source]


@pytest.mark.parametrize("exit_code", [0, 1])
@pytest.mark.parametrize("frozen", [False, True])
def test_explorer_install_lifecycle(controller, qtbot, monkeypatch, exit_code, frozen):
    c = controller
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    start = c.process.start
    launches = []

    def launch(executable, arguments):
        launches.append((executable, arguments))
        start(
            sys.executable,
            [
                "-c",
                f"import time; time.sleep(0.3); raise SystemExit({exit_code})",
            ],
        )

    monkeypatch.setattr(c.process, "start", launch)
    c.countdown("export", 30)
    c.install_button.click()
    expected = ["--install-explorer"]
    if not frozen:
        expected = ["-I", "-m", "fastvideocropper", *expected]
    assert launches == [(sys.executable, expected)]
    assert c.running and c.installing
    assert not c.count_timer.isActive()
    for control in (
        c.install_button,
        c.open_button,
        c.open_action,
        c.folder,
        c.export_button,
        c.previous,
        c.next,
        c.pause,
        c.stop,
        c.cancel,
    ):
        assert not control.isEnabled()
    assert c.install_status.text() == "Installing…"
    qtbot.waitUntil(lambda: not c.running, timeout=10000)
    assert not c.installing
    assert c.install_button.isEnabled()
    assert c.open_button.isEnabled()
    assert c.folder.isEnabled()
    assert (c.install_status.text() == "Installed in File Explorer") == (exit_code == 0)


def test_explorer_folder_startup(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "folder.ini"), QSettings.Format.IniFormat)
    settings.setValue("folder_path", "previous folder")
    monkeypatch.setattr(app, "QSettings", lambda *args: settings)
    folder = str(tmp_path / "Selected folder with spaces")
    c = app.Application(folder=folder)
    qtbot.addWidget(c.window)
    assert c.folder.text() == folder
    assert settings.value("folder_path") == folder
    assert c.paths == []
    assert not c.running
    assert not c.count_timer.isActive()
    c.window.close()


def test_explorer_startup_argument(monkeypatch, tmp_path):
    folder = str(tmp_path / "Selected folder with spaces")
    monkeypatch.setattr(sys, "argv", ["fastvideocropper", folder])
    application = MagicMock()
    application.return_value.exec.return_value = 0
    controller = MagicMock()
    controller.return_value.window.pending_installer = None
    monkeypatch.setattr(app, "QApplication", application)
    monkeypatch.setattr(app, "Application", controller)
    assert app.main() == 0
    controller.assert_called_once_with(folder=folder)
