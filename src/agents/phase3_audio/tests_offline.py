from __future__ import annotations

"""AutoShorts Phase 3 — Offline Harness
=================================
No ElevenLabs required.

Generates fake audio bytes from text length, then:
- trims silence
- measures duration
- prints PASS/FAIL

Run:
python -m src.agents.phase3_audio.tests_offline
"""

import io
from pydub import AudioSegment as PydubAudioSegment
from pydub.generators import Sine

from src.agents.phase3_audio.trimming import trim_silence, TrimConfig
from src.agents.phase3_audio.duration import duration_ms


def _fake_tts(text: str, fmt: str = "mp3") -> bytes:
    # 18 cps baseline: 1 sec per ~18 chars; add 300ms head/tail silence.
    secs = max(0.5, len(text) / 18.0)
    tone = Sine(440).to_audio_segment(duration=int(secs * 1000)).apply_gain(-6)
    head = PydubAudioSegment.silent(duration=300)
    tail = PydubAudioSegment.silent(duration=300)
    audio = head + tone + tail

    buf = io.BytesIO()
    audio.export(buf, format=fmt)
    return buf.getvalue()


def main() -> None:
    samples = [
        ("HOOK", "Bhai aaj ka scene simple hai: numbers bolenge.",),
        ("ITEM_1", "A 42 pe, B 19 pe. Gap expose.",),
        ("OUTRO", "Verdict locked.",),
    ]

    cfg = TrimConfig(pad_ms=50, min_silence_len_ms=100)
    for tag, text in samples:
        raw = _fake_tts(text)
        raw_ms = duration_ms(raw)
        trimmed = trim_silence(raw, cfg=cfg)
        trim_ms = duration_ms(trimmed)

        ok = (trim_ms > 0) and (trim_ms < raw_ms)
        status = "PASS" if ok else "FAIL"
        print(f"{status}  {tag}: raw={raw_ms}ms trimmed={trim_ms}ms")

    print("Offline harness complete.")


if __name__ == "__main__":
    main()
