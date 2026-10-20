import subprocess

import pytest

from fastvideocropper.segments import SceneScan


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
