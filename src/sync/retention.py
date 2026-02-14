# src/sync/retention.py
from __future__ import annotations
from manim import *
import numpy as np


def _safe_z(obj, z=200):
    try:
        obj.set_z_index(z)
    except Exception:
        pass


def hold_breathing(scene: Scene, duration: float, focus: Mobject | None = None):
    """
    'boring time' ko alive banata hai.
    - duration seconds tak video extend karta hai (scene.wait).
    - focus object par subtle scan sheen chalti rehti hai.
    """
    try:
        duration = float(duration)
    except Exception:
        duration = 0.0

    if duration <= 0.02:
        return

    # Agar focus nahi diya, simple wait (still extends video)
    if focus is None:
        scene.wait(duration)
        return

    # Subtle moving sheen (alive feel)
    w = max(0.15, float(getattr(focus, "width", 1.0)))
    h = max(0.15, float(getattr(focus, "height", 1.0)))

    sheen = Rectangle(width=0.10, height=h * 1.25).set_stroke(width=0).set_fill(WHITE, opacity=0.10)
    sheen.rotate(15 * DEGREES)
    _safe_z(sheen, 400)

    # Move across focus bounds
    start = focus.get_left() + LEFT * 0.15
    end = focus.get_right() + RIGHT * 0.15
    sheen.move_to(start)

    def _upd(m, dt):
        # 0..1 loop
        t = (np.sin(scene.time * 2.0) + 1.0) / 2.0
        m.move_to(start + (end - start) * t)

    sheen.add_updater(_upd)
    scene.add(sheen)

    # ✅ THIS IS THE KEY: time advance => video becomes longer
    scene.wait(duration)

    sheen.remove_updater(_upd)
    scene.remove(sheen)


def banner_scan_hold(scene: Scene, banner: Mobject, duration: float, color=WHITE):
    """
    Winner/outro me banner ke upar scan line chalti rehti hai + scene.wait(duration)
    """
    try:
        duration = float(duration)
    except Exception:
        duration = 0.0

    if duration <= 0.02:
        return

    w = max(0.3, float(getattr(banner, "width", 4.0)))
    h = max(0.2, float(getattr(banner, "height", 1.0)))

    line = Rectangle(width=0.08, height=h * 1.10).set_stroke(width=0).set_fill(color, opacity=0.12)
    line.rotate(12 * DEGREES)
    _safe_z(line, 500)

    start = banner.get_left() + LEFT * 0.12
    end = banner.get_right() + RIGHT * 0.12
    line.move_to(start)

    def _upd(m, dt):
        t = (scene.time * 0.75) % 1.0
        m.move_to(start + (end - start) * t)

    line.add_updater(_upd)
    scene.add(line)

    # ✅ extend video
    scene.wait(duration)

    line.remove_updater(_upd)
    scene.remove(line)
