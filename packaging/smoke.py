"""Verify playback and export using the environment created by Setup."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

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
started = False
timer = QTimer()


def step():
    global started
    if controller.ready and not started:
        controller.replace_segments([(0.2, 0.7), (0.7, 1.2)])
        controller.segment_list.setCurrentRow(1)
        controller.merge_segments_button.click()
        assert len(controller.segments) == 1
        assert (controller.segments[0].start, controller.segments[0].end) == (0.2, 1.2)
        controller.set_rect((20, 20, 160, 120))
        controller.rotate(1)
        started = True
        controller.export_with_encoder("libx265")
    elif started and not controller.running:
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
        Path(sys.argv[1]).write_text(
            json.dumps(
                {
                    "result": "passed",
                    "ffmpeg": ffmpeg,
                    "ffprobe": ffprobe,
                    "video_dimensions": [120, 160],
                    "frames": 10,
                    "playback": "Qt Multimedia decoded source",
                    "audio": "aac",
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
