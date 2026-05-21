# src/sync/retention_accents.py
"""
Per-template retention accent functions.

Each function:
  - Receives (scene, focus, seconds)
  - Adds purely additive Mobjects / updaters (never mutates template objects)
  - Returns a cleanup callable that removes everything it added
  - Is wrapped in try/except — a broken accent never kills the hold

Wire up in construct() with ONE call:
    from src.sync.retention_accents import retain_accent_<template>
    from src.sync.retention_base  import register_template_accent
    register_template_accent(self, lambda s, f, t: retain_accent_<template>(s, f, t, ...))

Design rule: animations are driven PURELY by the geometric structure of
the focus Mobject (bounding box, center, colour). Never topic-specific.
"""
from __future__ import annotations

import logging
import math
import numpy as np
from typing import Callable, Optional
from manim import *

_log = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# 1. bar_chart — Trailing Edge Ghost
# A soft vertical cap line at the right edge of the focus (the active bar).
# Breathes opacity on a 2.5-second cycle.
# -----------------------------------------------------------------------

def retain_accent_bar_chart(
    scene: Scene,
    focus: Optional[Mobject],
    seconds: float,
    *,
    bar_color: str = "#00F0FF",
) -> Callable:
    if focus is None or seconds < 0.30:
        return lambda: None
    try:
        x_right  = focus.get_right()[0]
        y_bottom = focus.get_bottom()[1]
        y_top    = focus.get_top()[1]

        cap = Line([x_right + 0.06, y_bottom, 0], [x_right + 0.06, y_top, 0])
        cap.set_stroke(bar_color, width=4, opacity=0.0)
        cap.set_z_index(focus.get_z_index() + 1)
        scene.add(cap)

        t0     = float(scene.time)
        period = 2.5

        def _cap_upd(m, dt):
            t     = float(scene.time) - t0
            phase = np.sin(t * (2.0 * np.pi / period))
            op    = 0.38 * (0.5 + 0.5 * phase)
            m.set_stroke(opacity=float(np.clip(op, 0.0, 0.42)))

        cap.add_updater(_cap_upd)

        def _cleanup():
            cap.clear_updaters()
            scene.remove(cap)

        return _cleanup
    except Exception as e:
        _log.warning("retain_accent_bar_chart failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# 2. butterfly_chart — Central Spine Pulse
# A bright segment glides up and down the central spine (or focus Line).
# -----------------------------------------------------------------------

def retain_accent_butterfly(
    scene: Scene,
    focus: Optional[Mobject],
    seconds: float,
    *,
    spine_mobject: Optional[Mobject] = None,
    pulse_color: str = "#00F0FF",
) -> Callable:
    target = spine_mobject if spine_mobject is not None else focus
    if target is None or seconds < 0.30:
        return lambda: None
    try:
        x_c      = target.get_center()[0]
        y_bottom = target.get_bottom()[1]
        y_top    = target.get_top()[1]
        span     = max(0.20, y_top - y_bottom)
        pulse_h  = min(0.55, span * 0.22)

        pulse = Line([x_c, y_bottom, 0], [x_c, y_bottom + pulse_h, 0])
        pulse.set_stroke(pulse_color, width=3, opacity=0.0)
        pulse.set_z_index(target.get_z_index() + 2)
        scene.add(pulse)

        t0     = float(scene.time)
        period = 3.5

        def _pulse_upd(m, dt):
            t = float(scene.time) - t0
            # Smooth travel: 0 (bottom) → 1 (top) → 0 (bottom)
            a   = 0.5 - 0.5 * np.cos(t * (2.0 * np.pi / period))  # 0..1
            y_c = y_bottom + pulse_h / 2 + a * (span - pulse_h)
            m.put_start_and_end_on(
                [x_c, y_c - pulse_h / 2, 0],
                [x_c, y_c + pulse_h / 2, 0],
            )
            # Brightest mid-travel, dim near edges
            edge_dist = 1.0 - abs(a * 2.0 - 1.0)   # 0 at edges, 1 in middle
            op = 0.45 * (0.35 + 0.65 * edge_dist)
            m.set_stroke(opacity=float(np.clip(op, 0.0, 0.50)))

        pulse.add_updater(_pulse_upd)

        def _cleanup():
            pulse.clear_updaters()
            scene.remove(pulse)

        return _cleanup
    except Exception as e:
        _log.warning("retain_accent_butterfly failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# 3. geo_universal — Node Ping Rings
# Radiating concentric circles from the focus (active node/card).
# -----------------------------------------------------------------------

def retain_accent_geo(
    scene: Scene,
    focus: Optional[Mobject],
    seconds: float,
    *,
    ring_color: str = "#00F0FF",
    num_rings: int = 2,
) -> Callable:
    if focus is None or seconds < 0.40:
        return lambda: None
    try:
        center     = focus.get_center().copy()
        base_r     = max(0.14, focus.width / 2.0) if hasattr(focus, "width") else 0.14
        max_r      = base_r + 0.42
        ring_dur   = 1.80   # seconds for one ring to expand + fade
        stagger    = 1.20   # seconds between ring starts
        ring_cycle = ring_dur + stagger

        rings = []
        for i in range(num_rings):
            r = Circle(radius=base_r)
            r.set_stroke(ring_color, width=2, opacity=0.0)
            r.set_fill(opacity=0.0)
            r.move_to(center)
            r.set_z_index(focus.get_z_index() + 1)
            scene.add(r)
            rings.append(r)

        t0 = float(scene.time)

        def make_ring_upd(ring_obj, t_offset):
            def _upd(m, dt):
                t       = float(scene.time) - t0 - t_offset
                t_local = t % ring_cycle
                if t_local < 0 or t_local > ring_dur:
                    m.set_stroke(opacity=0.0)
                    return
                progress = t_local / ring_dur             # 0→1
                new_r    = base_r + (max_r - base_r) * progress
                new_d    = new_r * 2.0
                # set_width + set_height with stretch=True correctly resizes a Circle
                # without distorting it (both axes scaled independently to same value).
                m.set_width(new_d, stretch=True)
                m.set_height(new_d, stretch=True)
                m.move_to(center)
                op = 0.45 * (1.0 - progress)
                m.set_stroke(opacity=float(np.clip(op, 0.0, 0.50)))
            return _upd

        updaters = []
        for idx, ring_obj in enumerate(rings):
            upd = make_ring_upd(ring_obj, idx * stagger)
            ring_obj.add_updater(upd)
            updaters.append((ring_obj, upd))

        def _cleanup():
            for ring_obj, upd in updaters:
                ring_obj.clear_updaters()
                scene.remove(ring_obj)

        return _cleanup
    except Exception as e:
        _log.warning("retain_accent_geo failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# 4. sort_card — Scanner Idle Hover
# A separate indicator line micro-bobs just above the focus Mobject.
# Never mutates the template's own scanner object.
# -----------------------------------------------------------------------

def retain_accent_sort_card(
    scene: Scene,
    focus: Optional[Mobject],
    seconds: float,
    *,
    accent_color: str = "#2DD4FF",
) -> Callable:
    if focus is None or seconds < 0.30:
        return lambda: None
    try:
        x_left  = focus.get_left()[0]
        x_right = focus.get_right()[0]
        base_y  = focus.get_top()[1] + 0.10
        amp     = 0.04

        hover = Line([x_left, base_y, 0], [x_right, base_y, 0])
        hover.set_stroke(accent_color, width=3, opacity=0.0)
        hover.set_z_index(focus.get_z_index() + 3)
        scene.add(hover)

        t0     = float(scene.time)
        period = 2.0

        def _hover_upd(m, dt):
            t      = float(scene.time) - t0
            offset = amp * np.sin(t * (2.0 * np.pi / period))
            y      = base_y + offset
            m.put_start_and_end_on([x_left, y, 0], [x_right, y, 0])
            op = 0.30 + 0.22 * np.sin(t * (2.0 * np.pi / period))
            m.set_stroke(opacity=float(np.clip(op, 0.05, 0.55)))

        hover.add_updater(_hover_upd)

        def _cleanup():
            hover.clear_updaters()
            scene.remove(hover)

        return _cleanup
    except Exception as e:
        _log.warning("retain_accent_sort_card failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# 5. vs_card — Divider Energy Bridge
# A bright segment travels top-to-bottom along the central VS divider.
# Falls back to using the focus if no explicit divider is provided.
# -----------------------------------------------------------------------

def retain_accent_vs_card(
    scene: Scene,
    focus: Optional[Mobject],
    seconds: float,
    *,
    divider_mobject: Optional[Mobject] = None,
    pulse_color: str = "#FFFFFF",
) -> Callable:
    target = divider_mobject if divider_mobject is not None else focus
    if target is None or seconds < 0.30:
        return lambda: None
    try:
        x_c      = target.get_center()[0]
        y_top    = target.get_top()[1]
        y_bottom = target.get_bottom()[1]
        span     = max(0.20, y_top - y_bottom)
        pulse_h  = min(0.45, span * 0.20)

        pulse = Line([x_c, y_top, 0], [x_c, y_top - pulse_h, 0])
        pulse.set_stroke(pulse_color, width=3, opacity=0.0)
        pulse.set_z_index(target.get_z_index() + 3)
        scene.add(pulse)

        t0     = float(scene.time)
        period = 3.0

        def _pulse_upd(m, dt):
            t     = float(scene.time) - t0
            phase = (t % period) / period                          # 0..1 sawtooth
            # smooth downward sweep
            a    = 0.5 - 0.5 * np.cos(phase * 2.0 * np.pi)       # 0..1..0
            y_c  = y_top - pulse_h / 2 - a * (span - pulse_h)
            m.put_start_and_end_on(
                [x_c, y_c + pulse_h / 2, 0],
                [x_c, y_c - pulse_h / 2, 0],
            )
            op = 0.45 * np.sin(phase * np.pi)
            m.set_stroke(opacity=float(np.clip(op, 0.0, 0.50)))

        pulse.add_updater(_pulse_upd)

        def _cleanup():
            pulse.clear_updaters()
            scene.remove(pulse)

        return _cleanup
    except Exception as e:
        _log.warning("retain_accent_vs_card failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# 6. scan_race — Lane Indicator Sweep
# A bright horizontal segment sweeps left-to-right across the focus bar.
# -----------------------------------------------------------------------

def retain_accent_scan_race(
    scene: Scene,
    focus: Optional[Mobject],
    seconds: float,
    *,
    bar_color: str = "#00F0FF",
) -> Callable:
    if focus is None or seconds < 0.30:
        return lambda: None
    try:
        x_left  = focus.get_left()[0]
        x_right = focus.get_right()[0]
        y_c     = focus.get_center()[1]
        span    = max(0.10, x_right - x_left)

        sweep = Line([x_left, y_c, 0], [x_left + 0.001, y_c, 0])
        sweep.set_stroke(bar_color, width=8, opacity=0.0)
        sweep.set_z_index(focus.get_z_index() + 2)
        scene.add(sweep)

        t0     = float(scene.time)
        period = 2.5
        seg_w  = max(0.10, span * 0.22)    # fixed-width sweep segment

        def _sweep_upd(m, dt):
            t       = float(scene.time) - t0
            phase   = (t % period) / period                    # 0..1 sawtooth
            center_x = x_left + phase * (span + seg_w) - seg_w / 2
            start_x  = max(x_left,  center_x - seg_w / 2)
            end_x    = min(x_right, center_x + seg_w / 2)

            if start_x >= end_x - 0.001:
                m.set_stroke(opacity=0.0)
                return

            m.put_start_and_end_on([start_x, y_c, 0], [end_x, y_c, 0])
            # Fade at the extremes of travel
            edge = min(phase, 1.0 - phase) * 6.0
            op   = 0.55 * min(1.0, edge)
            m.set_stroke(opacity=float(np.clip(op, 0.0, 0.60)))

        sweep.add_updater(_sweep_upd)

        def _cleanup():
            sweep.clear_updaters()
            scene.remove(sweep)

        return _cleanup
    except Exception as e:
        _log.warning("retain_accent_scan_race failed: %s", e, exc_info=True)
        return lambda: None


# -----------------------------------------------------------------------
# 7. donut_breakdown — Radial Slice Lift
# The active slice gently pulses outward along its bisector direction.
# Direction is inferred from (focus.center - donut_center) — no angle
# parameter needed; works regardless of which slice is focused.
#
# Implementation note: we animate a GHOST COPY of the focus Mobject,
# not the focus itself. This upholds the module contract of never
# mutating template objects — other code reading focus.get_center()
# during the hold will always see the original unmodified position.
# -----------------------------------------------------------------------

def retain_accent_donut(
    scene: Scene,
    focus: Optional[Mobject],
    seconds: float,
    *,
    donut_center: Optional[np.ndarray] = None,
    lift_amp: float = 0.06,
) -> Callable:
    if focus is None or seconds < 0.30:
        return lambda: None
    try:
        dc = donut_center if donut_center is not None else np.array([0.0, 0.0, 0.0])

        # Compute bisector from current focus position
        direction = focus.get_center() - dc
        norm = float(np.linalg.norm(direction[:2]))
        if norm < 0.01:
            bisector = np.array([1.0, 0.0, 0.0])
        else:
            bisector = direction / norm

        original_center = focus.get_center().copy()
        t0     = float(scene.time)
        period = 3.0

        # Create a ghost copy so we never move the original focus Mobject
        ghost = focus.copy()
        ghost.set_z_index(focus.get_z_index())
        scene.add(ghost)

        def _lift_upd(m, dt):
            t      = float(scene.time) - t0
            phase  = np.sin(t * (2.0 * np.pi / period))
            offset = lift_amp * (0.5 + 0.5 * phase)     # 0 → lift_amp
            m.move_to(original_center + bisector * offset)

        ghost.add_updater(_lift_upd)

        def _cleanup():
            ghost.clear_updaters()
            scene.remove(ghost)

        return _cleanup
    except Exception as e:
        _log.warning("retain_accent_donut failed: %s", e, exc_info=True)
        return lambda: None
