"""Exercise the installed launcher's mixed folder/file arguments with real media."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from fastvideocropper import app, installed

report = Path(sys.argv[1])
workspace = tempfile.TemporaryDirectory(prefix="FastVideoCropper-inputs-")
root = Path(workspace.name)
folder = root / "Folder with spaces"
folder.mkdir()
video = folder / "clip.MP4"
direct = root / "Direct video.mp4"
tools = Path(sys.prefix).parents[1] / "tools/ffmpeg/ffmpeg-8.1.2-essentials_build/bin"
subprocess.run(
    [
        str(tools / "ffmpeg.exe"),
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=white:s=160x90:r=10:d=2",
        "-c:v",
        "libx264",
        str(video),
    ],
    check=True,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
direct.write_bytes(video.read_bytes())
(folder / "notes.txt").write_text("not a video")
app.user_config_path = lambda *args, **kwargs: root


def create_controller(*args, **kwargs):
    controller = app.Application(*args, **kwargs)
    timer = QTimer(controller)
    selected_second = False

    def check():
        nonlocal selected_second
        if not controller.ready:
            return
        assert controller.paths == [video, direct]
        assert controller.video.videoSink().videoFrame().isValid()
        assert controller.view.opacity() == 1
        assert controller.view.sceneBoundingRect().width() > 100
        assert not controller.running and not controller.count_timer.isActive()
        if not selected_second:
            assert Path(controller.player.source().toLocalFile()) == video
            controller.file_list.setCurrentRow(1)
            selected_second = True
        else:
            assert Path(controller.player.source().toLocalFile()) == direct
            report.write_text(
                json.dumps(
                    {
                        "result": "passed",
                        "launcher": installed.MODULE,
                        "inputs": "Folder with spaces, direct video, duplicate folder video",
                        "preview": "Both imported videos decoded and displayed",
                    },
                    indent=2,
                )
            )
            timer.stop()
            controller.window.close()
            QApplication.instance().quit()

    timer.timeout.connect(check)
    timer.start(100)
    QTimer.singleShot(60000, lambda: QApplication.instance().exit(1))
    return controller


installed.Application = create_controller
sys.argv = [sys.argv[0], str(folder), str(direct), str(video)]
sys.exit(installed.main())
