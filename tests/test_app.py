import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import psutil
import pytest
from PySide6.QtCore import QMimeData, QPointF, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QSpinBox,
)

from fastvideocropper import app


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
    controller = app.Application()
    qtbot.addWidget(controller.window)
    controller.window.show()
    yield controller
    controller.window.close()


def test_load_crop_rotate_export(controller, qtbot, source, tmp_path):
    c = controller
    c.paths = [source, source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    c.replace_segments([(0, c.player.duration() / 1000)])
    assert (c.width, c.height) == (320, 240)
    c.set_rect((20, 30, 160, 120))
    c.rotate(1)
    assert c.rect() == (90, 20, 120, 160)
    c.rotate(3)
    assert c.rect() == (20, 30, 160, 120)
    qtbot.mouseClick(c.preset_buttons["Square"], Qt.MouseButton.LeftButton)
    assert c.rect()[2:] == (120, 120)
    c.center()
    assert c.rect() == (100, 60, 120, 120)
    c.replace_segments([(2.3, 5.7)])
    c.window.grab().save(str(tmp_path / "window.png"))
    c.export()
    assert not c.next.isEnabled()
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.progress_text.text() == "Complete — 1 segments saved"
    assert source in c.done
    assert c.output.exists()
    c.load(1)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    assert c.rect() == (100, 60, 120, 120)


@pytest.mark.parametrize("floating", [False, True])
def test_detect_select_clear_segments(
    controller, qtbot, scene_video, tmp_path, floating
):
    c = controller
    c.segments_dock.setFloating(floating)
    c.paths = [scene_video]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 6000, timeout=15000)
    assert not c.export_button.isEnabled()
    assert not c.crop_page.isEnabled()
    assert not hasattr(c, "start")
    assert not hasattr(c, "end")
    assert not hasattr(c, "range_region")
    c.detection_progress(3, 1)
    assert c.progress.value() == 50
    assert "3.0 / 6.0 s scanned • 1 cuts found" in c.progress_text.text()

    def accept_detection():
        dialog = next(
            d
            for d in c.window.findChildren(QDialog)
            if d.windowTitle() == "Detect segments"
        )
        dialog.grab().save(str(tmp_path / "detection-dialog.png"))
        framestep, threads = dialog.findChildren(QSpinBox)
        assert (framestep.value(), threads.value()) == (1, 0)
        framestep.setValue(2)
        threads.setValue(1)
        dialog.findChild(QDialogButtonBox).button(
            QDialogButtonBox.StandardButton.Ok
        ).click()

    QTimer.singleShot(100, accept_detection)
    c.detect_action.trigger()
    assert not c.detect_button.isEnabled()
    assert not c.open_action.isEnabled()
    qtbot.waitUntil(lambda: not c.detecting, timeout=15000)
    assert c.progress.value() == 100
    assert c.progress_text.text() == "Scene detection complete — 3 segments"
    assert [(s.start, s.end) for s in c.segments] == [(0, 2), (2, 4), (4, 6)]
    assert c.segment_list.count() == 3
    assert c.scene_scan.framestep == 2
    assert c.scene_scan.threads == 1
    assert c.settings.value("scene_framestep", type=int) == 2
    assert c.settings.value("scene_decoder_threads", type=int) == 1

    def check_saved_detection():
        dialog = QApplication.activeModalWidget()
        framestep, threads = dialog.findChildren(QSpinBox)
        assert (framestep.value(), threads.value()) == (2, 1)
        dialog.reject()

    QTimer.singleShot(100, check_saved_detection)
    c.detect_action.trigger()
    assert c.export_button.isEnabled()
    assert c.crop_page.isEnabled()
    assert len(c.segment_regions) == 3
    point = c.range_view.mapViewToScene(QPointF(5, 0.5))
    qtbot.mouseClick(
        c.range_graph.viewport(),
        Qt.MouseButton.LeftButton,
        pos=c.range_graph.mapFromScene(point),
    )
    assert c.active_segment == 2
    c.segment_list.setFocus()
    qtbot.keyClick(c.segment_list, Qt.Key.Key_Home)
    assert c.active_segment == 0
    c.set_rect((20, 30, 160, 120))
    c.lock.setChecked(True)
    c.rotate(1)
    first_rect = c.rect()
    c.segment_list.setCurrentRow(1)
    assert c.turns == 0
    assert c.rect() == (0, 0, 320, 240)
    assert not c.lock.isChecked()
    assert (c.segments[c.active_segment].start, c.segments[c.active_segment].end) == (
        2,
        4,
    )
    c.set_rect((40, 50, 100, 80))
    c.segment_list.setCurrentRow(0)
    assert c.turns == 1
    assert c.rect() == first_rect
    assert c.lock.isChecked()
    c.segment_list.setCurrentRow(1)
    assert c.rect() == (40, 50, 100, 80)
    c.window.grab().save(str(tmp_path / "segments-window.png"))
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.active_segment == 0, timeout=15000)
    assert c.rect() == first_rect
    assert (c.segments[c.active_segment].start, c.segments[c.active_segment].end) == (
        0,
        2,
    )
    c.countdown("export", 30)
    c.clear_segments_action.trigger()
    assert not c.count_timer.isActive()
    assert c.segments == []
    assert c.segment_list.count() == 0
    assert c.segment_regions == []
    assert not c.export_button.isEnabled()
    assert not c.crop_page.isEnabled()
    assert c.detect_button.isEnabled()
    c.detect_segments(0.3, 1)
    qtbot.waitUntil(lambda: not c.detecting, timeout=15000)
    assert len(c.segments) == 3


@pytest.mark.parametrize("preview", [True, False])
def test_export_segments_with_independent_crops(controller, qtbot, source, preview):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    c.replace_segments([(0, 2), (2, 8)])
    c.set_rect((20, 30, 160, 120))
    c.segment_list.setCurrentRow(1)
    c.rotate(1)
    c.set_rect((10, 20, 100, 200))
    c.lock.setChecked(True)
    c.preview.setChecked(preview)
    # Exercise both a changed selection and a first segment already selected.
    if not preview:
        c.segment_list.setCurrentRow(0)
    saved = [(s.rect, s.turns, s.preset, s.locked) for s in c.segments]
    observed = []

    def capture_export_ui():
        observed.append(
            (
                c.segment_list.currentRow(),
                c.rect(),
                c.turns,
                c.lock.isChecked(),
                c.crop_summary.text(),
                [field.value() for field in c.fields[2:]],
                c.player.isPlaying(),
            )
        )

    c.process.started.connect(capture_export_ui)
    c.export()
    assert not c.clear_segments_action.isEnabled()
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.progress_text.text() == "Complete — 2 segments saved"
    assert source in c.done
    assert len(observed) == 2
    for index, (row, rect, turns, locked, summary, size, playing) in enumerate(
        observed
    ):
        assert row == index
        assert rect == [(20, 30, 160, 120), (10, 20, 100, 200)][index]
        assert turns == index
        assert locked == saved[index][3]
        assert f"Processing segment {index + 1} of 2" in summary
        assert f"Crop {size[0]:.0f} × {size[1]:.0f}" in summary
        assert size == list(rect[2:])
        assert not playing
    assert [(s.rect, s.turns, s.preset, s.locked) for s in c.segments] == saved
    assert "Selected segment 2 of 2" in c.crop_summary.text()
    for job, size, frames in zip(c.export_jobs, [(160, 120), (100, 200)], [20, 60]):
        metadata = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-of",
                    "json",
                    str(job.output),
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        )
        video, audio = metadata["streams"]
        assert (video["width"], video["height"]) == size
        assert int(video["nb_frames"]) == frames
        assert audio["codec_name"] == "aac"
        assert float(audio["duration"]) == pytest.approx(frames / 10, abs=0.05)
    assert c.export_jobs[0].output.name.endswith("_SEGMENT_001_CROPPED.mp4")
    assert c.export_jobs[1].output.name.endswith("_SEGMENT_002_CROPPED.mp4")


def test_scrubber_selects_segment_without_jumping_to_start(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 2), (2, 8)])
    c.set_rect((20, 30, 160, 120))
    c.segment_list.setCurrentRow(1)
    c.rotate(1)
    c.set_rect((10, 20, 100, 200))
    c.lock.setChecked(True)
    saved = [(s.rect, s.turns, s.locked) for s in c.segments]

    for position, index in [(1500, 0), (2000, 1), (5750, 1), (0, 0), (8000, 1)]:
        c.seek.setValue(position)
        assert c.segment_list.currentRow() == index
        assert c.active_segment == index
        assert c.player.position() == position
        assert c.turns == saved[index][1]
        assert c.lock.isChecked() == saved[index][2]
        assert c.rect() == [(20, 30, 160, 120), (10, 20, 100, 200)][index]
    assert [(s.rect, s.turns, s.locked) for s in c.segments] == saved


def test_segment_ranges_preserve_precision_when_switching(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 2.033333333), (2.033333333, 8)])
    c.set_rect((0, 0, 160, 120))
    c.segment_list.setCurrentRow(1)
    c.segment_list.setCurrentRow(0)
    assert c.segments[0].end == 2.033333333
    assert c.segments[1].start == 2.033333333


@pytest.mark.parametrize("close", [False, True])
def test_detection_progress_and_cancel(
    controller, qtbot, scene_video, monkeypatch, tmp_path, close
):
    c = controller
    c.paths = [scene_video]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 3), (3, 6)])
    c.output = tmp_path / "previous-output.mp4"
    c.output.write_bytes(b"previous export")
    start = c.process.start

    def realtime(program, arguments):
        arguments.insert(arguments.index("-i"), "-re")
        start(program, arguments)

    monkeypatch.setattr(c.process, "start", realtime)
    c.detect_segments(1, 0, framestep=30, threads=1)
    qtbot.waitUntil(lambda: c.progress.value() > 5, timeout=5000)
    assert c.detecting
    assert "0 cuts found" in c.progress_text.text()
    assert "pts_time" not in c.log.toPlainText()
    assert not c.pause.isEnabled()
    assert not c.stop.isEnabled()
    assert c.cancel.isEnabled()
    c.preview.setChecked(not c.preview.isChecked())
    assert not c.follow_timer.isActive()
    if close:
        c.window.close()
    else:
        c.cancel.click()
    qtbot.waitUntil(lambda: not c.running, timeout=3000)
    assert not c.detecting
    assert c.output.read_bytes() == b"previous export"
    assert [(s.start, s.end) for s in c.segments] == [(0, 3), (3, 6)]
    assert c.progress_text.text() == "Scene detection canceled"


def test_metadata_probe_keeps_event_loop_responsive(
    controller, qtbot, source, monkeypatch
):
    c = controller
    start = c.probe.start
    ticks = []

    def delayed_probe(program, arguments):
        start(
            sys.executable,
            [
                "-c",
                'import time; time.sleep(0.4); print(\'{"streams":[{"width":320,"height":240}]}\')',
            ],
        )

    monkeypatch.setattr(c.probe, "start", delayed_probe)
    c.paths = [source]
    c.load(0)
    assert not c.ready
    assert not c.open_button.isEnabled()
    QTimer.singleShot(20, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks))
    assert c.loading
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert not c.loading


def test_gpu_probe_keeps_event_loop_responsive(controller, qtbot, source, monkeypatch):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, c.player.duration() / 1000)])
    c.encoder.setCurrentIndex(c.encoder.findData("auto"))
    c.compiled_encoders = "hevc_nvenc"
    start = c.gpu_probe.start
    selected = []
    ticks = []

    def delayed_probe(program, arguments):
        start(
            sys.executable,
            ["-c", 'import time; time.sleep(0.4); print(\'[{"Name":"NVIDIA"}]\')'],
        )

    monkeypatch.setattr(c.gpu_probe, "start", delayed_probe)
    monkeypatch.setattr(c, "export_with_encoder", selected.append)
    c.export()
    assert not c.export_button.isEnabled()
    QTimer.singleShot(20, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks))
    assert c.resolving_encoder
    qtbot.waitUntil(lambda: bool(selected))
    assert selected == ["hevc_nvenc"]
    assert not c.resolving_encoder


def test_numeric_lock_and_preset(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, c.player.duration() / 1000)])
    c.set_rect((0, 0, 160, 120))
    c.lock.setChecked(True)
    c.fields[2].setValue(80)
    assert c.rect()[2:] == (80, 60)
    c.fields[0].setValue(95)
    assert c.rect()[0] == 240
    c.wheel.setChecked(True)
    c.fit()


def test_close_releases_video(controller, qtbot, source, tmp_path):
    import shutil

    video = tmp_path / "close-test.mp4"
    shutil.copyfile(source, video)
    controller.paths = [video]
    controller.load(0)
    qtbot.waitUntil(lambda: controller.ready, timeout=15000)
    controller.window.close()
    assert controller.player.source().isEmpty()
    video.rename(tmp_path / "released.mp4")


def test_all_stock_handles_preserve_locked_ratio(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, c.player.duration() / 1000)])
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
    c.replace_segments([(0, c.player.duration() / 1000)])
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
    c.replace_segments([(0, c.player.duration() / 1000)])
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
@pytest.mark.parametrize("segmented", [False, True])
def test_pause_resume_and_interrupt(
    controller, qtbot, source, monkeypatch, finish, segmented
):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    c.replace_segments([(0, 4), (4, 8)] if segmented else [(0, 8)])
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
    assert c.export_index == 0
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
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    c.replace_segments([(0, c.player.duration() / 1000)])
    c.advance.setChecked(True)
    c.auto.setChecked(True)
    c.auto_delay.setValue(30)
    c.export()
    qtbot.waitUntil(lambda: c.index == 1 and c.ready, timeout=15000)
    assert c.count_timer.isActive()
    c.count_cancelled()
    assert not c.count_timer.isActive()
    c.countdown("export", 1)
    qtbot.waitUntil(lambda: c.running, timeout=5000)
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.progress_text.text() == "Complete — 1 segments saved"


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
    qtbot.waitUntil(lambda: c.ready and c.player.duration() >= 1000, timeout=15000)
    c.replace_segments([(0, 1)])
    assert c.width == 640
    assert c.fields[2].value() == 320
    c.set_rect((160, 0, 320, 240))
    c.rotate(turns)
    c.square.setChecked(True)
    c.export()
    assert c.job.rect == rect
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.progress_text.text() == "Complete — 1 segments saved"
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
    qtbot.waitUntil(lambda: c.ready and c.player.duration() >= 1000, timeout=15000)
    assert (c.width, c.height) == (240, 320)
    assert c.video.boundingRect().width() == 240
    assert c.video.boundingRect().height() == 320
    c.window.grab().save(str(tmp_path / "rotated-preview.png"))
    assert (c.fields[2].value(), c.fields[3].value()) == (240, 320)
    c.replace_segments([(0, 1)])
    c.export()
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.progress_text.text() == "Complete — 1 segments saved"


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
@pytest.mark.parametrize("module", ["fastvideocropper", "fastvideocropper.installed"])
def test_explorer_install_lifecycle(controller, qtbot, monkeypatch, exit_code, module):
    c = controller
    c.launcher_module = module
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
    expected = ["-I", "-m", module, "--install-explorer"]
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
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("folder_path", "previous folder")
    settings.sync()
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
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


def test_preferences_restored_from_config_file(controller, qtbot, source, tmp_path):
    c = controller
    assert Path(c.settings.fileName()) == tmp_path / "settings.ini"
    assert c.settings.format() == QSettings.Format.IniFormat
    checkboxes = [
        "mute",
        "zoom",
        "notify",
        "preview",
        "wheel",
        "square",
        "advance",
        "auto",
        "quit_done",
    ]
    expected = {}
    for name in checkboxes:
        control = getattr(c, name)
        control.setChecked(not control.isChecked())
        expected[name] = control.isChecked()
    c.folder.setText(str(tmp_path))
    c.encoder.setCurrentIndex(c.encoder.findData("auto"))
    c.device.setValue(2)
    c.auto_delay.setValue(12)
    c.quit_delay.setValue(45)
    c.tabs.setCurrentIndex(1)
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 8)])
    c.rotate(1)
    c.set_rect((10, 20, 100, 200))
    c.lock.setChecked(True)

    def configure_detection():
        dialog = QApplication.activeModalWidget()
        threshold, minimum = dialog.findChildren(QDoubleSpinBox)
        step, threads = dialog.findChildren(QSpinBox)
        threshold.setValue(0.12)
        minimum.setValue(0.5)
        step.setValue(3)
        threads.setValue(2)
        dialog.reject()

    QTimer.singleShot(20, configure_detection)
    c.detect_action.trigger()
    c.window.close()
    restored = app.Application()
    qtbot.addWidget(restored.window)
    restored.window.show()
    for name, value in expected.items():
        assert getattr(restored, name).isChecked() == value
    assert restored.audio.isMuted() == expected["mute"]
    assert restored.folder.text() == str(tmp_path)
    assert restored.encoder.currentData() == "auto"
    assert restored.device.value() == 2
    assert restored.auto_delay.value() == 12
    assert restored.quit_delay.value() == 45
    assert restored.tabs.currentIndex() == 1
    assert restored.settings.contains("mainWindow/geometry")
    assert restored.settings.contains("mainWindow/state")
    assert restored.settings.contains("mainWindow/splitterState")
    assert not {"geometry", "turns", "preset", "centered", "lock"}.intersection(
        restored.settings.allKeys()
    )
    restored.paths = [source]
    restored.load(0)
    qtbot.waitUntil(lambda: restored.ready, timeout=15000)
    assert restored.segments == []
    assert restored.turns == 0
    assert restored.rect() == (0, 0, 320, 240)
    assert not restored.lock.isChecked()

    def verify_detection():
        dialog = QApplication.activeModalWidget()
        threshold, minimum = dialog.findChildren(QDoubleSpinBox)
        step, threads = dialog.findChildren(QSpinBox)
        assert (threshold.value(), minimum.value(), step.value(), threads.value()) == (
            0.12,
            0.5,
            3,
            2,
        )
        dialog.reject()

    QTimer.singleShot(20, verify_detection)
    restored.detect_action.trigger()
    restored.window.close()


def test_crop_settings_stay_with_video(controller, qtbot, source, tmp_path):
    import shutil

    other = tmp_path / "other.mp4"
    shutil.copyfile(source, other)
    c = controller
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 8)])
    c.rotate(1)
    c.set_rect((10, 20, 100, 200))
    c.lock.setChecked(True)
    c.load(1)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.turns == 0
    assert c.rect() == (0, 0, 320, 240)
    assert not c.lock.isChecked()
    c.replace_segments([(0, 8)])
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.turns == 1
    assert c.rect() == (10, 20, 100, 200)
    assert c.lock.isChecked()


def test_segment_selection_remains_visible(controller, qtbot, source, tmp_path):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 2), (2, 8)])
    for index in (1, 0):
        item = c.segment_list.item(index)
        qtbot.mouseClick(
            c.segment_list.viewport(),
            Qt.MouseButton.LeftButton,
            pos=c.segment_list.visualItemRect(item).center(),
        )
        c.seek.setFocus()
        assert c.active_segment == index
        assert item.isSelected()
        assert item.font().bold()
        assert not c.segment_list.item(1 - index).font().bold()
        selected = c.segment_regions[index]
        other = c.segment_regions[1 - index]
        assert selected.brush.color().alpha() > other.brush.color().alpha()
        selected.setMouseHover(True)
        assert selected.currentBrush == selected.brush
        selected.setMouseHover(False)
        qtbot.wait(50)
        assert c.crop_summary.height() >= c.crop_summary.heightForWidth(
            c.crop_summary.width()
        )
        c.window.grab().save(str(tmp_path / f"selection-{index}.png"))
    c.running = True
    c.update_enabled()
    assert c.segment_list.currentItem().font().bold()
    c.running = False
    c.update_enabled()


def test_cached_segment_dimensions_follow_source(controller, qtbot, source, tmp_path):
    other = tmp_path / "small.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source),
            "-vf",
            "scale=160:120",
            str(other),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    c = controller
    c.paths = [source, other]
    for index in (0, 1):
        c.load(index)
        qtbot.waitUntil(lambda: c.ready, timeout=15000)
        c.replace_segments([(0, 2), (2, 8)])
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert "Crop 320 × 240" in c.segment_list.item(1).text()
    c.load(1)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert "Crop 160 × 120" in c.segment_list.item(1).text()


@pytest.mark.parametrize("trigger", ["menu", "button"])
def test_split_segment_in_place(controller, qtbot, source, trigger):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert not c.split_segment_action.isEnabled()
    c.replace_segments([(0, 2), (2, 6), (6, 8)])
    c.segment_list.setCurrentRow(1)
    c.rotate(1)
    c.set_rect((10, 20, 100, 200))
    c.lock.setChecked(True)
    original = c.segments[1]
    before, after = c.segments[0], c.segments[2]
    assert not c.split_segment_action.isEnabled()
    c.seek.setValue(4500)
    assert c.split_segment_action.isEnabled()
    assert c.split_segment_button.isEnabled()
    if trigger == "menu":
        c.split_segment_action.trigger()
    else:
        qtbot.mouseClick(c.split_segment_button, Qt.MouseButton.LeftButton)
    assert [(s.start, s.end) for s in c.segments] == [
        (0, 2),
        (2, 4.5),
        (4.5, 6),
        (6, 8),
    ]
    assert c.segments[0] is before
    assert c.segments[3] is after
    for segment in c.segments[1:3]:
        assert (segment.rect, segment.turns, segment.preset, segment.locked) == (
            original.rect,
            original.turns,
            original.preset,
            original.locked,
        )
    assert c.segment_list.currentRow() == c.active_segment == 2
    assert c.player.position() == 4500
    assert not c.split_segment_button.isEnabled()
    assert len(c.segment_regions) == c.segment_list.count() == 4
    c.set_rect((20, 30, 80, 160))
    assert c.segments[1].rect == original.rect
    assert c.segments[2].rect != original.rect
    c.seek.setValue(5000)
    c.running = True
    c.update_enabled()
    assert not c.split_segment_action.isEnabled()
    c.running = False
    c.update_enabled()
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert [(s.start, s.end) for s in c.segments] == [
        (0, 2),
        (2, 4.5),
        (4.5, 6),
        (6, 8),
    ]


@pytest.mark.parametrize("placement", ["left", "floating", "hidden"])
def test_segments_dock_layout_persistence_and_reset(controller, qtbot, placement):
    c = controller
    dock = c.segments_dock
    toggle = dock.toggleViewAction()
    view_menu = next(
        action.menu()
        for action in c.window.menuBar().actions()
        if action.text() == "&View"
    )
    assert view_menu.actions() == [
        toggle,
        view_menu.actions()[1],
        c.reset_layout_action,
    ]
    assert view_menu.actions()[1].isSeparator()
    assert toggle.isCheckable() and toggle.isChecked()
    assert c.window.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea
    for widget in (
        c.segment_list,
        c.segment_summary,
        c.detect_button,
        c.clear_segments_button,
        c.split_segment_button,
    ):
        assert dock.isAncestorOf(widget)
    assert not dock.isAncestorOf(c.tabs)
    dock.close()
    assert not toggle.isChecked()
    toggle.trigger()
    assert dock.isVisible()
    c.window.resize(1400, 900)
    c.window.move(60, 60)
    c.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    if placement == "floating":
        dock.setFloating(True)
        dock.resize(420, 500)
        dock.move(120, 120)
    elif placement == "hidden":
        toggle.trigger()
    c.splitter.setSizes([600, 400])
    qtbot.wait(50)
    geometry = c.window.geometry()
    dock_geometry = dock.geometry()
    sizes = c.splitter.sizes()
    c.window.close()

    restored = app.Application()
    qtbot.addWidget(restored.window)
    restored.window.show()
    qtbot.wait(50)
    dock = restored.segments_dock
    assert restored.window.geometry() == geometry
    assert restored.window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert dock.isFloating() == (placement == "floating")
    assert dock.isVisible() == (placement != "hidden")
    assert dock.toggleViewAction().isChecked() == (placement != "hidden")
    assert restored.splitter.sizes() == sizes
    if placement == "floating":
        assert dock.geometry() == dock_geometry
    restored.reset_layout_action.trigger()
    assert not dock.isFloating()
    assert dock.isVisible()
    assert dock.toggleViewAction().isChecked()
    assert restored.window.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert restored.window.geometry() == geometry
    restored.window.close()

    reset = app.Application()
    qtbot.addWidget(reset.window)
    reset.window.show()
    assert not reset.segments_dock.isFloating()
    assert reset.segments_dock.isVisible()
    assert (
        reset.window.dockWidgetArea(reset.segments_dock)
        == Qt.DockWidgetArea.RightDockWidgetArea
    )
    reset.window.close()


def test_hidden_segments_stay_linked_to_timeline(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 2), (2, 8)])
    c.segments_dock.hide()
    c.seek_segment(4500)
    assert c.segment_list.currentRow() == c.active_segment == 1
    c.split_segment_action.trigger()
    assert c.active_segment == 2
    assert c.segment_list.count() == len(c.segment_regions) == 3
    c.segments_dock.toggleViewAction().trigger()
    assert c.segment_list.currentRow() == 2
    c.segments_dock.setFloating(True)
    c.segment_list.setFocus()
    qtbot.keyClick(c.segment_list, Qt.Key.Key_Home)
    assert c.active_segment == 0
    c.clear_segments_button.click()
    assert c.segment_list.count() == len(c.segment_regions) == 0
    assert not c.export_button.isEnabled()
