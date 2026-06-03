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

from src.agents.phase3_audio._offline_tts import _fake_tts
from src.agents.phase3_audio.trimming import trim_silence, TrimConfig
from src.agents.phase3_audio.duration import duration_ms


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
