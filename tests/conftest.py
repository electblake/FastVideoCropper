import _winapi
import subprocess

import pytest


@pytest.fixture
def assert_file_released():
    def check(path):
        # Exclusive access fails natively if any decoder still holds this file.
        handle = _winapi.CreateFile(
            str(path), _winapi.GENERIC_READ, 0, 0, _winapi.OPEN_EXISTING, 0, 0
        )
        _winapi.CloseHandle(handle)

    return check


@pytest.fixture(scope="session")
def source(tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=10:duration=8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=8",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return path


@pytest.fixture
def scene_video(tmp_path):
    path = tmp_path / "scenes.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=320x240:r=10:d=2",
            "-f",
            "lavfi",
            "-i",
            "color=white:s=320x240:r=10:d=2",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=320x240:r=10:d=2",
            "-filter_complex",
            "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
            "-c:v",
            "libx264",
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return path
