"""FFmpeg border detection for one segment."""

import re


class CropScan:
    def __init__(self, source, segment, options):
        self.source = source
        self.segment = segment
        self.options = options
        self.buffer = ""
        self.rectangles = []

    def arguments(self):
        filters = [f"trim=duration={self.segment.end - self.segment.start:.7f}"]
        filters += [[], ["transpose=clock"], ["hflip", "vflip"], ["transpose=cclock"]][
            self.segment.turns
        ]
        if self.options["mode"] == "mvedges":
            filters.append("mestimate")
        filters.append(
            "cropdetect="
            + ":".join(f"{key}={value}" for key, value in self.options.items())
        )
        return [
            "-hide_banner",
            "-nostdin",
            "-ss",
            f"{self.segment.start:.7f}",
            "-i",
            str(self.source),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            ",".join(filters),
            "-progress",
            "pipe:1",
            "-nostats",
            "-f",
            "null",
            "-",
        ]

    def read_log(self, text):
        self.buffer += text
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()
        for line in lines:
            for width, height, x, y in re.findall(
                r"crop=(\d+):(\d+):(\d+):(\d+)", line
            ):
                self.rectangles.append((int(x), int(y), int(width), int(height)))

    def rect(self):
        return self.rectangles[-1]
