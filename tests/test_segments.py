import subprocess
from dataclasses import replace

import pytest

from fastvideocropper.segments import SceneScan, Segment


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, True),
        ({"preset": "16:9", "locked": True, "rotation": 3}, True),
        ({"start": 1.001}, False),
        ({"start": 0.999}, False),
        ({"rect": (0.1, 0, 1, 1)}, False),
        ({"rect": (0, 0.1, 1, 1)}, False),
        ({"rect": (0, 0, 0.5, 1)}, False),
        ({"rect": (0, 0, 1, 0.5)}, False),
        ({"padding_x": -4}, False),
        ({"padding_y": 4}, False),
    ],
)
def test_merge_compatibility(changes, expected):
    left = Segment(0, 1, (0, 0, 1, 1), 0, "Custom", False)
    right = replace(left, start=1, end=2)
    assert left.can_merge(replace(right, **changes)) is expected


@pytest.mark.parametrize(
    "framestep,threads,cuts",
    [(1, 0, [2, 4]), (2, 1, [2, 4]), (3, 2, [2.1, 4.2])],
)
def test_real_scene_detection(scene_video, framestep, threads, cuts):
    scan = SceneScan(scene_video, 6, 0.3, 1, framestep, threads)
    arguments = scan.arguments()
    assert arguments.index("-threads:v") < arguments.index("-i")
    result = subprocess.run(
        ["ffmpeg", *scan.arguments()],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    for index in range(0, len(result.stderr), 13):
        scan.read_log(result.stderr[index : index + 13])
    assert scan.ranges() == [(0, cuts[0]), (cuts[0], cuts[1]), (cuts[1], 6)]
    assert "progress=end" in result.stdout
    scan = SceneScan(scene_video, 6, 0.3, 3)
    scan.read_log(result.stderr)
    assert scan.ranges() == [(0, 6)]
