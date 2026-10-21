"""Scene boundaries and per-segment crop settings."""

import re
from dataclasses import dataclass
from itertools import pairwise


@dataclass
class Segment:
    start: float
    end: float
    rect: tuple[float, float, float, float]
    rotation: int
    preset: str
    locked: bool
    padding_x: int = 0
    padding_y: int = 0


class SceneScan:
    def __init__(self, source, duration, threshold, minimum, framestep=1, threads=0):
        self.source = source
        self.duration = duration
        self.threshold = threshold
        self.minimum = minimum
        self.framestep = framestep
        self.threads = threads
        self.boundaries = [0.0]
        self.buffer = ""

    def arguments(self):
        return [
            "-hide_banner",
            "-nostdin",
            "-threads:v",
            str(self.threads),
            "-i",
            str(self.source),
            "-filter_complex",
            (
                "[0:v:0]split=2[scan][scenes];"
                f"[scenes]framestep={self.framestep},"
                f"select='gt(scene,{self.threshold})',showinfo,nullsink"
            ),
            "-map",
            "[scan]",
            "-an",
            "-progress",
            "pipe:1",
            "-stats_period",
            "0.5",
            "-nostats",
            "-fps_mode",
            "vfr",
            "-f",
            "null",
            "-",
        ]

    def read_log(self, text):
        self.buffer += text
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()
        for line in lines:
            for value in re.findall(r"pts_time:([\d.eE+-]+)", line):
                timestamp = float(value)
                if (
                    timestamp > self.boundaries[-1]
                    and timestamp - self.boundaries[-1] >= self.minimum
                    and self.duration - timestamp >= self.minimum
                    and timestamp < self.duration
                ):
                    self.boundaries.append(timestamp)

    def ranges(self):
        return list(pairwise([*self.boundaries, self.duration]))
