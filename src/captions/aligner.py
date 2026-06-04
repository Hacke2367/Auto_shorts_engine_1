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
    Returns [] for empty input (callers should guard against an empty list).
    """
    if not words:
        return []

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
    used_words = sum(len(split_words(l)) for l in lines)
    if used_words < len(words) and lines:
        lines[-1] = (lines[-1] + " ...").strip()

    return lines


def pack_words_into_chunks(
    words: List[str],
    max_lines: int = 2,
    max_chars_per_line: int = 32,
) -> List[List[str]]:
    """
    Greedily pack ALL words into a sequence of chunks. No words are dropped.

    Each chunk holds up to `max_lines` lines, and each line holds up to
    `max_chars_per_line` characters. When a chunk fills up, a new chunk is
    started. A word longer than `max_chars_per_line` is placed on its own
    line rather than dropped (prevents truncation / infinite loops).

    Returns a list of chunks; each chunk is a list of line strings.
    Returns [] for empty input.

    This replaces the single truncate-to-2-lines behaviour of
    `wrap_words_to_lines`, so long segment captions are shown in full
    across multiple timed chunks instead of being cut off with "...".
    """
    if not words:
        return []

    max_lines = max(1, int(max_lines))

    chunks: List[List[str]] = []
    cur_lines: List[str] = []
    cur: List[str] = []

    def line_len(tokens: List[str]) -> int:
        return len(" ".join(tokens)) if tokens else 0

    for w in words:
        if not cur:
            cur = [w]
            continue

        if line_len(cur + [w]) <= max_chars_per_line:
            cur.append(w)
        else:
            # current line is full -> commit it
            cur_lines.append(" ".join(cur))
            cur = [w]
            if len(cur_lines) >= max_lines:
                # chunk is full -> commit it and start fresh
                chunks.append(cur_lines)
                cur_lines = []

    # flush trailing line + chunk
    if cur:
        cur_lines.append(" ".join(cur))
    if cur_lines:
        chunks.append(cur_lines)

    return chunks
