import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QTreeView

from fastvideocropper import app


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
    c = app.Application(no_profile=True)
    qtbot.addWidget(c.window)
    c.window.showMinimized()
    yield c
    c.window.close()


@pytest.fixture
def folder(tmp_path, source):
    path = tmp_path / "Video folder"
    path.mkdir()
    (path / "clip.MP4").write_bytes(source.read_bytes())
    (path / "notes.txt").write_text("not a video")
    (path / "nested").mkdir()
    (path / "nested/deeper.mp4").write_bytes(source.read_bytes())
    return path


def test_mixed_startup_loads_folder(qtbot, tmp_path, monkeypatch, source, folder):
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
    c = app.Application(
        paths=[str(folder), str(source), str(folder / "clip.MP4")], no_profile=True
    )
    qtbot.addWidget(c.window)
    c.window.showMinimized()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.paths == [folder / "clip.MP4", source]
    assert c.file_list.count() == 2
    assert Path(c.player.source().toLocalFile()) == folder / "clip.MP4"
    assert c.video.videoSink().videoFrame().isValid()
    assert not c.running and not c.count_timer.isActive()
    c.window.close()


def test_low_frame_rate_hevc_with_audio_loads_and_seeks(controller, qtbot, tmp_path):
    video = tmp_path / "low-fps-with-audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=1:duration=16",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=16",
            "-c:v",
            "libx265",
            "-x265-params",
            "bframes=4:log-level=error",
            "-c:a",
            "aac",
            str(video),
        ],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    c = controller
    c.add_paths([video])
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert not c.loading
    assert c.player.hasAudio()
    assert c.player.audioOutput() is c.audio
    assert c.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    assert c.video.videoSink().videoFrame().isValid()
    assert c.open_button.isEnabled()
    assert "Probing metadata:" in c.log.toPlainText()
    assert "Video ready: first preview frame decoded" in c.log.toPlainText()
    with qtbot.waitSignal(c.video.videoSink().videoFrameChanged, timeout=15000):
        c.seek_segment(8000)
    assert c.player.position() == 8000
    with qtbot.waitSignal(c.video.videoSink().videoFrameChanged, timeout=15000):
        c.player.play()
    c.player.pause()


@pytest.mark.parametrize("target", ["panel", "list", "window"])
@pytest.mark.parametrize("populated", [False, True])
def test_folder_drop_appends(controller, qtbot, source, folder, target, populated):
    c = controller
    if populated:
        c.add_paths([source])
        qtbot.waitUntil(lambda: c.ready, timeout=15000)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(folder)), QUrl.fromLocalFile(str(source))])
    widget = {
        "panel": c.files_dock.widget(),
        "list": c.file_list.viewport(),
        "window": c.window,
    }[target]
    drag = QDragEnterEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, drag)
    assert drag.isAccepted()
    drop = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, drop)
    assert drop.isAccepted()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    video = folder / "clip.MP4"
    assert c.paths == ([source, video] if populated else [video, source])
    assert c.index == (1 if populated else 0)


def test_aliases_preserve_crop(controller, qtbot, folder):
    c = controller
    video = folder / "clip.MP4"
    c.add_paths([video])
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 2)])
    c.set_rect((20, 30, 160, 120))
    c.add_paths([folder / ".." / folder.name, video])
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.paths == [video]
    assert c.rect() == (20, 30, 160, 120)
    assert len(c.segments) == 1


def test_empty_folder_and_cancel_keep_loaded_video(
    controller, qtbot, source, tmp_path, monkeypatch
):
    c = controller
    c.add_paths([source])
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 2)])
    c.set_rect((20, 30, 160, 120))
    empty = tmp_path / "Empty"
    empty.mkdir()
    c.add_paths([empty])
    monkeypatch.setattr(
        app.VideoFileDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )
    c.open_button.click()
    assert c.ready and not c.loading
    assert c.paths == [source]
    assert c.rect() == (20, 30, 160, 120)
    assert c.video.videoSink().videoFrame().isValid()


def test_open_folder_after_completed_run(
    controller, qtbot, source, folder, monkeypatch
):
    c = controller
    c.add_paths([source])
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    c.replace_segments([(0, 0.5)])
    c.advance.setChecked(True)
    c.export_with_encoder("libx265")
    qtbot.waitUntil(lambda: not c.running, timeout=30000)
    assert c.index == -1
    monkeypatch.setattr(
        app.VideoFileDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )
    monkeypatch.setattr(
        app.VideoFileDialog, "selectedFiles", lambda self: [str(folder)]
    )
    c.open_button.click()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.paths == [source, folder / "clip.MP4"]
    assert c.index == 1
    assert c.video.videoSink().videoFrame().isValid()
    assert c.view.opacity() == 1
    assert c.view.sceneBoundingRect().width() > 100


@pytest.mark.parametrize("mixed", [False, True])
def test_real_dialog_accepts_folders(qtbot, tmp_path, folder, source, mixed):
    video = tmp_path / "video.mp4"
    video.write_bytes(source.read_bytes())
    dialog = app.VideoFileDialog(None, "Open videos", str(tmp_path))
    qtbot.addWidget(dialog)
    dialog.setOption(app.QFileDialog.Option.DontUseNativeDialog)
    dialog.setFileMode(app.QFileDialog.FileMode.ExistingFiles)
    dialog.setViewMode(app.QFileDialog.ViewMode.Detail)
    dialog.show()
    view = dialog.findChild(QTreeView, "treeView")
    model = view.model()
    qtbot.waitUntil(lambda: model.index(str(folder)).isValid())
    selected = [folder, video] if mixed else [folder]
    for path in selected:
        view.selectionModel().select(
            model.index(str(path)),
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows,
        )
    button = dialog.findChild(QDialogButtonBox).button(
        QDialogButtonBox.StandardButton.Open
    )
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert {Path(path) for path in dialog.selectedFiles()} == set(selected)
