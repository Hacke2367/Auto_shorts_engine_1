# src/captions/aligner.py
from __future__ import annotations
import re
from typing import List, Tuple


_WORD_RE = re.compile(r"\S+")


def split_words(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    return _WORD_RE.findall(text)


def word_karaoke_equal_split(text: str, dur_seconds: float) -> List[Tuple[str, int]]:
    """
    Returns list of (word, centiseconds).
    Simple equal split across words.
    """
    words = split_words(text)
    if not words:
        return []

    total_cs = max(1, int(round(dur_seconds * 100.0)))
    n = len(words)

    base = max(1, total_cs // n)
    rem = max(0, total_cs - base * n)

    out: List[Tuple[str, int]] = []
    for i, w in enumerate(words):
        cs = base + (1 if i < rem else 0)
        out.append((w, cs))
    return out


def wrap_words_to_lines(words: List[str], max_lines: int = 2, max_chars_per_line: int = 28) -> List[str]:
    """
    Very simple line wrapper: makes up to max_lines lines.
    """
    if not words:
        return [""]

    lines: List[str] = []
    cur: List[str] = []

    def cur_len(tokens: List[str]) -> int:
        if not tokens:
            return 0
        return len(" ".join(tokens))

    for w in words:
        if not cur:
            cur = [w]
            continue

        if cur_len(cur + [w]) <= max_chars_per_line:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
            if len(lines) >= max_lines - 1:
                break

    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))

    # If too many words, last line gets "..."
    used_words = sum(len(l.split()) for l in lines)
    if used_words < len(words) and lines:
        lines[-1] = (lines[-1] + " ...").strip()

    return lines
