# src/captions/ass_renderer.py
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Any, List

from .styles import get_style_preset
from .script_loader import pick_text_for_lang
from .aligner import word_karaoke_equal_split, split_words, wrap_words_to_lines

_log = logging.getLogger(__name__)


def _ass_time(t: float) -> str:
    """
    Convert seconds -> ASS time format: H:MM:SS.CC
    """
    if t < 0:
        t = 0.0
    cs = int(round(t * 100.0))
    s = cs // 100
    cc = cs % 100
    mm = s // 60
    ss = s % 60
    hh = mm // 60
    mm = mm % 60
    return f"{hh}:{mm:02d}:{ss:02d}.{cc:02d}"


def _make_style_line(style_name: str, st: Dict[str, Any], margin_v: int) -> str:
    """
    Build one ASS style line.
    """
    return (
        "Style: {name},{font},{size},{pri},{sec},{out},{back},"
        "{bold},{italic},0,0,100,100,0,0,{border},{outline},{shadow},"
        "{align},{ml},{mr},{mv},1"
    ).format(
        name=style_name,
        font=st["font"],
        size=st["font_size"],
        pri=st["primary_color"],
        sec="&H00000000",
        out=st["outline_color"],
        back=st["back_color"],
        bold=st["bold"],
        italic=st["italic"],
        border=st["border_style"],
        outline=st["outline"],
        shadow=st["shadow"],
        align=st["alignment"],
        ml=st["margin_l"],
        mr=st["margin_r"],
        mv=margin_v,
    )


def _ass_escape_text(s: str) -> str:
    r"""
    ASS-safe escaping for normal (non-tag) text.
    NOTE: We DO NOT use this on strings that contain ASS tags like {\kf...}.
    """
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\\", r"\\")
    s = s.replace("{", r"\{").replace("}", r"\}")
    s = s.replace("\n", r"\N")
    return s


def _split_words_keep_punct(text: str) -> list[str]:
    """
    Split by spaces, punctuation stays attached with word.
    """
    text = " ".join(str(text).strip().split())
    if not text:
        return []
    return text.split(" ")


def _distribute_cs(total_cs: int, words: list[str]) -> list[int]:
    """
    Distribute centiseconds across words.
    Longer words get slightly more time.
    """
    if not words:
        return []

    total_cs = max(1, int(total_cs))
    weights = [max(1, len(w)) for w in words]
    wsum = sum(weights)

    cs = [max(1, int(round(total_cs * (w / wsum)))) for w in weights]

    diff = total_cs - sum(cs)
    i = 0
    while diff != 0 and cs:
        j = i % len(cs)
        if diff > 0:
            cs[j] += 1
            diff -= 1
        else:
            if cs[j] > 1:
                cs[j] -= 1
                diff += 1
        i += 1
    return cs


def _to_reveal_words_ass(text: str, duration_sec: float) -> str:
    r"""
    "Premium" word-wise reveal using ASS karaoke tags (\kf).
    This is NOT true forced-alignment karaoke. It's an approximation:
    - segment duration split across words (weighted by word length)

    Trick:
    - {\2a&HFF&}  => secondary color fully transparent for unrevealed portion
    - {\kfXX}word => word revealed over XX centiseconds
    """
    safe = _ass_escape_text(text)  # escape user text only (not our tags)
    words = _split_words_keep_punct(safe)
    if not words:
        return safe

    total_cs = int(round(max(0.2, float(duration_sec)) * 100.0))
    per_word_cs = _distribute_cs(total_cs, words)

    out = [r"{\2a&HFF&}"]
    for w, cs in zip(words, per_word_cs):
        out.append(r"{\kf" + str(int(cs)) + r"}" + w)

    return " ".join(out)


def _with_premium_entry_tags(text: str, dur_s: float = 0.0) -> str:
    """
    Subtle per-dialogue entry + exit treatment for premium preset.
    Entry: fade-in 140ms + blur easing over 180ms.
    Exit: blur-out over the last 100ms (timed transform from dur_s).
    """
    if not text:
        return ""
    entry = r"{\fad(140,100)\blur0.90\bord3.4\t(0,180,\blur0.35\bord2.8)}"
    if dur_s > 0.15:
        dur_cs = int(round(dur_s * 100))
        exit_start = max(0, dur_cs - 100)
        exit_tag = r"{\t(" + str(exit_start) + r"," + str(dur_cs) + r",\blur0.55\bord3.2)}"
        return entry + text + exit_tag
    return entry + text


def render_ass(
    out_path: Path,
    job: Dict[str, Any],
    timeline_segments: List[Dict[str, Any]],
    script_map: Dict[str, Any],
) -> None:
    """
    Create an ASS subtitle file based on job['captions'] config.
    Supports:
      - mode: plain
      - mode: reveal_words  (word-by-word reveal premium)
      - mode: karaoke       (equal split karaoke)
    """
    captions = job.get("captions") if isinstance(job.get("captions"), dict) else {}
    render_cfg = captions.get("render") if isinstance(captions.get("render"), dict) else {}
    style_cfg = render_cfg.get("style") if isinstance(render_cfg.get("style"), dict) else {}

    preset_name = str(style_cfg.get("preset", "modern_clean"))
    preset_key = preset_name.strip().lower()
    safe_margin_px = int(style_cfg.get("safe_margin_px", 80))
    max_lines = int(style_cfg.get("max_lines", 2))

    video_cfg = job.get("video") if isinstance(job.get("video"), dict) else {}
    res_x = int(video_cfg.get("w", 1080))
    res_y = int(video_cfg.get("h", 1920))

    tracks = render_cfg.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        tracks = [{"lang": "en", "mode": "plain", "position": "bottom"}]

    st = get_style_preset(preset_name, safe_margin_px=safe_margin_px)
    use_premium_entry = preset_key == "modern_premium"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("[Script Info]")
    lines.append("ScriptType: v4.00+")
    lines.append(f"PlayResX: {res_x}")
    lines.append(f"PlayResY: {res_y}")
    lines.append("WrapStyle: 2")
    lines.append("ScaledBorderAndShadow: yes")
    lines.append("YCbCr Matrix: TV.709")
    lines.append("")

    # Styles
    lines.append("[V4+ Styles]")
    lines.append(
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding"
    )

    def margin_for_pos(pos: str) -> int:
        pos = (pos or "bottom").strip().lower()
        if pos == "above_bottom":
            return safe_margin_px + 130
        return safe_margin_px

    style_names_by_track: List[str] = []
    for i, tr in enumerate(tracks):
        pos = str(tr.get("position", "bottom"))
        style_name = f"Cap{i}_{pos}"
        style_names_by_track.append(style_name)
        mv = margin_for_pos(pos)
        lines.append(_make_style_line(style_name, st, mv))

    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text")

    # Events
    for seg in timeline_segments:
        name = seg["name"]
        start = float(seg["start"])
        end = float(seg["end"])

        seg_data = script_map.get(name, {})
        if name not in script_map:
            _log.warning(
                "captions: no script entry for segment '%s' — segment will have no captions",
                name,
            )
        if not isinstance(seg_data, dict):
            seg_data = {}

        for ti, tr in enumerate(tracks):
            lang = str(tr.get("lang", "en"))
            mode = str(tr.get("mode", "plain")).strip().lower()
            style_name = style_names_by_track[ti]

            txt = pick_text_for_lang(seg_data, lang=lang, fallback_lang="default")

            if not str(txt).strip():
                continue

            # Canonical duration: computed from start/end (already centisecond-rounded
            # by timeline_resolver). Used consistently for all modes.
            dur_s = max(0.01, float(end) - float(start))

            if mode == "karaoke":
                # simple equal split karaoke
                pairs = word_karaoke_equal_split(txt, dur_seconds=dur_s)
                words = [w for (w, _) in pairs]
                wrapped = wrap_words_to_lines(words, max_lines=max_lines, max_chars_per_line=28)

                karaoke_chunks: List[str] = []
                word_index = 0
                for li, line in enumerate(wrapped):
                    line_words = split_words(line.replace(" ...", "").strip())
                    for _w in line_words:
                        if word_index >= len(pairs):
                            break
                        w, cs = pairs[word_index]
                        karaoke_chunks.append(r"{\k" + str(cs) + "}" + _ass_escape_text(w))
                        karaoke_chunks.append(" ")
                        word_index += 1
                    if li < len(wrapped) - 1:
                        karaoke_chunks.append(r"\N")

                text_out = "".join(karaoke_chunks).strip()
                if use_premium_entry:
                    text_out = _with_premium_entry_tags(text_out, dur_s=dur_s)
                dialogue = f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},{style_name},,0,0,0,,{text_out}"
                lines.append(dialogue)

            else:
                # plain OR reveal_words
                words = split_words(txt)
                wrapped = wrap_words_to_lines(words, max_lines=max_lines, max_chars_per_line=32)

                if mode == "reveal_words":
                    # Split duration across lines by word-count
                    line_counts = [max(1, len(split_words(line.strip()))) for line in wrapped]
                    total = sum(line_counts) if line_counts else 1

                    remaining = float(dur_s)
                    reveal_lines: List[str] = []
                    for li, line in enumerate(wrapped):
                        if li == len(wrapped) - 1:
                            line_dur = max(0.01, remaining)
                        else:
                            frac = line_counts[li] / total
                            line_dur = max(0.01, float(dur_s) * frac)
                            remaining -= line_dur

                        reveal_lines.append(_to_reveal_words_ass(line, line_dur))

                    ass_text = r"\N".join(reveal_lines).strip()
                else:
                    # plain
                    ass_text = r"\N".join(_ass_escape_text(x) for x in wrapped).strip()

                if use_premium_entry:
                    ass_text = _with_premium_entry_tags(ass_text, dur_s=dur_s)
                dialogue = f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},{style_name},,0,0,0,,{ass_text}"
                lines.append(dialogue)

    out_path.write_text("\n".join(lines), encoding="utf-8")
