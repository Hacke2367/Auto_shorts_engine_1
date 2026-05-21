# src/sync/retention_base.py
"""
Retention Base Layer — Universal visual-hold architecture.

Three independent, fail-safe layers are applied during audio-hold pauses:
  A) Living Data     — breathing glow ring around the focus Mobject
  B) Confidence Tick — thin bottom-edge progress bar (Reels-style)
  C) Narrative Cursor — lower-third key-phrase pill (opt-in per template)

Each layer is wrapped in try/except so a failure in one never breaks
the hold or adjacent layers. All cleanups run in LIFO order after
scene.wait().

Public API (backward-compatible with the old retention.py):
  hold_breathing(scene, seconds, focus=None, text="", *, ...)
  banner_scan_hold(scene, banner, seconds, color=WHITE)
"""
from __future__ import annotations

import logging
import numpy as np
from typing import Callable, List, Optional
from manim import *

_log = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Utilities (preserved from original retention.py)
# -----------------------------------------------------------------------

def _get_safe_frame(margin: float = 0.70) -> dict:
    half_w = float(config.frame_width) / 2
    half_h = float(config.frame_height) / 2
    return {
        "left":   -half_w + margin,
        "right":   half_w - margin,
        "top":     half_h - margin,
        "bottom": -half_h + margin,
        "w": float(config.frame_width)  - (2 * margin),
        "h": float(config.frame_height) - (2 * margin),
        "cx": 0.0,
        "cy": 0.0,
    }


def _text_with_fallback(
    content: str,
    *,
    font_size: int,
    weight=BOLD,
    color=WHITE,
    z_index: int = 0,
) -> Text:
    for font_name in ("Montserrat", "Arial", "DejaVu Sans"):
        try:
            return Text(
                content, font=font_name, weight=weight,
                font_size=font_size, color=color,
            ).set_z_index(z_index)
        except Exception:
            continue
    return Text(content, weight=weight, font_size=font_size, color=color).set_z_index(z_index)


# -----------------------------------------------------------------------
# Concept A — Living Data
# A SurroundingRectangle glow ring whose stroke width and opacity breathe
# on a 3-second sine cycle. The original focus Mobject is never modified.
# -----------------------------------------------------------------------

def _apply_living_data_breath(
    scene: Scene,
    focus: Mobject,
    duration: float,
    *,
    period: float = 3.0,
    glow_max_opacity: float = 0.18,
    glow_color: str = "#FFFFFF",
    glow_stroke_width: float = 5.0,
    glow_buff: float = 0.10,
    glow_shape: Optional[Mobject] = None,
) -> List[Callable]:
    """
    Adds a breathing glow ring behind the focus Mobject.
    Returns a list of cleanup callables (run after scene.wait).
    """
    if duration < 0.30:
        return []

    try:
        # Use a provided custom shape or default SurroundingRectangle
        if glow_shape is not None:
            glow = glow_shape
        else:
            glow = SurroundingRectangle(
                focus,
                corner_radius=0.16,
                buff=glow_buff,
                color=glow_color,
                stroke_width=glow_stroke_width,
            )

        glow.set_fill(opacity=0.0)
        glow.set_stroke(opacity=0.0)
        glow.set_z_index(focus.get_z_index() - 1)
        scene.add(glow)

        t0 = float(scene.time)

        def _glow_upd(m, dt):
            t = float(scene.time) - t0
            phase = np.sin(t * (2.0 * np.pi / period))        # −1 … +1
            op  = glow_max_opacity * (0.5 + 0.5 * phase)      #  0 … max_op
            sw  = glow_stroke_width * (1.0 + 0.25 * (0.5 + 0.5 * phase))
            m.set_stroke(opacity=float(np.clip(op, 0.0, glow_max_opacity)), width=sw)

        glow.add_updater(_glow_upd)

        return [
            lambda: glow.clear_updaters(),
            lambda: scene.remove(glow),
        ]

    except Exception as e:
        _log.warning("retention: Living Data layer failed: %s", e, exc_info=True)
        return []


# -----------------------------------------------------------------------
# Concept B — Confidence Tick
# A thin Line-based progress bar anchored to the bottom safe-frame edge.
# Uses put_start_and_end_on so there is zero accumulation drift.
# -----------------------------------------------------------------------

def _build_confidence_tick(
    scene: Scene,
    sf: dict,
    duration: float,
    *,
    accent: str = "#00F0FF",
    track_opacity: float = 0.25,
    fill_opacity: float = 0.50,
    height: float = 0.05,
    width_ratio: float = 0.96,
    y_offset: float = -0.05,
) -> Callable:
    """
    Builds a bottom-edge progress bar that fills over `duration` seconds.
    Returns a single cleanup callable.
    """
    if duration < 0.40:
        return lambda: None

    try:
        bar_w     = sf["w"] * width_ratio
        y_pos     = sf["bottom"] + y_offset
        x_left    = sf["cx"] - bar_w / 2
        x_right   = sf["cx"] + bar_w / 2
        stroke_px = height * 35          # converts unit height → stroke width approx

        # Track (background)
        track = Line([x_left, y_pos, 0], [x_right, y_pos, 0])
        track.set_stroke("#1a1a1a", width=stroke_px, opacity=track_opacity)
        track.set_z_index(950)

        # Fill (progress) — starts as a zero-length line at the left edge
        fill = Line([x_left, y_pos, 0], [x_left + 0.001, y_pos, 0])
        fill.set_stroke(accent, width=stroke_px, opacity=fill_opacity)
        fill.set_z_index(951)

        tick = VGroup(track, fill)
        scene.add(tick)

        t0 = float(scene.time)

        def _tick_upd(m, dt):
            t        = float(scene.time) - t0
            progress = min(1.0, t / max(0.01, duration))
            end_x    = x_left + bar_w * progress
            fill.put_start_and_end_on(
                [x_left,                    y_pos, 0],
                [max(x_left + 0.001, end_x), y_pos, 0],
            )

        tick.add_updater(_tick_upd)

        def _cleanup():
            tick.clear_updaters()
            scene.remove(tick)

        return _cleanup

    except Exception as e:
        _log.warning("retention: Confidence Tick layer failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# Concept C — Narrative Cursor (opt-in)
# Lower-third rounded-pill with a short key phrase derived from the
# segment narration text. Fades in, holds, fades out.
# -----------------------------------------------------------------------

def _derive_key_phrase(text: str) -> str:
    """Auto-derive a ≤3-word key phrase from narration text."""
    if not text or not text.strip():
        return ""
    words = text.split()
    snippet = " ".join(words[:3])
    if len(words) > 3:
        snippet += "…"
    return snippet.upper()


def _build_narrative_cursor(
    scene: Scene,
    sf: dict,
    key_phrase: str,
    duration: float,
    *,
    accent: str = "#00F0FF",
    font_size: int = 20,
    pad_x: float = 0.30,
    pad_y: float = 0.12,
    fade_in_t: float = 0.20,
    fade_out_t: float = 0.20,
    y_offset: float = 1.2,
) -> Callable:
    """
    Builds a lower-third pill badge. Returns a single cleanup callable.
    Suppressed if key_phrase is empty or duration < 0.60s.
    """
    if not key_phrase or duration < 0.60:
        return lambda: None

    # Cap at 4 words
    words = key_phrase.split()
    if len(words) > 4:
        key_phrase = " ".join(words[:4]) + "…"

    try:
        label = _text_with_fallback(
            key_phrase.upper(), font_size=font_size, weight=BOLD, color=WHITE,
        )

        pill = RoundedRectangle(
            width=label.width + pad_x * 2,
            height=label.height + pad_y * 2,
            corner_radius=0.12,
        )
        pill.set_fill("#080808", opacity=0.88)
        pill.set_stroke(accent, width=2.0, opacity=0.85)

        y_pos = sf["bottom"] + y_offset
        pill.move_to([sf["cx"], y_pos, 0])
        label.move_to(pill.get_center())

        pill.set_z_index(960)
        label.set_z_index(961)

        cursor = VGroup(pill, label)
        cursor.set_opacity(0.0)
        scene.add(cursor)

        t0     = float(scene.time)
        hold_t = max(0.0, duration - fade_in_t - fade_out_t)

        def _cursor_upd(m, dt):
            t = float(scene.time) - t0
            if t < fade_in_t:
                op = t / max(0.001, fade_in_t)
            elif t < fade_in_t + hold_t:
                op = 1.0
            elif t < duration:
                op = max(0.0, 1.0 - (t - fade_in_t - hold_t) / max(0.001, fade_out_t))
            else:
                op = 0.0
            cursor.set_opacity(float(np.clip(op, 0.0, 1.0)))

        cursor.add_updater(_cursor_upd)

        def _cleanup():
            cursor.clear_updaters()
            scene.remove(cursor)

        return _cleanup

    except Exception as e:
        _log.warning("retention: Narrative Cursor layer failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# PUBLIC: hold_breathing  (new tiered implementation)
# -----------------------------------------------------------------------

def hold_breathing(
    scene: Scene,
    seconds: float,
    focus: Optional[Mobject] = None,
    text: str = "",
    *,
    accent: str = "#00F0FF",
    enable_tick: bool = True,
    enable_cursor: bool = False,   # opt-in; template authors pass enable_cursor=True
    template_accent: Optional[Callable] = None,
    glow_shape: Optional[Mobject] = None,
) -> None:
    """
    Visual hold during audio narration gaps.

    Layers applied in order (each independent and fail-safe):
      A) Living Data glow    — if focus is provided
      B) Confidence Tick     — if enable_tick (default ON)
      C) Narrative Cursor    — if enable_cursor AND text is non-empty
      D) Template accent     — if template_accent callable is provided

    Args:
        scene:           The active Manim Scene.
        seconds:         Hold duration in seconds.
        focus:           Mobject to apply the glow ring around.
        text:            Narration text; auto-derives key phrase for Concept C.
        accent:          Template accent color for tick + cursor border.
        enable_tick:     Toggle Concept B (default True).
        enable_cursor:   Toggle Concept C (default False — template opts in).
        template_accent: Per-template accent callable(scene, focus, seconds).
        glow_shape:      Override glow shape for non-rectangular focus Mobjects.
    """
    s = float(max(0.0, seconds))
    if s <= 0.001:
        return

    sf       = _get_safe_frame(margin=0.70)
    cleanups: List[Callable] = []

    # — Layer A: Living Data ————————————————————————————————————————
    if focus is not None:
        cleanups.extend(
            _apply_living_data_breath(scene, focus, s, glow_color=accent, glow_shape=glow_shape)
        )

    # — Layer B: Confidence Tick ————————————————————————————————————
    if enable_tick:
        cleanups.append(
            _build_confidence_tick(scene, sf, s, accent=accent)
        )

    # — Layer C: Narrative Cursor ———————————————————————————————————
    if enable_cursor:
        # Always derive the key phrase from the text — never pass raw transcript
        phrase = _derive_key_phrase(text)
        cleanups.append(
            _build_narrative_cursor(scene, sf, phrase, s, accent=accent)
        )

    # — Layer D: Template-specific accent ———————————————————————————
    # Check explicit kwarg first, then fall back to scene-registered accent
    effective_accent = template_accent or getattr(scene, "_retention_accent", None)
    if effective_accent is not None:
        try:
            result = effective_accent(scene, focus, s)
            if callable(result):
                cleanups.append(result)
        except Exception as e:
            _log.warning("retention: template accent layer failed: %s", e, exc_info=True)

    # — Hold ————————————————————————————————————————————————————————
    scene.wait(s)

    # — Cleanup (LIFO order) ————————————————————————————————————————
    for cb in reversed(cleanups):
        try:
            cb()
        except Exception as e:
            _log.warning("retention: cleanup callable failed: %s", e, exc_info=True)


# -----------------------------------------------------------------------
# PUBLIC: banner_scan_hold  (unchanged from original)
# -----------------------------------------------------------------------

def banner_scan_hold(scene: Scene, banner: Mobject, seconds: float, color=WHITE) -> None:
    """Repeating scanline on a banner Mobject during audio holds."""
    s = float(max(0.0, seconds))
    if s <= 0.001:
        return

    try:
        scan = Rectangle(width=banner.width * 0.98, height=0.10).set_stroke(width=0)
        scan.set_fill(color, opacity=0.10)
        scan.set_z_index(getattr(banner, "z_index", 200) + 5)

        t0 = float(scene.time)

        def _upd(m, dt):
            t = float(scene.time) - t0
            a = 0.5 + 0.5 * np.sin(t * 2.2)
            y = banner.get_top()[1] - a * (banner.height - 0.20)
            m.move_to([banner.get_center()[0], y, 0])

        scan.add_updater(_upd)
        scene.add(scan)
        scene.wait(s)
        scan.clear_updaters()
        scene.remove(scan)

    except Exception as e:
        _log.warning("retention: banner_scan_hold failed: %s", e, exc_info=True)
        scene.wait(s)


# -----------------------------------------------------------------------
# Scene-level accent registry
# -----------------------------------------------------------------------

def register_template_accent(scene: Scene, accent_fn: Callable) -> None:
    """
    Register a default accent for every hold_breathing call on this scene.
    Call once at the top of construct() — no per-call template_accent= needed.

    The accent_fn must accept (scene, focus, seconds) and return a cleanup
    callable (or None).
    """
    scene._retention_accent = accent_fn


__all__ = ["hold_breathing", "banner_scan_hold", "register_template_accent"]
