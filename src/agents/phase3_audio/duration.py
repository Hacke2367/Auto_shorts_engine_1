from __future__ import annotations

"""AutoShorts Phase 3 — Duration Helpers
================================
Compute physical audio duration reliably from bytes.

Uses pydub for decode; mp3 requires ffmpeg installed.
"""

import io
from pydub import AudioSegment as PydubAudioSegment

from src.agents.phase3_audio.contracts import AudioTrimError


def duration_ms(audio_bytes: bytes, input_format: str = "mp3") -> int:
    try:
        audio = PydubAudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
    except Exception as e:
        raise AudioTrimError(f"Failed to decode audio for duration: {e}") from e
    return int(len(audio))


def duration_sec(audio_bytes: bytes, input_format: str = "mp3") -> float:
    ms = duration_ms(audio_bytes, input_format=input_format)
    return round(ms / 1000.0, 3)
