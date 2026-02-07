from __future__ import annotations
from typing import Optional
from manim import *
from manim import rate_functions as rf

def hold_breathing(scene: Scene, seconds: float, focus: Optional[Mobject] = None):
    """
    leftover time me "alive wait":
    - pehle small pulse (Indicate) => 0.25-0.50s
    - baaki time normal wait (particles/scanners/updaters still moving)
    """
    seconds = float(max(0.0, seconds))
    if seconds <= 0.02:
        return

    pulse = 0.0
    if focus is not None and seconds >= 0.25:
        pulse = min(0.50, seconds)
        try:
            scene.play(Indicate(focus, scale_factor=1.02), run_time=pulse, rate_func=rf.ease_out_cubic)
        except Exception:
            pulse = 0.0

    rest = max(0.0, seconds - pulse)
    if rest > 0:
        scene.wait(rest)

def banner_scan_hold(scene: Scene, banner: Mobject, seconds: float, color=WHITE):
    """
    winner/outro me banner par scan line move karega (alive hold).
    """
    seconds = float(max(0.0, seconds))
    if seconds <= 0.02:
        return

    scan = Rectangle(width=banner.width * 0.18, height=banner.height * 0.92)
    scan.set_fill(color=color, opacity=0.12).set_stroke(width=0)
    scan.move_to(banner.get_left()).shift(RIGHT * (scan.width * 0.6))

    z = getattr(banner, "z_index", 0)
    scan.set_z_index(z + 5)

    def _upd(m, dt):
        speed = banner.width / 1.2
        m.shift(RIGHT * speed * dt)
        if m.get_right()[0] > banner.get_right()[0]:
            m.move_to(banner.get_left()).shift(RIGHT * (scan.width * 0.6))

    scan.add_updater(_upd)
    scene.add(scan)
    scene.wait(seconds)
    scan.remove_updater(_upd)
    scene.remove(scan)
