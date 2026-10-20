"""FFmpeg command construction; coordinates are rotated source pixels."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Export:
    source: Path
    rect: tuple[float, float, float, float]
    turns: int
    start: float
    end: float
    square_pixels: bool = False
    encoder: str = "libx265"
    device: int = 0
    segment_number: int = 1
    exact_crop: bool = False

    @property
    def output(self):
        return self.source.with_stem(
            f"{self.source.stem}_SEGMENT_{self.segment_number:03d}_CROPPED"
        )

    def arguments(self):
        x, y, w, h = self.rect
        filters = [[], ["transpose=clock"], ["hflip", "vflip"], ["transpose=cclock"]][
            self.turns
        ].copy()
        filters.append(f"crop={w:.7f}:{h:.7f}:{x:.7f}:{y:.7f}")
        if self.exact_crop:
            filters[-1] += ":exact=1"
        if self.square_pixels:
            filters += ["scale=trunc(iw*sar/2)*2:ih", "setsar=1"]
        quality = {
            "libx265": ["-crf", "18", "-fps_mode", "passthrough"],
            "hevc_nvenc": [
                "-gpu",
                str(self.device),
                "-rc",
                "vbr",
                "-b:v",
                "0",
                "-cq",
                "18",
            ],
            "hevc_qsv": ["-global_quality", "18"],
            "hevc_amf": ["-rc", "cqp", "-qp_i", "18", "-qp_p", "18"],
        }[self.encoder]
        return [
            "-y",
            "-hide_banner",
            "-ss",
            f"{self.start:.7f}",
            "-i",
            str(self.source),
            "-c:v",
            self.encoder,
            "-c:a",
            "copy",
            *quality,
            "-ss",
            "0",
            "-t",
            f"{self.end - self.start:.7f}",
            "-vf",
            ",".join(filters),
            "-progress",
            "pipe:1",
            "-nostats",
            str(self.output),
        ]


def padded_rect(rect, padding_x, padding_y, width, height):
    x, y, w, h = rect
    left, top = max(0, x - padding_x), max(0, y - padding_y)
    right = min(width, x + w + padding_x)
    bottom = min(height, y + h + padding_y)
    return left, top, right - left, bottom - top


def rotate_rect(rect, width, height):
    x, y, w, h = rect
    return height - y - h, x, h, w
