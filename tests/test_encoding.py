import json
import subprocess

import numpy as np
import pytest

from fastvideocropper.encoding import Export, padded_rect, rotate_rect


@pytest.mark.parametrize(
    "padding,expected",
    [
        ((3, -5), (37, 35, 166, 110)),
        ((0, 0), (40, 30, 160, 120)),
        ((50, 100), (0, 0, 250, 240)),
    ],
)
def test_padding_in_source_pixels(padding, expected):
    assert padded_rect((40, 30, 160, 120), *padding, 320, 240) == expected


@pytest.mark.parametrize(
    "start,end,rotation,expected_size",
    [
        (2.3, 5.7, 0, (160, 120)),
        (0, 2, 1, (160, 120)),
        (6, 8, 2, (160, 120)),
        (0, 8, 3, (160, 120)),
    ],
)
def test_real_crop_and_trim(source, start, end, rotation, expected_size):
    job = Export(source, (20, 30, 160, 120), rotation, start, end)
    subprocess.run(
        ["ffmpeg", *job.arguments()],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
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
    assert (video["width"], video["height"]) == expected_size
    assert int(video["nb_frames"]) == round((end - start) * 10)
    assert float(audio["duration"]) == pytest.approx(end - start, abs=0.05)
    assert video["codec_name"] == "hevc"
    assert audio["codec_name"] == "aac"
    rotation_filter = ["", "transpose=clock,", "hflip,vflip,", "transpose=cclock,"][
        rotation
    ]
    expected = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-vf",
            rotation_filter + "crop=160:120:20:30",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    actual = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(job.output),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    error = np.abs(
        np.frombuffer(actual, np.uint8).astype(float)
        - np.frombuffer(expected, np.uint8).astype(float)
    )
    assert error.mean() < 5


def test_four_rotations_preserve_crop():
    rect = original = (20, 30, 160, 120)
    width, height = 320, 240
    for _ in range(4):
        rect = rotate_rect(rect, width, height)
        width, height = height, width
    assert rect == original


def test_square_pixel_output(source, tmp_path):
    anamorphic = tmp_path / "anamorphic.mp4"
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
            str(anamorphic),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    job = Export(anamorphic, (0, 0, 320, 240), 0, 0, 1, square_pixels=True)
    subprocess.run(
        ["ffmpeg", *job.arguments()],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
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
                str(job.output),
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    )["streams"][0]
    assert (result["width"], result["height"]) == (640, 240)
    assert result["sample_aspect_ratio"] == "1:1"
