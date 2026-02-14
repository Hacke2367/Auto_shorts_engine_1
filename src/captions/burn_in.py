# src/captions/burn_in.py
from __future__ import annotations
import subprocess
from pathlib import Path


def _ffmpeg_filter_path(p: Path) -> str:
    """
    Makes Windows-safe path for ffmpeg filter arguments:
    C:\a\b\c.ass -> C\:/a/b/c.ass  (colon escaped)
    """
    s = p.resolve().as_posix()       # C:/a/b/c.ass
    s = s.replace(":/", r"\:/")      # C\:/a/b/c.ass
    return s


def burn_in_ass(
    ffmpeg: str,
    video_in: Path,
    ass_path: Path,
    video_out: Path,
) -> None:
    video_out.parent.mkdir(parents=True, exist_ok=True)

    ass_arg = _ffmpeg_filter_path(ass_path)

    # ass filter uses libass internally
    vf = f"ass='{ass_arg}'"

    cmd = [
        ffmpeg, "-y",
        "-i", str(video_in),
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-c:a", "copy",
        str(video_out),
    ]
    subprocess.run(cmd, check=True)
