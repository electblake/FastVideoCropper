"""Verify playback and export using the environment created by Setup."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton

from fastvideocropper import app as application

tools = Path(sys.prefix).parents[1] / "tools/ffmpeg/ffmpeg-8.1.2-essentials_build/bin"
ffmpeg, ffprobe = str(tools / "ffmpeg.exe"), str(tools / "ffprobe.exe")
workspace = tempfile.TemporaryDirectory(prefix="FastVideoCropper-smoke-")
source = Path(workspace.name) / "source.mp4"
subprocess.run(
    [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=320x240:rate=10:duration=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(source),
    ],
    check=True,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
application.user_config_path = lambda *args, **kwargs: Path(workspace.name)
app = QApplication([])
controller = application.Application(ffmpeg, ffprobe)
controller.window.show()
controller.paths = [source]
controller.load(0)
phase = "load"
timer = QTimer()


def step():
    global phase
    if controller.ready and phase == "load":
        controller.replace_segments([(0.2, 0.7), (0.7, 1.2)])
        controller.segment_list.setCurrentRow(1)
        controller.merge_segments_button.click()
        assert len(controller.segments) == 1
        assert (controller.segments[0].start, controller.segments[0].end) == (0.2, 1.2)
        for name in list(application.RATIOS) * 3:
            controller.preset_buttons[name].click()
            x, y, width, height = controller.rect()
            assert (
                abs(max(width / controller.width, height / controller.height) - 1)
                < 1e-9
            )
            assert abs(x + width / 2 - controller.width / 2) < 1e-9
            assert abs(y + height / 2 - controller.height / 2) < 1e-9
        buttons = {
            button.text(): button
            for button in controller.window.findChildren(QPushButton)
        }
        buttons["1/2 Center"].click()
        assert controller.rect() == (80, 0, 160, 240)
        buttons["1/2 Right"].click()
        buttons["Center frame"].click()
        assert controller.rect() == (80, 0, 160, 240)
        controller.set_rect((20, 20, 160, 120))
        controller.rotate(1)
        controller.advance.setChecked(True)
        phase = "export"
        controller.export_with_encoder("libx265")
    elif phase == "export" and not controller.running:
        assert (
            controller.window.statusBar().currentMessage()
            == "Complete — 1 segments saved"
        ), controller.log.toPlainText()
        streams = json.loads(
            subprocess.check_output(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_streams",
                    "-of",
                    "json",
                    str(controller.output),
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        )["streams"]
        assert (streams[0]["width"], streams[0]["height"]) == (120, 160)
        assert int(streams[0]["nb_frames"]) == 10
        assert streams[0]["codec_name"] == "hevc"
        assert streams[1]["codec_name"] == "aac"
        assert controller.paths == [source]
        assert controller.index == controller.file_list.currentRow() == -1
        assert controller.player.source().isEmpty()
        assert not controller.video.videoSink().videoFrame().isValid()
        controller.file_list.setCurrentRow(0)
        phase = "reload"
    elif phase == "reload" and controller.ready:
        assert controller.rotation == 1
        assert controller.video.videoSink().videoFrame().isValid()
        assert controller.view.opacity() == 1
        assert controller.view.sceneBoundingRect().width() > 100
        assert controller.export_button.isEnabled()
        controller.select_none_button.click()
        assert controller.paths == [source]
        assert controller.player.source().isEmpty()
        controller.clear_files_button.click()
        assert not controller.paths and not controller.source_segments
        Path(sys.argv[1]).write_text(
            json.dumps(
                {
                    "result": "passed",
                    "ffmpeg": ffmpeg,
                    "ffprobe": ffprobe,
                    "video_dimensions": [120, 160],
                    "frames": 10,
                    "playback": "Qt Multimedia decoded source",
                    "presets": "Three cycles retained full-frame crop dimensions",
                    "half_center": "Matched a half crop followed by Center frame",
                    "audio": "aac",
                    "file_lifecycle": "Export unloaded video; retained file reloaded with preview; Select none and Clear files released it",
                },
                indent=2,
            )
        )
        timer.stop()
        controller.window.close()
        app.quit()


timer.timeout.connect(step)
timer.start(100)
QTimer.singleShot(60000, lambda: app.exit(1))
sys.exit(app.exec())
