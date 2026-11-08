"""Shared editing effects for every template (finance skin, 2026-11).

Each helper returns an Animation (or plays a short beat) with an explicit
run_time, so the caller's segment budget stays in charge. Segment ENDS are
anchored to the master clock by ``sync_hold``, so nothing here can cause
audio/visual drift: a longer effect only shortens the hold that follows it.

Use effects on beats (a reveal, a twist, a winner), never on every line: an
effect that repeats stops reading as an effect.
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Tuple

import numpy as np
from manim import (
    TAU, Animation, FadeIn, FadeOut, Rectangle, UpdateFromAlphaFunc, VGroup,
    config,
)
from manim import rate_functions as rf

# "$29T", "+125%", "-27%", "3.2x", "₹1.07 Cr", "$4,705/oz", "-$5"
_NUM_RE = re.compile(
    r"^(?P<pre>[^\d\-+−.]*)(?P<sign>[+\-−]?)(?P<pre2>[^\d.]*)"
    r"(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suf>.*)$"
)


def split_number(text: str) -> Optional[Tuple[str, float, int, str, bool]]:
    """('$', 29.0, 0, 'T', False) for "$29T"; None when there is no number."""
    m = _NUM_RE.match(str(text).strip())
    if not m:
        return None
    num = m["num"]
    decimals = len(num.split(".", 1)[1]) if "." in num else 0
    return m["pre"] + m["sign"] + m["pre2"], float(num.replace(",", "")), decimals, m["suf"], "," in num


def count_text(final_text: str, a: float = 0.0) -> str:
    """The odometer string at progress ``a`` (0..1): "0.0%" for "33.5%" at 0.
    ``final_text`` itself at a >= 1 or when it has no number. Use a=0 to pre-set
    a label before it is revealed, so it does not flash the final value first."""
    parts = split_number(final_text)
    if parts is None or a >= 1.0:
        return final_text
    pre, val, dec, suf, comma = parts
    v = val * rf.ease_out_cubic(a)
    return f"{pre}{v:,.{dec}f}{suf}" if comma else f"{pre}{v:.{dec}f}{suf}"


def count_up(mob, final_text: str, make: Callable[[str], object], run_time: float = 0.6) -> Animation:
    """Odometer: the number inside ``final_text`` rolls up from 0 and lands
    exactly on ``final_text``. ``make(s)`` returns the positioned/fitted mobject
    for string ``s``; ``mob`` becomes it. Text without a number just appears."""
    last = [None]

    def upd(m, a):
        s = count_text(final_text, a)
        if s != last[0]:  # only rebuild when the string changes (Pango is slow)
            m.become(make(s))
            last[0] = s

    return UpdateFromAlphaFunc(mob, upd, run_time=run_time)


def shake(mob, amp: float = 0.07, run_time: float = 0.28, cycles: float = 4.0) -> Animation:
    """Decaying camera-style shake; ends exactly where it started."""
    c0 = [None]

    def upd(m, a):
        if c0[0] is None:
            c0[0] = m.get_center().copy()
        d = amp * (1.0 - a) * np.sin(a * cycles * TAU)
        m.move_to(c0[0] + np.array([d, -0.6 * d, 0.0]))

    return UpdateFromAlphaFunc(mob, upd, run_time=run_time)


def slam_in(mob, scale: float = 1.9, run_time: float = 0.32) -> Animation:
    """Big -> settle with a small overshoot. ``mob`` must NOT be opacity-0:
    FadeIn animates from transparent to the mobject's own style."""
    return FadeIn(mob, scale=scale, run_time=run_time, rate_func=rf.ease_out_back)


def pop(mob, factor: float = 1.25, run_time: float = 0.25) -> Animation:
    """Scale up and back (score badge, value lock). Driven by alpha, so it still
    lands on the original size inside a play() that sets its own rate_func
    (play kwargs override every child animation's rate_func)."""
    base = [None]

    def upd(m, a):
        if base[0] is None:
            base[0] = m.copy()
        m.become(base[0]).scale(1.0 + (factor - 1.0) * rf.there_and_back(min(1.0, max(0.0, a))))

    return UpdateFromAlphaFunc(mob, upd, run_time=run_time)


def frame_flash(scene, color: str = "#FFFFFF", opacity: float = 0.22, run_time: float = 0.14) -> None:
    """Full-frame flash for a hard cut accent (2-4 frames)."""
    r = Rectangle(width=config.frame_width * 1.1, height=config.frame_height * 1.1)
    r.set_stroke(width=0).set_fill(color, 0.0).set_z_index(950)
    scene.add(r)
    scene.play(r.animate(rate_func=rf.there_and_back).set_fill(opacity=opacity), run_time=run_time)
    scene.remove(r)


def fly_to(mob, target_point, run_time: float = 0.45) -> Animation:
    """Fly a small label (e.g. "+1") into ``target_point`` and vanish."""
    return FadeOut(mob, target_position=target_point, scale=0.45, run_time=run_time, rate_func=rf.ease_in_cubic)


def build_progress(n: int, y: float, width: float, color: str, dim: str = "#FFFFFF") -> VGroup:
    """Story-style segmented progress bar (one pip per round)."""
    n = max(1, int(n))
    gap = 0.10
    seg_w = (width - gap * (n - 1)) / n
    pips = VGroup()
    for i in range(n):
        base = Rectangle(width=seg_w, height=0.055).set_stroke(width=0).set_fill(dim, 0.18)
        fill = Rectangle(width=seg_w, height=0.055).set_stroke(width=0).set_fill(color, 0.95)
        fill.stretch(0.001, 0, about_edge=np.array([-1.0, 0.0, 0.0]))
        pip = VGroup(base, fill).move_to([-width / 2 + seg_w / 2 + i * (seg_w + gap), y, 0])
        fill.align_to(base, np.array([-1.0, 0.0, 0.0]))
        pips.add(pip)
    pips.set_z_index(900)
    pips.seg_w = seg_w
    return pips


def progress_fill(pips: VGroup, i: int, run_time: float = 0.35) -> Animation:
    """Fill pip ``i`` left-to-right."""
    base, fill = pips[i]
    target = base.copy().set_fill(fill.get_fill_color(), 0.95)
    return fill.animate(run_time=run_time, rate_func=rf.ease_out_cubic).become(target)


def _fit_text(s: str, font: str, size: int, color: str, max_w: float):
    from manim import BOLD, Text
    t = Text(s, font=font, font_size=size, color=color, weight=BOLD)
    if t.width > max_w:
        t.scale_to_fit_width(max_w)
    return t


def cold_open(scene, meta: dict, y: float, budget: float, *, font: str, gold: str, white: str = "#FFFFFF") -> float:
    """Hook card on screen at frame 0: HOOK_LINE / HOOK_STAT (big) / HOOK_SUB,
    settles, then zooms through the camera. Plays nothing without HOOK_STAT.
    Returns seconds used (caller's hook segment budget)."""
    stat_s = str(meta.get("HOOK_STAT", "") or "").strip()
    if not stat_s:
        return 0.0
    t0 = float(scene.time)
    W = float(config.frame_width)
    stat = _fit_text(stat_s, font, 190, gold, W * 0.80)
    parts = []
    for key in ("HOOK_LINE", None, "HOOK_SUB"):
        if key is None:
            parts.append(stat)
            continue
        s = str(meta.get(key, "") or "").strip()
        if s:
            parts.append(_fit_text(s.upper(), font, 40, white, W * 0.86))
    card = VGroup(*parts).arrange(np.array([0.0, -1.0, 0.0]), buff=0.38).move_to([0.0, y, 0.0])
    card.set_z_index(400)

    total = max(1.0, min(1.8, budget * 0.55))
    stat.scale(1.25)
    scene.add(card)  # visible at t=0
    scene.play(stat.animate.scale(1 / 1.25), run_time=0.45, rate_func=rf.ease_out_cubic)
    scene.wait(max(0.0, total - 0.45 - 0.28))
    scene.play(card.animate.scale(2.6).set_opacity(0.0), run_time=0.28, rate_func=rf.ease_in_cubic)
    scene.remove(card)
    frame_flash(scene, opacity=0.18, run_time=0.12)
    return float(scene.time) - t0


def build_loop_card(meta: dict, fallback_q: str, y: float, *, font: str, gold: str, white: str = "#FFFFFF") -> VGroup:
    """Outro question card in the cold-open style (OUTRO_Q / OUTRO_SUB meta), so the
    Shorts replay seam reads as one loop. Play it with ``slam_in``."""
    W = float(config.frame_width)
    q = str(meta.get("OUTRO_Q", "") or fallback_q).strip()
    sub = str(meta.get("OUTRO_SUB", "") or "comment mein batao").strip()
    card = VGroup(
        _fit_text(q.upper(), font, 96, gold, W * 0.86),
        _fit_text(sub.upper(), font, 40, white, W * 0.86),
    ).arrange(np.array([0.0, -1.0, 0.0]), buff=0.40).move_to([0.0, y, 0.0])
    card.set_z_index(400)
    return card


if __name__ == "__main__":  # self-check: python -m src.fx
    assert split_number("$29T") == ("$", 29.0, 0, "T", False)
    assert split_number("+125%") == ("+", 125.0, 0, "%", False)
    assert split_number("-27%") == ("-", 27.0, 0, "%", False)
    assert split_number("3.2x") == ("", 3.2, 1, "x", False)
    assert split_number("$4,705/oz") == ("$", 4705.0, 0, "/oz", True)
    assert split_number("₹1.07 Cr") == ("₹", 1.07, 2, " Cr", False)
    assert split_number("Losses") is None
    assert count_text("33.5% year-over-year") == "0.0% year-over-year"
    assert count_text("$4,705/oz", 1.0) == "$4,705/oz" and count_text("N/A") == "N/A"
    from manim import Square
    for _rf, _peak in ((rf.smooth, 0.5), (rf.ease_out_cubic, 0.2)):  # play(rate_func=...) overrides the child's
        sq = Square()
        an = pop(sq, 1.5, 0.3)
        an.rate_func = _rf
        an.begin()
        an.interpolate(_peak)
        assert sq.width > 2.4
        an.finish()
        assert abs(sq.width - 2.0) < 1e-6
    print("fx self-check: PASS")
