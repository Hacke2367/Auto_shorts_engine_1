from __future__ import annotations

"""AutoShorts Phase 3 — Trimming Utilities
=================================
Silence trimming for synthesized speech audio.

Design goals:
- Trim leading/trailing dead-air reliably.
- Preserve a small safety pad to avoid clipping speech.
- Avoid hardcoded fixed-cut approaches; use threshold-based silence detection.

Dependencies:
- pydub (requires ffmpeg available on system PATH for mp3)
"""

import io
import logging
from dataclasses import dataclass

from pydub import AudioSegment as PydubAudioSegment
from pydub.silence import detect_nonsilent

from src.agents.phase3_audio.contracts import AudioTrimError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrimConfig:
    pad_ms: int = 50
    min_silence_len_ms: int = 120
    # How far below average loudness we consider "silence"
    silence_offset_db: float = 16.0
    # If audio is extremely quiet, clamp the threshold
    min_silence_threshold_dbfs: float = -50.0


def _compute_silence_thresh_dbfs(audio: PydubAudioSegment, cfg: TrimConfig) -> float:
    # Use average loudness as baseline; subtract offset.
    baseline = audio.dBFS
    if baseline == float("-inf"):
        # Pure digital silence
        return cfg.min_silence_threshold_dbfs
    thresh = baseline - cfg.silence_offset_db
    return max(thresh, cfg.min_silence_threshold_dbfs)


def _trim_bounds(audio: PydubAudioSegment, cfg: TrimConfig) -> tuple[int, int]:
    thresh = _compute_silence_thresh_dbfs(audio, cfg)
    ranges = detect_nonsilent(
        audio,
        min_silence_len=cfg.min_silence_len_ms,
        silence_thresh=thresh,
        # seek_step=10: silence window is 120ms so checking every 10ms cannot miss it,
        # and is 10× faster than seek_step=1 (3,000 iterations → 300 for a 3s clip).
        seek_step=10,
    )
    if not ranges:
        # No speech detected; return as-is.
        return 0, len(audio)

    start = max(0, ranges[0][0] - cfg.pad_ms)
    end = min(len(audio), ranges[-1][1] + cfg.pad_ms)
    if end <= start:
        logger.warning("Degenerate trim bounds (end <= start) for audio — returning full length.")
        return 0, len(audio)
    return start, end


def trim_silence(
    audio_bytes: bytes,
    input_format: str = "mp3",
    cfg: TrimConfig | None = None,
) -> bytes:
    """Trim leading/trailing silence and return new bytes."""
    cfg = cfg or TrimConfig()
    try:
        audio = PydubAudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
    except Exception as e:
        raise AudioTrimError(f"Failed to decode audio for trimming: {e}") from e

    start, end = _trim_bounds(audio, cfg)
    trimmed = audio[start:end]

    # Export back to bytes
    try:
        buf = io.BytesIO()
        trimmed.export(buf, format=input_format)
        return buf.getvalue()
    except Exception as e:
        raise AudioTrimError(f"Failed to export trimmed audio: {e}") from e
