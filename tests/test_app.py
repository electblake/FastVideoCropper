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
    QGridLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
)

from fastvideocropper import app


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(
        app.VideoFileDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )
    controller = app.Application()
    qtbot.addWidget(controller.window)
    controller.window.show()
    yield controller
    controller.window.close()


@pytest.mark.parametrize("placement", ["docked", "floating", "hidden"])
def test_segment_and_export_button_grid(controller, qtbot, source, placement):
    c = controller
    parent = c.export_button.parentWidget()
    layout = parent.layout()
    grid = next(
        layout.itemAt(i).layout()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).layout(), QGridLayout)
        and layout.itemAt(i).layout().indexOf(c.add_segment_button) >= 0
    )
    buttons = [
        c.add_segment_button,
        c.split_segment_button,
        c.merge_segments_button,
        c.detect_button,
        c.clear_segments_button,
        c.export_button,
        c.pause,
        c.stop,
        c.cancel,
    ]
    assert grid.count() == 8
    grid_buttons = [button for button in buttons if button is not c.export_button]
    for i, button in enumerate(grid_buttons):
        assert grid.itemAtPosition(i // 3, i % 3).widget() is button
        assert button.parentWidget() is parent
        assert not c.segments_dock.isAncestorOf(button)
    export_index = layout.indexOf(c.export_button)
    assert layout.itemAt(export_index - 1).layout() is grid
    assert layout.itemAt(export_index + 1).layout().indexOf(c.remember_crop) >= 0
    if placement == "floating":
        c.segments_dock.setFloating(True)
    elif placement == "hidden":
        c.segments_dock.hide()
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.add_segment_button.click()
    c.seek_segment(3000)
    c.split_segment_button.click()
    c.seek_segment(4000)
    assert len(c.segments) == 2
    for button in buttons:
        assert button.isVisible()
        assert button.width() >= button.minimumSizeHint().width()
    assert c.export_button.width() == grid.geometry().width()
    assert c.export_button.height() >= 44
    assert c.export_button.height() > c.add_segment_button.height()
    for state in ("loading", "running", "resolving_encoder"):
        setattr(c, state, True)
        c.update_enabled()
        assert all(not button.isEnabled() for button in buttons[:6])
        assert c.cancel.isEnabled() == (state == "running")
        assert c.pause.isEnabled() == (state == "running")
        assert c.stop.isEnabled() == (state == "running")
        setattr(c, state, False)
    c.update_enabled()
    assert all(button.isEnabled() for button in buttons[:6])
    c.merge_segments_button.click()
    assert len(c.segments) == 1
    c.clear_segments_button.click()
    assert not c.segments
    assert not c.export_button.isEnabled()


@pytest.mark.parametrize("trigger", ["button", "menu"])
def test_merge_similar_segments(controller, qtbot, source, trigger):
    c = controller
    assert not c.merge_segments_action.isEnabled()
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 8)])
    c.segment_list.setCurrentRow(3)
    c.set_rect((160, 0, 160, 240))
    c.segment_list.setCurrentRow(6)
    c.seek.setValue(6500)
    position = c.player.position()
    original = list(c.segments)
    assert c.merge_segments_action.isEnabled()
    assert c.merge_segments_button.isEnabled()
    c.loading = True
    c.update_enabled()
    assert not c.merge_segments_action.isEnabled()
    assert not c.merge_segments_button.isEnabled()
    c.loading = False
    c.update_enabled()
    if trigger == "menu":
        c.merge_segments_action.trigger()
    else:
        c.merge_segments_button.click()
    assert [(s.start, s.end) for s in c.segments] == [(0, 3), (3, 4), (4, 8)]
    assert all(s is original[i] for s, i in zip(c.segments, (0, 3, 4)))
    assert c.source_segments[source] is c.segments
    assert c.active_segment == c.segment_list.currentRow() == 2
    assert c.player.position() == position
    assert c.segment_list.count() == len(c.segment_regions) == 3
    assert c.export_button.text() == "Export 3 segments"
    assert not c.merge_segments_action.isEnabled()
    assert not c.merge_segments_button.isEnabled()
    c.merge_segments()
    assert [(s.start, s.end) for s in c.segments] == [(0, 3), (3, 4), (4, 8)]
    c.set_rect((160, 0, 160, 240))
    assert c.merge_segments_action.isEnabled()
    c.merge_segments_button.click()
    assert [(s.start, s.end) for s in c.segments] == [(0, 3), (3, 8)]
    assert c.active_segment == 1


@pytest.mark.parametrize("size", [(1200, 800), (900, 700)])
def test_process_options_layout_keyboard_and_persistence(
    controller, qtbot, tmp_path, size
):
    c = controller
    c.window.resize(*size)
    c.window.activateWindow()
    qtbot.waitUntil(c.window.isActiveWindow)
    parent = c.export_button.parentWidget()
    layout = parent.layout()
    buttons = layout.itemAt(layout.count() - 2).layout()
    options = layout.itemAt(layout.count() - 1).layout()
    assert isinstance(buttons, QGridLayout)
    assert isinstance(options, QGridLayout)
    assert buttons.indexOf(c.export_button) >= 0
    assert options.count() == 5
    preferences = [
        ("remember_crop", "remember_crop"),
        ("auto_segment", "auto_segment"),
        ("advance", "advance"),
        ("auto", "auto"),
        ("quit_done", "quit"),
    ]
    c.remember_crop.setFocus()
    for index, (name, key) in enumerate(preferences):
        control = getattr(c, name)
        assert options.itemAtPosition(index // 2, index % 2).widget() is control
        assert control.parentWidget() is parent
        assert control.isVisible()
        assert control.width() >= control.minimumSizeHint().width()
        assert parent.rect().contains(control.geometry())
        assert control.y() > c.cancel.geometry().bottom()
        assert control.hasFocus()
        qtbot.keyClick(control, Qt.Key.Key_Space)
        assert control.isChecked()
        assert c.settings.value(key, False, bool)
        qtbot.keyClick(control, Qt.Key.Key_Tab)
    c.window.grab().save(str(tmp_path / "process-controls.png"))
    c.window.close()
    restored = app.Application()
    qtbot.addWidget(restored.window)
    restored.window.show()
    for name, _ in preferences:
        assert getattr(restored, name).isChecked()
        assert (
            getattr(restored, name).parentWidget()
            is restored.export_button.parentWidget()
        )
    restored.window.close()


def test_merge_ignores_editing_settings_and_exports(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    c.replace_segments([(0, 2), (2, 8)])
    c.set_preset("Original")
    c.padding_fields[0].setValue(-4)
    c.segment_list.setCurrentRow(1)
    c.rotate(1)
    c.full_frame()
    c.padding_fields[0].setValue(-4)
    c.set_preset("Custom")
    c.lock.setChecked(True)
    c.seek.setValue(4000)
    first = c.segments[0]
    assert c.segments[1].rotation != first.rotation
    assert c.segments[1].preset != first.preset
    assert c.segments[1].locked != first.locked
    assert c.merge_segments_button.isEnabled()
    c.merge_segments_button.click()
    assert c.segments == [first]
    assert (first.start, first.end) == (0, 8)
    assert c.player.position() == 4000
    assert c.rotation == first.rotation == 0
    assert c.selected_preset == first.preset
    assert c.lock.isChecked() == first.locked
    c.export_with_encoder("libx265")
    assert not c.merge_segments_action.isEnabled()
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.window.statusBar().currentMessage() == "Complete — 1 segments saved"
    metadata = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(c.output)],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    )
    video, audio = metadata["streams"]
    assert (video["width"], video["height"]) == (312, 240)
    assert int(video["nb_frames"]) == 80
    assert audio["codec_name"] == "aac"


@pytest.mark.parametrize("trigger", ["button", "menu"])
def test_add_full_timeline_segment(controller, qtbot, source, trigger):
    c = controller
    status = c.window.statusBar()
    assert type(status) is QStatusBar
    assert status.isVisible() and status.isEnabled()
    assert not c.add_segment_button.isEnabled()
    assert not c.add_segment_action.isEnabled()
    segment_menu = next(
        action.menu()
        for action in c.window.menuBar().actions()
        if action.text() == "&Segment"
    )
    assert c.add_segment_action in segment_menu.actions()
    assert c.window.centralWidget().isAncestorOf(c.export_button)
    assert c.add_segment_button.parentWidget() is c.export_button.parentWidget()
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    for state in ("loading", "running", "resolving_encoder"):
        setattr(c, state, True)
        c.update_enabled()
        assert not c.add_segment_button.isEnabled()
        assert not c.add_segment_action.isEnabled()
        setattr(c, state, False)
    c.update_enabled()
    c.seek_segment(3000)
    if trigger == "button":
        qtbot.mouseClick(c.add_segment_button, Qt.MouseButton.LeftButton)
    else:
        c.add_segment_action.trigger()
    assert [(s.start, s.end) for s in c.segments] == [(0, 8)]
    assert c.source_segments[source] is c.segments
    assert c.segment_list.count() == len(c.segment_regions) == 1
    assert c.segment_regions[0].getRegion() == (0, 8)
    assert c.active_segment == c.segment_list.currentRow() == 0
    assert c.rect() == (0, 0, 320, 240)
    assert c.crop_page.isEnabled() and c.export_button.isEnabled()
    assert status.currentMessage() == "Added segment covering the full timeline"
    c.set_rect((20, 30, 160, 120))
    c.seek_segment(3000)
    c.split_segment_action.trigger()
    originals = list(c.segments)
    if trigger == "button":
        qtbot.mouseClick(c.add_segment_button, Qt.MouseButton.LeftButton)
    else:
        c.add_segment_action.trigger()
    assert c.segments == originals
    assert all(a is b for a, b in zip(c.segments, originals))
    assert c.active_segment == 1
    assert c.player.position() == 3000
    assert c.rect() == (20, 30, 160, 120)
    assert status.currentMessage() == "No segment added — segments already exist"
    c.clear_segments_action.trigger()
    c.add_segment_button.click()
    assert [(s.start, s.end) for s in c.segments] == [(0, 8)]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert [(s.start, s.end) for s in c.segments] == [(0, 8)]
    c.update_busy(True)
    assert not c.add_segment_button.isEnabled()
    assert not c.export_button.isEnabled()
    c.update_busy(False)
    assert c.add_segment_button.isEnabled() and c.export_button.isEnabled()


@pytest.mark.parametrize("remember", [False, True])
@pytest.mark.parametrize("trigger", ["open", "next", "export_complete"])
def test_automatically_create_first_segment(
    controller, qtbot, source, tmp_path, monkeypatch, remember, trigger
):
    c = controller
    other = tmp_path / "next.mp4"
    other.write_bytes(source.read_bytes())
    assert not c.auto_segment.isChecked()
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and not c.load_timer.isActive(), timeout=15000)
    assert not c.segments
    c.auto_segment.setChecked(True)
    assert not c.segments
    c.remember_crop.setChecked(remember)
    c.add_segment_button.click()
    c.rotate(1)
    c.set_rect((20, 30, 120, 120))
    c.set_preset("Square")
    c.lock.setChecked(True)
    c.padding_fields[0].setValue(7)
    c.padding_fields[1].setValue(-3)
    if trigger == "open":
        monkeypatch.setattr(
            app.VideoFileDialog, "selectedFiles", lambda self: [str(other)]
        )
        c.open_action.trigger()
    elif trigger == "next":
        c.next.click()
    else:
        c.advance.setChecked(True)
        c.export_with_encoder("libx265")
    qtbot.waitUntil(
        lambda: c.ready and c.paths[c.index] == other and bool(c.segments),
        timeout=30000,
    )
    assert [(s.start, s.end) for s in c.segments] == [(0, 8)]
    assert c.rect() == ((20, 30, 120, 120) if remember else (0, 0, 320, 240))
    assert c.segments[0].rotation == (1 if remember else 0)
    assert c.segments[0].preset == ("Square" if remember else "Custom")
    assert c.segments[0].locked == remember
    assert (c.segments[0].padding_x, c.segments[0].padding_y) == (
        (7, -3) if remember else (0, 0)
    )
    assert c.segments[0].rect == (
        (20 / 240, 30 / 320, 120 / 240, 120 / 320) if remember else (0, 0, 1, 1)
    )
    assert c.segment_list.count() == len(c.segment_regions) == 1
    assert c.active_segment == c.segment_list.currentRow() == 0
    assert c.export_button.isEnabled()
    assert (
        c.window.statusBar().currentMessage()
        == "Added segment covering the full timeline"
    )
    segment = c.segments[0]
    c.load(c.index)
    qtbot.waitUntil(lambda: c.ready and not c.load_timer.isActive(), timeout=15000)
    assert c.segments == [segment]
    assert c.segments[0] is segment
    assert (
        c.window.statusBar().currentMessage()
        == "No segment added — segments already exist"
    )
    c.window.close()

    restored = app.Application()
    qtbot.addWidget(restored.window)
    restored.window.show()
    assert restored.auto_segment.isChecked()
    restored.paths = [other]
    restored.load(0)
    qtbot.waitUntil(lambda: restored.ready and bool(restored.segments), timeout=15000)
    assert [(s.start, s.end) for s in restored.segments] == [(0, 8)]
    restored.clear_segments_button.click()
    restored.auto_segment.setChecked(False)
    restored.load(0)
    qtbot.waitUntil(lambda: restored.ready, timeout=15000)
    assert not restored.segments
    assert not restored.settings.value("auto_segment", type=bool)
    restored.window.close()


@pytest.mark.parametrize("remember", [False, True])
def test_remember_crop_between_files_and_sessions(
    controller, qtbot, source, tmp_path, remember
):
    c = controller
    other = tmp_path / "next.mp4"
    other.write_bytes(source.read_bytes())
    layout = c.advance.parentWidget().layout()
    layout = layout.itemAt(layout.count() - 1).layout()
    assert isinstance(layout, QGridLayout)
    assert layout.indexOf(c.remember_crop) + 1 == layout.indexOf(c.auto_segment)
    assert layout.indexOf(c.auto_segment) + 1 == layout.indexOf(c.advance)
    assert not c.remember_crop.isChecked()
    c.remember_crop.setChecked(remember)
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.add_segment_button.click()
    c.rotate(1)
    c.set_rect((20, 30, 120, 120))
    c.set_preset("Square")
    c.lock.setChecked(True)
    c.padding_fields[0].setValue(7)
    c.padding_fields[1].setValue(-3)
    c.next.click()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.settings.value("remember_crop", type=bool) == remember
    assert c.settings.value("crop/turns", type=int) == 1
    assert c.settings.value("crop/preset") == "Square"
    assert c.settings.value("crop/locked", type=bool)
    assert c.settings.value("crop/padding_x", type=int) == 7
    assert c.settings.value("crop/padding_y", type=int) == -3
    assert not c.segments
    assert c.rect() == ((20, 30, 120, 120) if remember else (0, 0, 320, 240))
    assert c.rotation == (1 if remember else 0)
    assert c.selected_preset == ("Square" if remember else "Custom")
    assert c.lock.isChecked() == remember
    assert [f.value() for f in c.padding_fields] == ([7, -3] if remember else [0, 0])
    c.add_segment_button.click()
    assert c.segments[0].rotation == c.rotation
    assert c.segments[0].padding_x == (7 if remember else 0)
    c.set_rect((0, 0, 60, 60))
    c.previous.click()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rect() == (20, 30, 120, 120)
    assert c.rotation == 1
    c.window.close()

    restored = app.Application()
    qtbot.addWidget(restored.window)
    restored.window.show()
    assert restored.remember_crop.isChecked() == remember
    restored.paths = [other]
    restored.load(0)
    qtbot.waitUntil(lambda: restored.ready, timeout=15000)
    assert restored.rect() == ((20, 30, 120, 120) if remember else (0, 0, 320, 240))
    assert restored.rotation == (1 if remember else 0)
    assert restored.selected_preset == ("Square" if remember else "Custom")
    assert restored.lock.isChecked() == remember
    assert [f.value() for f in restored.padding_fields] == (
        [7, -3] if remember else [0, 0]
    )
    restored.window.close()


def test_remember_crop_different_dimensions_and_disable(
    controller, qtbot, source, tmp_path
):
    other = tmp_path / "wide.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=10:duration=1",
            "-c:v",
            "libx264",
            str(other),
        ],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    c = controller
    c.remember_crop.setChecked(True)
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.add_segment_button.click()
    c.rotate(1)
    c.set_rect((20, 30, 120, 120))
    c.set_preset("Square")
    c.lock.setChecked(True)
    c.next.click()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rect() == (30, 60, 180, 180)
    assert c.selected_preset == "Square"
    assert c.rotation == 1 and c.lock.isChecked()
    c.add_segment_button.click()
    assert c.segments[0].rect == (30 / 360, 60 / 640, 180 / 360, 180 / 640)
    c.clear_segments_button.click()
    c.remember_crop.setChecked(False)
    c.load(1)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rect() == (0, 0, 640, 360)
    assert c.rotation == 0 and not c.lock.isChecked()
    assert c.selected_preset == "Custom"


def test_pixel_padding_segments_preview_and_export(controller, qtbot, source, tmp_path):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1), (1, 2)])
    c.set_rect((40, 30, 160, 120))
    c.padding_fields[0].setValue(3)
    c.padding_fields[1].setValue(-5)
    assert c.rect() == (40, 30, 160, 120)
    assert c.padding_outline.rect().getRect() == (37, 35, 166, 110)
    assert c.padding_outline.isVisible()
    assert c.masks[0].rect().height() == 35
    c.rotate(1)
    assert [field.value() for field in c.padding_fields] == [-5, 3]
    assert c.padding_outline.rect().getRect() == (95, 37, 110, 166)
    c.rotate(3)
    c.segment_list.setCurrentRow(1)
    assert [field.value() for field in c.padding_fields] == [0, 0]
    assert not c.padding_outline.isVisible()
    c.segment_list.setCurrentRow(0)
    assert [field.value() for field in c.padding_fields] == [3, -5]
    c.player.setPosition(500)
    c.split_segment()
    assert [(s.padding_x, s.padding_y) for s in c.segments] == [
        (3, -5),
        (3, -5),
        (0, 0),
    ]
    qtbot.wait(100)
    c.window.grab().save(str(tmp_path / "padding-preview.png"))
    c.export_with_encoder("libx265")
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.export_jobs[0].rect == (37, 35, 166, 110)
    assert [job.exact_crop for job in c.export_jobs] == [True, True, False]
    for job, size in zip(c.export_jobs, [(166, 110), (166, 110), (320, 240)]):
        metadata = json.loads(
            subprocess.check_output(
                [
                    c.ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "json",
                    str(job.output),
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        )
        video = metadata["streams"][0]
        assert (video["width"], video["height"]) == size
    c.segment_list.setCurrentRow(0)
    c.width = 640
    c.set_rect((80, 30, 320, 120))
    assert c.padding_outline.rect().getRect() == (74, 35, 332, 110)
    c.padding_fields[0].setValue(100)
    c.fit()
    assert c.view.viewRect().contains(c.padding_outline.rect())


def test_padding_resets_for_new_video_and_restores_on_return(
    controller, qtbot, source, tmp_path
):
    other = tmp_path / "other.mp4"
    other.write_bytes(source.read_bytes())
    c = controller
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1)])
    c.padding_fields[0].setValue(-7)
    c.padding_fields[1].setValue(-3)
    c.load(1)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1)])
    assert [field.value() for field in c.padding_fields] == [0, 0]
    assert (c.segments[0].padding_x, c.segments[0].padding_y) == (0, 0)
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert [field.value() for field in c.padding_fields] == [-7, -3]


def test_padding_edit_preserves_manual_zoom(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1)])
    c.set_rect((140, 100, 40, 40))
    c.view.scaleBy((0.5, 0.5))
    view_rect = c.view.viewRect()
    c.padding_fields[1].setValue(100)
    assert c.view.viewRect() == view_rect


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
    assert c.rect()[2:] == (240, 240)
    c.center()
    assert c.rect() == (40, 0, 240, 240)
    c.replace_segments([(2.3, 5.7)])
    c.window.grab().save(str(tmp_path / "window.png"))
    c.export()
    assert not c.next.isEnabled()
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.window.statusBar().currentMessage() == "Complete — 1 segments saved"
    assert source in c.done
    assert c.output.exists()
    c.load(1)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    assert c.rect() == (40, 0, 240, 240)


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
    assert "3.0 / 6.0 s scanned • 1 cuts found" in c.window.statusBar().currentMessage()

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
    c.detect_button.click()
    assert not c.detect_button.isEnabled()
    assert not c.open_action.isEnabled()
    qtbot.waitUntil(lambda: not c.detecting, timeout=15000)
    assert c.progress.value() == 100
    assert (
        c.window.statusBar().currentMessage() == "Scene detection complete — 3 segments"
    )
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
    assert c.rotation == 0
    assert c.rect() == (0, 0, 320, 240)
    assert not c.lock.isChecked()
    assert (c.segments[c.active_segment].start, c.segments[c.active_segment].end) == (
        2,
        4,
    )
    c.set_rect((40, 50, 100, 80))
    c.segment_list.setCurrentRow(0)
    assert c.rotation == 1
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
    saved = [(s.rect, s.rotation, s.preset, s.locked) for s in c.segments]
    observed = []

    def capture_export_ui():
        observed.append(
            (
                c.segment_list.currentRow(),
                c.rect(),
                c.rotation,
                c.lock.isChecked(),
                [field.value() for field in c.fields[2:]],
                c.player.isPlaying(),
            )
        )

    c.process.started.connect(capture_export_ui)
    c.export()
    assert not c.clear_segments_action.isEnabled()
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.window.statusBar().currentMessage() == "Complete — 2 segments saved"
    assert source in c.done
    assert len(observed) == 2
    for index, (row, rect, rotation, locked, size, playing) in enumerate(observed):
        assert row == index
        assert rect == [(20, 30, 160, 120), (10, 20, 100, 200)][index]
        assert rotation == index
        assert locked == saved[index][3]
        assert size == list(rect[2:])
        assert not playing
    assert [(s.rect, s.rotation, s.preset, s.locked) for s in c.segments] == saved
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


def test_export_preview_keeps_segment_geometry_during_progress(
    controller, qtbot, source, monkeypatch, tmp_path
):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 8000, timeout=15000)
    c.replace_segments([(0, 3), (3, 6)])
    c.set_rect((20, 30, 160, 120))
    c.padding_fields[0].setValue(-6)
    c.segment_list.setCurrentRow(1)
    c.rotate(1)
    c.set_rect((10, 20, 100, 200))
    c.padding_fields[0].setValue(4)
    c.padding_fields[1].setValue(-2)
    c.lock.setChecked(True)
    c.preview.setChecked(True)
    saved = [vars(segment).copy() for segment in c.segments]
    arguments = app.Export.arguments

    def realtime_arguments(job):
        args = arguments(job)
        return ["-re", *args[:-1], "-tune", "zerolatency", args[-1]]

    monkeypatch.setattr(app.Export, "arguments", realtime_arguments)
    c.export_with_encoder("libx265")
    for index, expected in enumerate([(20, 30, 160, 120), (10, 20, 100, 200)]):
        qtbot.waitUntil(
            lambda index=index: (
                c.export_index == index
                and c.player.position() > (c.segments[index].start + 0.5) * 1000
            ),
            timeout=15000,
        )
        assert c.running
        assert c.active_segment == c.segment_list.currentRow() == index
        assert c.rect() == expected
        assert c.rotation == index
        assert c.lock.isChecked() == saved[index]["locked"]
        assert [field.value() for field in c.fields[2:]] == list(expected[2:])
        x, y, width, height = c.job.rect
        assert c.padding_outline.rect().getRect() == (x, y, width, height)
        assert [mask.rect().getRect() for mask in c.masks] == [
            (0, 0, c.width, y),
            (0, y + height, c.width, c.height - y - height),
            (0, y, x, height),
            (x + width, y, c.width - x - width, height),
        ]
        c.window.grab().save(str(tmp_path / f"export-preview-{index}.png"))
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert [vars(segment) for segment in c.segments] == saved


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
    saved = [(s.rect, s.rotation, s.locked) for s in c.segments]

    for position, index in [(1500, 0), (2000, 1), (5750, 1), (0, 0), (8000, 1)]:
        c.seek.setValue(position)
        assert c.segment_list.currentRow() == index
        assert c.active_segment == index
        assert c.player.position() == position
        assert c.rotation == saved[index][1]
        assert c.lock.isChecked() == saved[index][2]
        assert c.rect() == [(20, 30, 160, 120), (10, 20, 100, 200)][index]
    assert [(s.rect, s.rotation, s.locked) for s in c.segments] == saved


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
@pytest.mark.parametrize("auto_segment", [False, True])
def test_detection_progress_and_cancel(
    controller, qtbot, scene_video, monkeypatch, tmp_path, close, auto_segment
):
    c = controller
    c.paths = [scene_video]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.auto_segment.setChecked(auto_segment)
    c.replace_segments([(0, 3), (3, 6)])
    c.output = tmp_path / "previous-output.mp4"
    c.output.write_bytes(b"previous export")
    start = c.process.start

    def realtime(program, arguments):
        arguments.insert(arguments.index("-i"), "-re")
        start(program, arguments)

    monkeypatch.setattr(c.process, "start", realtime)

    def confirm_replacement():
        dialog = QApplication.activeModalWidget()
        dialog.button(QMessageBox.StandardButton.Yes).click()

    QTimer.singleShot(20, confirm_replacement)
    c.detect_segments(1, 0, framestep=30, threads=1)
    qtbot.waitUntil(lambda: c.progress.value() > 5, timeout=5000)
    assert c.detecting
    assert "0 cuts found" in c.window.statusBar().currentMessage()
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
    assert [(s.start, s.end) for s in c.segments] == ([(0, 6)] if auto_segment else [])
    assert c.segment_list.count() == len(c.segment_regions) == int(auto_segment)
    assert c.window.statusBar().currentMessage() == "Scene detection canceled"


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


@pytest.mark.parametrize("rotation", [0, 1, 2, 3])
def test_slice_buttons_center_and_preserve_saved_crop(
    controller, qtbot, source, rotation
):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 4), (4, 8)])
    c.rotate(rotation)
    buttons = {button.text(): button for button in c.window.findChildren(QPushButton)}
    left = buttons["1/2 Left"].mapToGlobal(QPointF(0, 0).toPoint())
    center = buttons["1/2 Center"].mapToGlobal(QPointF(0, 0).toPoint())
    right = buttons["1/2 Right"].mapToGlobal(QPointF(0, 0).toPoint())
    third = buttons["1/3 Center"].mapToGlobal(QPointF(0, 0).toPoint())
    assert left.x() < center.x() < right.x()
    assert left.y() == center.y() == right.y()
    assert center.x() == third.x()
    assert center.y() > third.y()
    for locked in (False, True):
        c.lock.setChecked(locked)
        for name, x, width in [
            ("1/2 Left", 0, 0.5),
            ("1/2 Center", 0.25, 0.5),
            ("1/2 Right", 0.5, 0.5),
            ("1/3 Left", 0, 1 / 3),
            ("1/3 Center", 1 / 3, 1 / 3),
            ("1/3 Right", 2 / 3, 1 / 3),
        ]:
            c.set_preset("Square")
            c.set_rect((10, 20, 80, 80))
            qtbot.mouseClick(buttons[name], Qt.MouseButton.LeftButton)
            assert c.rect() == pytest.approx(
                (x * c.width, 0, width * c.width, c.height)
            )
            assert c.selected_preset == "Custom"
            assert c.lock.isChecked() == locked
            assert c.segments[0].rect == pytest.approx((x, 0, width, 1))
        qtbot.mouseClick(buttons["1/2 Left"], Qt.MouseButton.LeftButton)
        qtbot.mouseClick(buttons["Center frame"], Qt.MouseButton.LeftButton)
        expected = c.rect()
        buttons["1/2 Center"].setFocus()
        qtbot.keyClick(buttons["1/2 Center"], Qt.Key.Key_Space)
        assert c.rect() == pytest.approx(expected)
        c.segment_list.setCurrentRow(1)
        c.segment_list.setCurrentRow(0)
        assert c.rect() == pytest.approx(expected)
        assert c.selected_preset == "Custom"


@pytest.mark.parametrize("rotation", [0, 1, 2, 3])
def test_ratio_presets_center_and_preserve_saved_position(
    controller, qtbot, source, tmp_path, rotation
):
    c = controller
    other = tmp_path / "next.mp4"
    other.write_bytes(source.read_bytes())
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 4), (4, 8)])
    c.rotate(rotation)
    for locked in (False, True):
        c.lock.setChecked(locked)
        c.set_rect((10, 20, 160, 120))
        for name in list(app.RATIOS) * 3:
            ratio = c.width / c.height if name == "Original" else app.RATIOS[name]
            qtbot.mouseClick(c.preset_buttons[name], Qt.MouseButton.LeftButton)
            x, y, w, h = c.rect()
            assert w / h == pytest.approx(ratio)
            assert max(w / c.width, h / c.height) == pytest.approx(1)
            assert x + w / 2 == pytest.approx(c.width / 2)
            assert y + h / 2 == pytest.approx(c.height / 2)
            assert c.selected_preset == name
            assert c.lock.isChecked() == locked
            assert c.segments[0].rect == pytest.approx(
                (x / c.width, y / c.height, w / c.width, h / c.height)
            )
    c.preset_buttons["9:16"].setFocus()
    c.set_rect((10, 20, 160, 120))
    qtbot.keyClick(c.preset_buttons["9:16"], Qt.Key.Key_Space)
    height = min(c.height, c.width * 16 / 9)
    width = height * 9 / 16
    assert c.rect() == pytest.approx(
        ((c.width - width) / 2, (c.height - height) / 2, width, height)
    )
    qtbot.keyClick(c.preset_buttons["9:16"], Qt.Key.Key_Space)
    assert c.rect() == pytest.approx(
        ((c.width - width) / 2, (c.height - height) / 2, width, height)
    )
    c.set_rect((10, 20, 67.5, 120))
    c.segment_list.setCurrentRow(1)
    c.segment_list.setCurrentRow(0)
    assert c.rect() == pytest.approx((10, 20, 67.5, 120))
    assert c.selected_preset == "9:16"
    c.apply_preset()
    assert c.rect() == pytest.approx((10, 20, 67.5, 120))
    c.load(1)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rect() == pytest.approx((10, 20, 67.5, 120))
    assert c.selected_preset == "9:16"


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


@pytest.mark.parametrize("advance", [False, True])
@pytest.mark.parametrize("quit_done", [False, True])
def test_final_export_unloads_video(
    controller, qtbot, source, tmp_path, advance, quit_done
):
    import shutil

    video = tmp_path / "export-test.mp4"
    shutil.copyfile(source, video)
    source = video
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 0.5), (0.5, 1)])
    c.advance.setChecked(advance)
    c.quit_done.setChecked(quit_done)
    c.quit_delay.setValue(30)
    c.export_with_encoder("libx265")
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert source in c.done
    assert c.output.exists()
    assert c.window.statusBar().currentMessage() == "Complete — 2 segments saved"
    assert c.player.source().isEmpty() == advance
    assert c.ready == (not advance)
    assert c.view.opacity() == (0 if advance else 1)
    assert c.export_button.isEnabled() == (not advance)
    assert c.count_timer.isActive() == quit_done
    assert c.file_list.count() == 1
    assert c.file_list.item(0).text() == f"{source.name}\nDone"
    if quit_done:
        assert c.count_action == "quit"
        assert c.count_now.isEnabled()
        c.count_cancelled()
    if advance:
        assert not c.video.videoSink().videoFrame().isValid()
        assert source.resolve() not in {
            Path(file.path).resolve() for file in psutil.Process().open_files()
        }
        assert c.paths == [source]
        assert c.index == c.file_list.currentRow() == -1
        assert not c.file_list.selectedItems()
        assert not c.segments
        assert c.active_segment == -1
        assert c.segment_list.count() == 0
        assert not c.previous.isEnabled()
        assert not c.next.isEnabled()
        assert len(c.source_segments[source]) == 2
        renamed = source.rename(tmp_path / "released.mp4")
        renamed.rename(source)
        c.file_list.setCurrentRow(0)
        qtbot.waitUntil(lambda: c.ready, timeout=15000)
        assert c.view.isVisible()
        assert len(c.segments) == 2
        assert c.export_button.isEnabled()


@pytest.mark.parametrize("deselect", ["button", "selection"])
def test_unload_keeps_files_and_releases_source(
    controller, qtbot, source, tmp_path, deselect
):
    c = controller
    other = tmp_path / "other.mp4"
    other.write_bytes(source.read_bytes())
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 8)])
    c.set_rect((20, 30, 160, 120))
    c.player.play()
    c.countdown("export", 30)
    if deselect == "button":
        c.select_none_button.click()
    else:
        c.file_list.setCurrentRow(-1)
    assert c.paths == [source, other]
    assert c.file_list.count() == 2
    assert c.index == c.file_list.currentRow() == -1
    assert not c.file_list.selectedItems()
    assert not c.ready and not c.loading
    assert c.player.source().isEmpty()
    assert not c.video.videoSink().videoFrame().isValid()
    assert c.view.opacity() == 0
    assert not c.segments and c.segment_list.count() == 0
    assert not c.count_timer.isActive()
    assert not c.load_timer.isActive()
    assert not c.follow_timer.isActive()
    assert not c.export_button.isEnabled()
    assert not c.select_none_button.isEnabled()
    assert c.clear_files_button.isEnabled()
    assert source.resolve() not in {
        Path(file.path).resolve() for file in psutil.Process().open_files()
    }
    c.file_list.setCurrentRow(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rect() == (20, 30, 160, 120)
    c.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert source.resolve() not in {
        Path(file.path).resolve() for file in psutil.Process().open_files()
    }
    c.done.add(source)
    c.clear_files_button.click()
    assert not c.paths and not c.source_segments and not c.done
    assert c.index == c.file_list.currentRow() == -1
    assert c.file_list.count() == 0
    assert not c.ready and c.player.source().isEmpty()
    assert not c.clear_files_button.isEnabled()
    assert other.resolve() not in {
        Path(file.path).resolve() for file in psutil.Process().open_files()
    }
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert not c.segments
    assert c.view.opacity() == 1
    assert c.video.videoSink().videoFrame().isValid()


@pytest.mark.parametrize("reopen", ["selection", "open", "drop"])
def test_preview_after_repeated_completed_runs(
    controller, qtbot, source, scene_video, tmp_path, monkeypatch, reopen
):
    c = controller
    c.paths = [source, scene_video]
    c.advance.setChecked(True)
    c.load(1)
    for run in range(2):
        qtbot.waitUntil(lambda: c.ready and not c.load_timer.isActive(), timeout=15000)
        c.replace_segments([(0, 0.5)])
        c.export_with_encoder("libx265")
        qtbot.waitUntil(lambda: not c.running, timeout=30000)
        assert c.player.source().isEmpty()
        assert c.index == c.file_list.currentRow() == -1
        assert c.paths[-1] == scene_video
        if reopen != "selection":
            new_video = tmp_path / f"next-{run}.mp4"
            new_video.write_bytes(scene_video.read_bytes())
            scene_video = new_video
        if reopen == "selection":
            c.file_list.setCurrentRow(len(c.paths) - 1)
        elif reopen == "open":
            monkeypatch.setattr(
                app.VideoFileDialog,
                "selectedFiles",
                lambda self, path=scene_video: [str(path)],
            )
            c.open_button.click()
        else:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(scene_video))])
            drop = QDropEvent(
                QPointF(20, 20),
                Qt.DropAction.CopyAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            c.eventFilter(c.window, drop)
            assert drop.isAccepted()
        qtbot.waitUntil(lambda: c.ready, timeout=15000)
        c.clear_segments()
        c.player.setPosition(2500)
        qtbot.waitUntil(
            lambda: (
                c.video.videoSink().videoFrame().isValid()
                and c.video.videoSink().videoFrame().startTime() >= 2400000
            ),
            timeout=15000,
        )
        assert c.view.isVisible() and c.video.isVisible()
        assert not c.video.videoSink().videoFrame().toImage().isNull()
        center = c.graphics.mapFromScene(
            c.video.mapToScene(c.video.boundingRect().center())
        )
        qtbot.waitUntil(
            lambda center=center: (
                c.viewport.grab().toImage().pixelColor(center).red() > 200
            ),
            timeout=15000,
        )


def test_preview_switches_dimensions_and_rotation_after_unload(
    controller, qtbot, source, tmp_path
):
    other = tmp_path / "wide.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=white:s=160x90:r=10:d=3",
            "-c:v",
            "libx264",
            str(other),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    c = controller
    c.paths = [source, other]
    c.auto_segment.setChecked(True)
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and bool(c.segments), timeout=15000)
    c.rotate(1)
    c.set_rect((20, 30, 120, 160))
    for _ in range(3):
        c.select_none_button.click()
        c.file_list.setCurrentRow(1)
        qtbot.waitUntil(lambda: c.ready and bool(c.segments), timeout=15000)
        assert (c.width, c.height, c.pixel_width, c.pixel_height) == (160, 90, 160, 90)
        assert c.rotation == 0
        assert c.rect() == (0, 0, 160, 90)
        assert c.video.boundingRect().size() == app.QRectF(0, 0, 160, 90).size()
        c.play.click()
        qtbot.waitUntil(lambda: c.player.position() >= 500, timeout=5000)
        c.play.click()
        qtbot.waitUntil(
            lambda: c.video.videoSink().videoFrame().startTime() >= 400000,
            timeout=5000,
        )
        center = c.graphics.mapFromScene(
            c.video.mapToScene(c.video.boundingRect().center())
        )
        qtbot.waitUntil(
            lambda center=center: (
                c.viewport.grab().toImage().pixelColor(center).red() > 200
            ),
            timeout=5000,
        )
        c.file_list.setCurrentRow(0)
        qtbot.waitUntil(lambda: c.ready, timeout=15000)
        assert (c.width, c.height, c.pixel_width, c.pixel_height) == (
            240,
            320,
            240,
            320,
        )
        assert c.rotation == 1
        assert c.rect() == (20, 30, 120, 160)
        assert other.resolve() not in {
            Path(file.path).resolve() for file in psutil.Process().open_files()
        }


@pytest.mark.parametrize(
    "code,status",
    [(1, app.QProcess.ExitStatus.NormalExit), (0, app.QProcess.ExitStatus.CrashExit)],
)
def test_failed_final_export_stays_loaded(
    controller, qtbot, source, monkeypatch, code, status
):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1)])
    c.advance.setChecked(True)
    monkeypatch.setattr(c.process, "start", MagicMock())
    c.export_with_encoder("libx265")
    c.finished(code, status)
    assert c.ready
    assert not c.player.source().isEmpty()
    assert c.view.isVisible()
    assert c.paths == [source]
    assert source not in c.done
    assert c.export_button.isEnabled()


@pytest.mark.parametrize("playing", [False, True])
def test_close_releases_video(controller, qtbot, source, tmp_path, playing):
    import shutil

    video = tmp_path / "close-test.mp4"
    shutil.copyfile(source, video)
    controller.paths = [video]
    controller.load(0)
    qtbot.waitUntil(lambda: controller.ready, timeout=15000)
    if playing:
        controller.player.play()
        qtbot.waitUntil(lambda: controller.player.position() > 0, timeout=15000)
    controller.window.close()
    assert controller.player.source().isEmpty()
    assert not controller.video.videoSink().videoFrame().isValid()
    assert video.resolve() not in {
        Path(file.path).resolve() for file in psutil.Process().open_files()
    }
    video.rename(tmp_path / "released.mp4")


@pytest.mark.parametrize(
    "suffix,video_encoder,audio_encoder",
    [(".3gp", "libx264", "aac"), (".webm", "libvpx-vp9", "libopus")],
)
def test_container_fallback_exports_remaining_segments(
    controller, qtbot, source, tmp_path, suffix, video_encoder, audio_encoder
):
    video = tmp_path / f"container-test{suffix}"
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
            "-c:v",
            video_encoder,
            "-c:a",
            audio_encoder,
            str(video),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    original = video.read_bytes()
    c = controller
    c.paths = [video]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 0.5), (0.5, 1)])
    c.set_rect((20, 30, 160, 120))
    c.save_segment()
    c.advance.setChecked(False)
    c.export_with_encoder("libx265")
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert video in c.done
    assert video.read_bytes() == original
    assert c.log.toPlainText().count("Container fallback:") == 1
    assert "New output:" in c.log.toPlainText()
    assert c.window.statusBar().currentMessage() == "Complete — 2 segments saved"
    for index, job in enumerate(c.export_jobs):
        assert job.output.suffix == ".mkv"
        assert not job.output.with_suffix(suffix).exists()
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
        video_stream, audio_stream = metadata["streams"]
        assert video_stream["codec_name"] == "hevc"
        assert audio_stream["codec_name"] == ("aac" if suffix == ".3gp" else "opus")
        assert (video_stream["width"], video_stream["height"]) == (
            (160, 120) if index == 0 else (320, 240)
        )


def test_container_fallback_failure_is_not_retried(
    controller, qtbot, source, monkeypatch
):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1)])
    start = MagicMock()
    monkeypatch.setattr(c.process, "start", start)
    c.export_with_encoder("libx265")
    c.output.touch()
    c.container_rejected = True
    c.finished(1, app.QProcess.ExitStatus.NormalExit)
    assert start.call_count == 2
    assert c.job.container == "mkv"
    assert c.running
    assert not c.container_rejected
    assert c.export_log == ""
    c.container_rejected = True
    c.finished(1, app.QProcess.ExitStatus.NormalExit)
    assert start.call_count == 2
    assert not c.running
    assert source not in c.done
    assert c.ready
    assert (
        c.window.statusBar().currentMessage()
        == "FFmpeg exited with code 1 — see Process log"
    )


@pytest.mark.parametrize(
    "message",
    ["Could not find tag for codec hevc", "Only VP8 or VP9 or AV1 video"],
)
def test_container_diagnostic_handles_chunks_without_retaining_log(
    controller, monkeypatch, message
):
    c = controller
    c.running = True
    chunks = [
        b"metadata\n" * 1000,
        message[:15].encode(),
        message[15:].encode(),
        b"diagnostics\n" * 1000,
    ]
    read = MagicMock(side_effect=chunks)
    monkeypatch.setattr(c.process, "readAllStandardError", read)
    for _ in chunks:
        c.read_log()
        assert len(c.export_log) <= 128
    assert c.container_rejected
    c.running = False


@pytest.mark.parametrize("outcome", ["cancel", "stop", "crash", "encoder"])
def test_container_fallback_does_not_retry_other_failures(
    controller, qtbot, source, monkeypatch, outcome
):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1)])
    start = MagicMock()
    monkeypatch.setattr(c.process, "start", start)
    c.export_with_encoder("libx265")
    c.output.touch()
    c.container_rejected = outcome != "encoder"
    if outcome in ("cancel", "stop"):
        c.outcome = outcome
    status = (
        app.QProcess.ExitStatus.CrashExit
        if outcome == "crash"
        else app.QProcess.ExitStatus.NormalExit
    )
    c.finished(1, status)
    assert start.call_count == 1
    assert not c.running
    assert c.job.container is None
    assert source not in c.done
    assert c.ready
    assert "Container fallback:" not in c.log.toPlainText()
    assert c.output is None if outcome == "cancel" else c.output.exists()


@pytest.mark.parametrize("playing", [False, True])
def test_switch_releases_previous_video(controller, qtbot, source, tmp_path, playing):
    import shutil

    video = tmp_path / "switch-test.mp4"
    shutil.copyfile(source, video)
    c = controller
    c.paths = [video, source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 1)])
    c.set_rect((20, 30, 160, 120))
    if playing:
        c.player.play()
        qtbot.waitUntil(lambda: c.player.position() > 0, timeout=15000)
    c.load(1)
    assert not c.video.videoSink().videoFrame().isValid()
    assert video.resolve() not in {
        Path(file.path).resolve() for file in psutil.Process().open_files()
    }
    renamed = video.rename(tmp_path / "released.mp4")
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.player.source().toLocalFile() == str(source).replace("\\", "/")
    renamed.rename(video)
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rect() == (20, 30, 160, 120)
    assert len(c.segments) == 1


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
@pytest.mark.parametrize("suffix", [".mp4", ".webm"])
def test_interrupt_after_completed_segment(
    controller, qtbot, source, tmp_path, monkeypatch, finish, suffix
):
    video = tmp_path / f"interrupt{suffix}"
    video.write_bytes(source.read_bytes())
    c = controller
    c.paths = [video, source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 0.5), (0.5, 6), (6, 8)])
    c.advance.setChecked(True)
    c.auto.setChecked(True)
    arguments = app.Export.arguments
    monkeypatch.setattr(
        app.Export,
        "arguments",
        lambda self: (["-re"] if self.segment_number == 2 else []) + arguments(self),
    )
    output_suffix = ".mkv" if suffix == ".webm" else suffix
    unstarted = video.with_stem(f"{video.stem}_SEGMENT_003_CROPPED").with_suffix(
        output_suffix
    )
    unstarted.write_bytes(b"output from a previous export")
    unrelated = tmp_path / "unrelated.mp4"
    unrelated.write_bytes(b"unrelated output")
    c.export_with_encoder("libx265")
    qtbot.waitUntil(
        lambda: c.export_index == 1 and c.processing_position > 0.5,
        timeout=15000,
    )
    completed, partial = [job.output for job in c.export_jobs[:2]]
    assert completed.exists() and partial.exists()
    c.pause_export()
    if finish == "cancel":
        c.cancel.click()
    else:
        c.stop.click()
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert completed.exists() == (finish == "stop")
    assert partial.exists() == (finish == "stop")
    assert unstarted.read_bytes() == b"output from a previous export"
    assert unrelated.read_bytes() == b"unrelated output"
    assert video.read_bytes() == source.read_bytes()
    assert c.index == 0 and c.export_index == 1
    assert c.ready and not c.loading
    assert not c.count_timer.isActive()
    assert not c.auto_export_pending
    assert video not in c.done
    assert c.output == (partial if finish == "stop" else None)


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
    c.advance.setChecked(True)
    c.export()
    qtbot.waitUntil(lambda: c.processing_position > 0, timeout=15000)
    assert c.window.statusBar().currentMessage().startswith("Processing segment 1/")
    assert "fps" in c.window.statusBar().currentMessage()
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
    assert c.ready
    assert not c.player.source().isEmpty()
    assert c.paths == [source]
    if finish == "stop":
        assert c.window.statusBar().currentMessage() == "Stopped — output saved"
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
        assert c.window.statusBar().currentMessage() == "Canceled — output deleted"
        assert not c.job.output.exists()


def test_queued_segment_creation_stops_on_load_and_close(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and not c.load_timer.isActive(), timeout=15000)
    c.auto_segment.setChecked(True)
    c.load_timer.start(0)
    c.load(0)
    assert not c.load_timer.isActive()
    assert not c.segments
    qtbot.waitUntil(lambda: c.ready and bool(c.segments), timeout=15000)
    c.clear_segments_button.click()
    c.load_timer.start(0)
    c.window.close()
    assert not c.load_timer.isActive()
    qtbot.wait(20)
    assert not c.segments


def test_auto_advance_with_automatic_segment(controller, qtbot, source, tmp_path):
    c = controller
    other = tmp_path / "next.mp4"
    other.write_bytes(source.read_bytes())
    c.remember_crop.setChecked(True)
    c.auto_segment.setChecked(True)
    c.advance.setChecked(True)
    c.auto.setChecked(True)
    c.auto_delay.setValue(30)
    c.paths = [source, other]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and bool(c.segments), timeout=15000)
    assert not c.count_timer.isActive()
    c.set_rect((20, 30, 160, 120))
    c.export_with_encoder("libx265")
    qtbot.waitUntil(
        lambda: c.index == 1 and c.ready and bool(c.segments), timeout=30000
    )
    assert c.rect() == (20, 30, 160, 120)
    qtbot.waitUntil(c.count_timer.isActive)
    assert c.count_action == "export"
    assert c.file_list.currentRow() == 1
    assert c.file_list.item(0).text() == f"{source.name}\nDone"
    c.count_execute()
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.done == {source, other}
    assert c.export_jobs[0].source == other
    assert c.export_jobs[0].rect == (20, 30, 160, 120)


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
    qtbot.waitUntil(c.count_timer.isActive)
    c.count_cancelled()
    assert not c.count_timer.isActive()
    c.countdown("export", 1)
    qtbot.waitUntil(lambda: c.running, timeout=5000)
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.window.statusBar().currentMessage() == "Complete — 1 segments saved"


@pytest.mark.parametrize(
    "rotation,rect,size",
    [
        (0, (80, 0, 160, 240), (320, 240)),
        (1, (0, 80, 240, 160), (120, 160)),
    ],
)
def test_anamorphic_view_maps_to_source_pixels(
    controller, qtbot, source, tmp_path, rotation, rect, size
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
    c.rotate(rotation)
    c.square.setChecked(True)
    c.export()
    assert c.job.rect == rect
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.window.statusBar().currentMessage() == "Complete — 1 segments saved"
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
    assert c.window.statusBar().currentMessage() == "Complete — 1 segments saved"


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
    assert controller.file_list.count() == 1
    assert controller.file_list.currentRow() == 0
    assert controller.file_list.item(0).data(Qt.ItemDataRole.UserRole) == source


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
    assert (c.install_status.text() == "Installed in File Explorer") == (exit_code == 0)


def test_explorer_folder_startup(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("folder_path", "previous folder")
    settings.sync()
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
    folder = str(tmp_path / "Selected folder with spaces")
    Path(folder).mkdir()
    c = app.Application(paths=[folder])
    qtbot.addWidget(c.window)
    assert settings.value("folder_path") == folder
    assert c.paths == []
    assert not c.running
    assert not c.count_timer.isActive()
    c.window.close()


def test_explorer_startup_argument(monkeypatch, tmp_path):
    folder = str(tmp_path / "Selected folder with spaces")
    monkeypatch.setattr(sys, "argv", ["fastvideocropper", folder, "clip.mp4"])
    application = MagicMock()
    application.return_value.exec.return_value = 0
    controller = MagicMock()
    controller.return_value.window.pending_installer = None
    monkeypatch.setattr(app, "QApplication", application)
    monkeypatch.setattr(app, "Application", controller)
    assert app.main() == 0
    controller.assert_called_once_with(paths=[folder, "clip.mp4"])


def test_preferences_restored_from_config_file(controller, qtbot, source, tmp_path):
    c = controller
    assert Path(c.settings.fileName()) == tmp_path / "settings.ini"
    assert c.settings.format() == QSettings.Format.IniFormat
    checkboxes = [
        "mute",
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
    c.settings.setValue("folder_path", str(tmp_path))
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
    assert restored.settings.value("folder_path") == str(tmp_path)
    assert restored.encoder.currentData() == "auto"
    assert restored.device.value() == 2
    assert restored.auto_delay.value() == 12
    assert restored.quit_delay.value() == 45
    assert restored.tabs.currentIndex() == 1
    assert restored.settings.contains("mainWindow/geometry")
    assert restored.settings.contains("mainWindow/state")
    assert restored.settings.contains("mainWindow/splitterState")
    assert not {"geometry", "rotation", "preset", "centered", "lock"}.intersection(
        restored.settings.allKeys()
    )
    restored.paths = [source]
    restored.load(0)
    qtbot.waitUntil(lambda: restored.ready, timeout=15000)
    assert restored.segments == []
    assert restored.rotation == 0
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
    assert c.rotation == 0
    assert c.rect() == (0, 0, 320, 240)
    assert not c.lock.isChecked()
    c.replace_segments([(0, 8)])
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.rotation == 1
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
        assert (segment.rect, segment.rotation, segment.preset, segment.locked) == (
            original.rect,
            original.rotation,
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


def test_crop_detection_enabled_on_cached_video(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 8)])
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.active_segment == 0
    assert c.detect_crop_action.isEnabled()
    assert c.detect_crop_button.isEnabled()


def test_navigation_fractional_millisecond_boundaries(controller, qtbot, source):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 2.333333), (2.333333, 5.666667), (5.666667, 8)])
    for name, position, segment in [
        ("next", 2333, 1),
        ("next", 5667, 2),
        ("previous", 2333, 1),
        ("previous", 0, 0),
    ]:
        c.navigation_buttons[name].click()
        assert c.player.position() == position
        assert c.active_segment == segment
        assert not c.split_segment_action.isEnabled()
        assert not c.split_segment_button.isEnabled()
    c.segment_list.setCurrentRow(1)
    assert c.navigation_buttons["previous"].isEnabled()
    c.seek_segment(2332)
    assert c.active_segment == 0
    c.seek_segment(2333)
    assert c.active_segment == 1


def test_player_navigation_controls(controller, qtbot, source):
    c = controller
    assert all(not b.isEnabled() for b in c.navigation_buttons.values())
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert not c.navigation_buttons["previous"].isEnabled()
    assert not c.navigation_buttons["next"].isEnabled()
    c.replace_segments([(0, 2), (2, 5), (5, 8)])
    c.segment_list.setCurrentRow(1)
    c.set_rect((20, 30, 160, 120))
    c.seek_segment(0)
    for name, position, segment in [
        ("next", 2000, 1),
        ("forward", 3000, 1),
        ("back", 2000, 1),
        ("next", 5000, 2),
        ("previous", 2000, 1),
        ("previous", 0, 0),
        ("back", 0, 0),
        ("end", 8000, 2),
        ("forward", 8000, 2),
        ("back", 7000, 2),
        ("start", 0, 0),
    ]:
        qtbot.mouseClick(c.navigation_buttons[name], Qt.MouseButton.LeftButton)
        assert c.player.position() == position
        assert c.active_segment == segment
        assert c.seek.value() == position
        assert c.time.text() == f"00:00:{position // 1000:02d}"
        assert c.total_time.text() == "00:00:08"
        if segment == 1:
            assert c.rect() == (20, 30, 160, 120)
    assert not c.navigation_buttons["previous"].isEnabled()
    c.seek_segment(8000)
    assert not c.navigation_buttons["next"].isEnabled()
    c.running = True
    c.update_enabled()
    assert all(not b.isEnabled() for b in c.navigation_buttons.values())
    c.running = False
    c.update_enabled()
    c.clear_segments()
    assert not c.navigation_buttons["previous"].isEnabled()
    assert not c.navigation_buttons["next"].isEnabled()


@pytest.mark.parametrize("trigger,rotation,sar", [("menu", 0, 1), ("button", 1, 2)])
def test_detect_crop_selected_segment(
    controller, qtbot, tmp_path, trigger, rotation, sar
):
    path = tmp_path / "bordered.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=white:s=320x240:r=10:d=4",
            "-vf",
            (
                "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,2)',"
                "drawbox=x=40:y=20:w=240:h=200:color=white:t=fill,"
                f"setsar={sar}"
            ),
            "-c:v",
            "libx264",
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    c = controller
    assert not c.detect_crop_action.isEnabled()
    c.paths = [path]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert not c.detect_crop_action.isEnabled()
    c.replace_segments([(0, 2), (2, 4)])
    c.segment_list.setCurrentRow(1)
    c.rotate(rotation)
    c.lock.setChecked(True)
    original = c.segments[0].rect

    def accept_detection():
        dialog = QApplication.activeModalWidget()
        dialog.findChild(QSpinBox, "round").setValue(2)
        dialog.grab().save(str(tmp_path / "crop-detection-dialog.png"))
        dialog.accept()

    QTimer.singleShot(20, accept_detection)
    if trigger == "menu":
        c.detect_crop_action.trigger()
    else:
        c.detect_crop_button.click()
    assert c.running and c.detecting_crop
    assert not c.detect_crop_action.isEnabled()
    assert not c.segment_list.isEnabled()
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert (
        c.window.statusBar().currentMessage()
        == "Crop detection complete — selected segment updated"
    )
    assert c.rect() == ((40, 20, 240, 200) if rotation == 0 else (20, 80, 200, 480))
    assert c.segments[0].rect == original
    assert c.active_segment == 1
    assert c.lock.isChecked()
    assert c.selected_preset == "Custom"
    detected = c.rect()
    c.segment_list.setCurrentRow(0)
    c.segment_list.setCurrentRow(1)
    assert c.rect() == detected
    assert c.detect_crop_action.isEnabled()


def test_cancel_crop_detection(controller, qtbot, source, monkeypatch):
    c = controller
    c.paths = [source]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 8)])
    c.set_rect((20, 30, 160, 120))
    original = c.rect()
    arguments = app.CropScan.arguments
    monkeypatch.setattr(
        app.CropScan, "arguments", lambda self: ["-re", *arguments(self)]
    )
    c.detect_crop({"mode": "black", "round": 2})
    qtbot.waitUntil(lambda: c.process.processId() != 0, timeout=5000)
    c.cancel_export()
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert c.rect() == original
    assert c.window.statusBar().currentMessage() == "Crop detection canceled"
    assert c.detect_crop_action.isEnabled()


@pytest.mark.parametrize("auto_segment", [False, True])
@pytest.mark.parametrize("result", ["failed", "empty"])
def test_scene_detection_without_segments(
    controller, qtbot, scene_video, monkeypatch, auto_segment, result
):
    c = controller
    c.paths = [scene_video]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 6000, timeout=15000)
    qtbot.waitUntil(lambda: not c.load_timer.isActive())
    c.auto_segment.setChecked(auto_segment)
    c.replace_segments([(0, 2), (2, 6)])
    c.set_rect((20, 30, 160, 120))
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Yes
    )
    if result == "failed":
        monkeypatch.setattr(
            app.SceneScan, "arguments", lambda self: ["-invalid-option"]
        )
    else:
        monkeypatch.setattr(app.SceneScan, "ranges", lambda self: [])
    c.detect_segments(0.3, 1)
    assert c.segments == []
    qtbot.waitUntil(lambda: not c.running, timeout=15000)
    assert not c.detecting
    assert [(s.start, s.end) for s in c.segments] == ([(0, 6)] if auto_segment else [])
    assert c.segment_list.count() == len(c.segment_regions) == int(auto_segment)
    assert c.active_segment == (0 if auto_segment else -1)
    assert c.export_button.isEnabled() == auto_segment
    assert c.source_segments[scene_video] is c.segments
    if auto_segment:
        assert c.segments[0].rect == (20 / 320, 30 / 240, 160 / 320, 120 / 240)
    message = c.window.statusBar().currentMessage()
    if result == "failed":
        assert message.startswith("FFmpeg exited with code")
    else:
        assert message == "Scene detection complete — 0 segments"


@pytest.mark.parametrize("auto_segment", [False, True])
@pytest.mark.parametrize("confirm", [False, True])
def test_scene_detection_replacement_confirmation(
    controller, qtbot, scene_video, confirm, auto_segment
):
    c = controller
    c.paths = [scene_video]
    c.load(0)
    qtbot.waitUntil(lambda: c.ready and c.player.duration() == 6000, timeout=15000)
    c.auto_segment.setChecked(auto_segment)
    c.replace_segments([(0, 1), (1, 6)])
    c.set_rect((20, 30, 160, 120))
    originals = list(c.segments)

    def answer_confirmation():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        assert "clear all existing segments" in dialog.text()
        dialog.button(
            QMessageBox.StandardButton.Yes
            if confirm
            else QMessageBox.StandardButton.Cancel
        ).click()

    QTimer.singleShot(20, answer_confirmation)
    c.detect_segments(0.3, 1)
    if confirm:
        assert c.detecting
        assert c.segments == []
        assert c.segment_list.count() == 0
        assert c.segment_regions == []
        assert c.active_segment == -1
        qtbot.waitUntil(lambda: not c.detecting, timeout=15000)
        assert [(s.start, s.end) for s in c.segments] == [(0, 2), (2, 4), (4, 6)]
        assert c.segment_list.count() == len(c.segment_regions) == 3
        assert all(s is not original for s in c.segments for original in originals)
    else:
        assert not c.detecting
        assert c.segments == originals
        assert c.segment_list.count() == len(c.segment_regions) == 2
        assert c.rect() == (20, 30, 160, 120)


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
        c.files_dock.toggleViewAction(),
        toggle,
        view_menu.actions()[2],
        c.reset_layout_action,
    ]
    assert view_menu.actions()[2].isSeparator()
    assert toggle.isCheckable() and toggle.isChecked()
    assert c.window.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert dock.isAncestorOf(c.segment_list)
    assert dock.widget().layout().count() == 1
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


def test_files_selection_and_append(controller, qtbot, source, tmp_path, monkeypatch):
    c = controller
    other = tmp_path / source.name
    other.write_bytes(source.read_bytes())
    assert c.file_list.count() == 0
    assert not c.file_list.isEnabled()
    monkeypatch.setattr(
        app.VideoFileDialog,
        "selectedFiles",
        lambda self: [str(source), str(other)],
    )
    c.open_button.click()
    assert not c.file_list.isEnabled()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.file_list.count() == 2
    assert c.file_list.currentRow() == c.index == 0
    assert c.file_list.item(1).data(Qt.ItemDataRole.UserRole) == other
    assert c.file_list.item(1).toolTip() == str(other)
    c.add_segment_button.click()
    c.set_rect((20, 30, 160, 120))
    c.file_list.setFocus()
    qtbot.keyClick(c.file_list, Qt.Key.Key_Down)
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.index == c.file_list.currentRow() == 1
    assert c.player.source().toLocalFile() == str(other).replace("\\", "/")
    c.previous.click()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.file_list.currentRow() == 0
    assert c.rect() == (20, 30, 160, 120)
    c.next.click()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.file_list.currentRow() == 1
    for state in ("running", "loading", "resolving_encoder"):
        setattr(c, state, True)
        c.update_enabled()
        assert not c.file_list.isEnabled()
        assert not c.select_none_button.isEnabled()
        assert not c.clear_files_button.isEnabled()
        setattr(c, state, False)
    c.update_enabled()
    c.update_busy(True)
    assert not c.files_dock.isEnabled()
    c.update_busy(False)
    assert c.file_list.isEnabled()
    monkeypatch.setattr(
        app.VideoFileDialog, "selectedFiles", lambda self: [str(source)]
    )
    c.open_action.trigger()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.file_list.count() == 2
    assert c.file_list.currentRow() == 0
    assert c.rect() == (20, 30, 160, 120)


@pytest.mark.parametrize("placement", ["right", "floating", "hidden"])
def test_files_dock_persistence_and_reset(controller, qtbot, placement):
    c = controller
    dock = c.files_dock
    assert dock.windowTitle() == "Files"
    assert c.window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    for widget in (
        c.open_button,
        c.previous,
        c.next,
        c.file_list,
        c.locate,
        c.select_none_button,
        c.clear_files_button,
    ):
        assert dock.isAncestorOf(widget)
    assert c.locate.text() == "Open Output Folder"
    c.window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    if placement == "floating":
        dock.setFloating(True)
    elif placement == "hidden":
        dock.close()
    c.window.close()
    restored = app.Application()
    qtbot.addWidget(restored.window)
    restored.window.show()
    dock = restored.files_dock
    assert restored.window.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert dock.isFloating() == (placement == "floating")
    assert dock.isVisible() == (placement != "hidden")
    restored.reset_layout_action.trigger()
    assert restored.window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert dock.isVisible() and not dock.isFloating()
    dock.toggleViewAction().trigger()
    assert not dock.isVisible()
    dock.toggleViewAction().trigger()
    assert dock.isVisible()
