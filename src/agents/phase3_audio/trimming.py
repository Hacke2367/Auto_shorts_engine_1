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
    # Small pad BEFORE the first word so speech doesn't start abruptly.
    lead_pad_ms: int = 40
    # Generous release AFTER the last word so endings are never clipped. The old
    # symmetric 50 ms pad chopped soft final syllables (e.g. the HOOK's last word).
    trail_pad_ms: int = 200
    # Only stretches of dead-air at least this long count as a gap to act on.
    min_silence_len_ms: int = 200
    # Collapse any internal pause longer than this down to this length. TTS often
    # inserts 1–1.5 s pauses between short sentences which read as "slow/gappy"
    # and (because the measured duration feeds job timeline) desync the visuals.
    max_internal_gap_ms: int = 260
    # How far below average loudness we consider "silence". Higher than the old 16
    # so soft word-tails are NOT mistaken for silence and trimmed.
    silence_offset_db: float = 22.0
    # If audio is extremely quiet, clamp the threshold.
    min_silence_threshold_dbfs: float = -45.0


def _compute_silence_thresh_dbfs(audio: PydubAudioSegment, cfg: TrimConfig) -> float:
    # Use average loudness as baseline; subtract offset.
    baseline = audio.dBFS
    if baseline == float("-inf"):
        # Pure digital silence
        return cfg.min_silence_threshold_dbfs
    thresh = baseline - cfg.silence_offset_db
    return max(thresh, cfg.min_silence_threshold_dbfs)


def _retime_audio(audio: PydubAudioSegment, cfg: TrimConfig) -> PydubAudioSegment:
    """Trim leading/trailing dead-air AND collapse over-long internal pauses.

    Leading silence is cut to ``lead_pad_ms``; a ``trail_pad_ms`` release is kept
    after the final word; any internal gap longer than ``max_internal_gap_ms`` is
    shortened to that cap using the real room-tone right before the next phrase
    (so the rhythm stays natural rather than splicing in synthetic silence).
    """
    thresh = _compute_silence_thresh_dbfs(audio, cfg)
    ranges = detect_nonsilent(
        audio,
        min_silence_len=cfg.min_silence_len_ms,
        silence_thresh=thresh,
        # seek_step=10: silence window is >=200ms so checking every 10ms cannot
        # miss it, and is ~10× faster than seek_step=1.
        seek_step=10,
    )
    if not ranges:
        # No speech detected; return as-is rather than risk nuking the whole clip.
        return audio

    total = len(audio)
    # First phrase, with a small leading pad.
    out = audio[max(0, ranges[0][0] - cfg.lead_pad_ms): ranges[0][1]]

    # Subsequent phrases: keep the gap as-is if short, else collapse to the cap.
    for i in range(1, len(ranges)):
        prev_end = ranges[i - 1][1]
        cur_start, cur_end = ranges[i]
        gap = cur_start - prev_end
        if gap <= cfg.max_internal_gap_ms:
            out += audio[prev_end:cur_end]
        else:
            out += audio[cur_start - cfg.max_internal_gap_ms: cur_end]

    # Trailing release after the last word.
    end = min(total, ranges[-1][1] + cfg.trail_pad_ms)
    out += audio[ranges[-1][1]:end]
    return out


def trim_silence(
    audio_bytes: bytes,
    input_format: str = "mp3",
    cfg: TrimConfig | None = None,
) -> bytes:
    """Trim leading/trailing silence, collapse long internal pauses, return bytes."""
    cfg = cfg or TrimConfig()
    try:
        audio = PydubAudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
    except Exception as e:
        raise AudioTrimError(f"Failed to decode audio for trimming: {e}") from e

    trimmed = _retime_audio(audio, cfg)

    # Export back to bytes
    try:
        buf = io.BytesIO()
        trimmed.export(buf, format=input_format)
        return buf.getvalue()
    except Exception as e:
        raise AudioTrimError(f"Failed to export trimmed audio: {e}") from e
