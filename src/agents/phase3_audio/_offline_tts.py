from __future__ import annotations

"""AutoShorts Phase 3 Audio Engine — Offline TTS Stub
=======================================================
Provides a deterministic fake TTS implementation for offline testing and
development. Imported by both the runner (offline mode) and the offline test
harness. Lives in the production package so runner.py does not import test files.
"""

import io

from pydub import AudioSegment as PydubAudioSegment
from pydub.generators import Sine


def _fake_tts(text: str, fmt: str = "mp3") -> bytes:
    """Generate a synthetic audio tone proportional to text length.

    Produces a 440 Hz sine tone flanked by 300 ms of silence so the trim
    pipeline has real silence to detect. Duration scales with text at 18 CPS.
    """
    secs = max(0.5, len(text) / 18.0)
    tone = Sine(440).to_audio_segment(duration=int(secs * 1000)).apply_gain(-6)
    head = PydubAudioSegment.silent(duration=300)
    tail = PydubAudioSegment.silent(duration=300)
    audio = head + tone + tail

    buf = io.BytesIO()
    audio.export(buf, format=fmt)
    return buf.getvalue()
