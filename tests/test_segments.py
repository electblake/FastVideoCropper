import subprocess

from fastvideocropper.segments import SceneScan


def test_real_scene_detection(scene_video):
    scan = SceneScan(scene_video, 6, 0.3, 1)
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
    assert scan.ranges() == [(0, 2), (2, 4), (4, 6)]
    scan = SceneScan(scene_video, 6, 0.3, 3)
    scan.read_log(result.stderr)
    assert scan.ranges() == [(0, 6)]
