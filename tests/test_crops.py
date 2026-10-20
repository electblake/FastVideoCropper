import subprocess

from fastvideocropper.crops import CropScan
from fastvideocropper.segments import Segment


def test_motion_edge_detection(source):
    scan = CropScan(
        source,
        Segment(2, 4, (0, 0, 1, 1), 1, "Custom", False),
        {"mode": "mvedges", "round": 2, "skip": 0},
    )
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
    x, y, width, height = scan.rect()
    assert 0 <= x < x + width <= 240
    assert 0 <= y < y + height <= 320
    assert "progress=end" in result.stdout
