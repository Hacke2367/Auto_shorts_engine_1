# src/sync/audio_trim.py
"""
Single source of truth for the per-segment silence trim applied to voice
segments.

`main.py:concat_audio_ffmpeg` trims each voice segment with `SILENCE_TRIM_FILTER`
before concatenating them into the final voice track. The captions pipeline
measures each segment's duration with the SAME filter so subtitle timing lines
up exactly with what is actually heard — instead of drifting against the raw
(untrimmed) `job["timeline"]` values.

Keep the filter defined here ONLY. Both the audio concat and the caption timing
import it from this module so they can never drift apart.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


# Strip leading/trailing (and internal dead-air) silence at -50 dB.
# This is the exact filter used by the voice concat in main.py.
SILENCE_TRIM_FILTER = (
    "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB:"
    "stop_periods=-1:stop_duration=0.02:stop_threshold=-50dB"
)


def _guess_ffprobe(ffmpeg_path: str) -> str:
    """Derive an ffprobe path from an ffmpeg path ('ffmpeg' -> 'ffprobe')."""
    p = Path(ffmpeg_path)
    name = p.name.lower()
    if "ffmpeg" in name:
        return str(p.with_name(name.replace("ffmpeg", "ffprobe")))
    return "ffprobe"


def trimmed_duration_seconds(ffmpeg: str, audio_path: Path) -> float:
    """
    Return the duration (seconds) of `audio_path` AFTER applying
    `SILENCE_TRIM_FILTER`.

    This is the segment's real length inside the final concatenated voice track.
    The segment is trimmed to a temporary PCM wav (no encoder priming/padding,
    so the duration is exact) and then probed with ffprobe.

    Raises RuntimeError on ffmpeg/ffprobe failure, FileNotFoundError if the
    source segment is missing.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"audio segment not found: {audio_path}")

    ffprobe = _guess_ffprobe(ffmpeg)

    fd, tmp_name = tempfile.mkstemp(suffix=".wav", prefix="_captrim_")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        subprocess.run(
            [
                ffmpeg, "-y",
                "-i", str(audio_path),
                "-af", SILENCE_TRIM_FILTER,
                "-c:a", "pcm_s16le",
                str(tmp),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        r = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(tmp),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return round(float((r.stdout or "").strip()), 3)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"trimmed_duration_seconds failed for {audio_path}: "
            f"{(e.stderr or '').strip() or e}"
        ) from e
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
