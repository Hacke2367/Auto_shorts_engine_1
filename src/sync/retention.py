

# src/sync/retention.py
from __future__ import annotations

import numpy as np
from manim import *
from manim import rate_functions as rf


# ------------------------------------------------------------
# SAFE FRAME (no dependency on src.utils)
# ------------------------------------------------------------
def _get_safe_frame(margin: float = 0.70) -> dict:
    half_w = float(config.frame_width) / 2
    half_h = float(config.frame_height) / 2
    return {
        "left": -half_w + margin,
        "right": half_w - margin,
        "top": half_h - margin,
        "bottom": -half_h + margin,
        "w": float(config.frame_width) - (2 * margin),
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
            return Text(content, font=font_name, weight=weight, font_size=font_size, color=color).set_z_index(z_index)
        except Exception:
            continue
    return Text(content, weight=weight, font_size=font_size, color=color).set_z_index(z_index)


# ------------------------------------------------------------
# RETENTION OVERLAY (lightweight, non-jarring)
# ------------------------------------------------------------
class RetentionOverlay(VGroup):
    """
    Lightweight attention-keeper overlay for boring pads/waits.
    - Edge-only subtle motion (center stays clean)
    - Thin gradient streaks (balanced L/R)
    - Anti-jarring: skips very short pads
    - Message pill near TOP (safe for subtitles at bottom)
    """

    def __init__(
        self,
        sf: dict,
        z_index: int = 900,
        seed: int = 7,
        n_streaks: int = 14,
        dim_opacity: float = 0.08,
        min_show_s: float = 0.45,
        msg_top_offset: float = 0.55,  # ✅ default: ABOVE most titles (no overlap)
    ):
        super().__init__()
        self.sf = sf
        self.z = int(z_index)
        self.dim_opacity = float(dim_opacity)
        self.min_show_s = float(min_show_s)
        self.msg_top_offset = float(msg_top_offset)

        self.active = False
        self._t = 0.0

        rng = np.random.RandomState(seed)

        # colors (safe)
        self.CYAN = "#00F0FF"
        self.PINK = "#FF0055"

        cx = float(sf.get("cx", 0.0))
        left = float(sf["left"])
        right = float(sf["right"])
        top = float(sf["top"])
        bottom = float(sf["bottom"])
        w = float(sf["w"])

        # ---- 1) super soft dim ----
        dim_w = max(float(config.frame_width) + 1.2, float(sf.get("w", config.frame_width)) + 1.6)
        dim_h = max(float(config.frame_height) + 1.2, float(sf.get("h", config.frame_height)) + 1.6)
        self.dim = Rectangle(width=dim_w, height=dim_h).set_stroke(width=0).set_z_index(self.z)
        self.dim.set_fill(BLACK, opacity=0.0)

        # ---- 2) edge-only streaks ----
        self.streaks = VGroup().set_z_index(self.z + 1)

        center_exclude = 0.18 * w
        left_band = (left, max(left, cx - center_exclude))
        right_band = (min(right, cx + center_exclude), right)

        if left_band[1] - left_band[0] < 0.5:
            left_band = (left, cx - 0.25)
        if right_band[1] - right_band[0] < 0.5:
            right_band = (cx + 0.25, right)

        n = int(max(6, round(float(n_streaks) * 0.72)))
        nL = n // 2
        nR = n - nL

        def _make_streak(x: float, y: float):
            length = float(rng.uniform(0.65, 1.85))
            width = float(rng.uniform(0.8, 1.7))
            op = float(rng.uniform(0.03, 0.08))

            ln = Line([x, y, 0], [x, y - length, 0]).set_z_index(self.z + 1)
            ln.set_stroke(color=[self.CYAN, self.PINK], width=width, opacity=op)

            glow = ln.copy().set_z_index(self.z)
            glow.set_stroke(color=[self.CYAN, self.PINK], width=width * 2.4, opacity=op * 0.16)

            grp = VGroup(glow, ln).set_z_index(self.z + 1)
            grp._spd = float(rng.uniform(0.65, 1.45))
            grp._wig = float(rng.uniform(0.00, 0.12))
            grp._phase = float(rng.uniform(0.0, 2 * np.pi))
            return grp

        for _ in range(nL):
            x = float(rng.uniform(left_band[0], left_band[1]))
            y = float(rng.uniform(bottom, top))
            self.streaks.add(_make_streak(x, y))

        for _ in range(nR):
            x = float(rng.uniform(right_band[0], right_band[1]))
            y = float(rng.uniform(bottom, top))
            self.streaks.add(_make_streak(x, y))

        def _streaks_upd(_, dt: float):
            if not self.active:
                return
            dt = float(max(0.0, dt))
            for g in self.streaks:
                g.shift(DOWN * g._spd * dt)
                if g._wig > 0:
                    dx = np.sin(self._t * 1.8 + g._phase) * g._wig * dt
                    g.shift(RIGHT * dx)

                if g.get_top()[1] < (bottom - 0.8):
                    gx = g.get_center()[0]
                    if gx < cx:
                        new_x = float(rng.uniform(left_band[0], left_band[1]))
                    else:
                        new_x = float(rng.uniform(right_band[0], right_band[1]))
                    new_y = top + float(rng.uniform(0.35, 1.25))
                    g.move_to([new_x, new_y, 0])

        self.streaks.add_updater(_streaks_upd)

        # ---- 2b) micro center particles (ambient, very subtle) ----
        self.micro_particles = VGroup().set_z_index(self.z + 1)
        center_half_w = max(0.45, 0.16 * w)
        p_left = max(left + 0.25, cx - center_half_w)
        p_right = min(right - 0.25, cx + center_half_w)
        p_bottom = bottom + 0.55
        p_top = top - 1.10
        for _ in range(18):
            p = Dot(radius=float(rng.uniform(0.010, 0.022)), color=WHITE).set_z_index(self.z + 1)
            p.move_to([float(rng.uniform(p_left, p_right)), float(rng.uniform(p_bottom, p_top)), 0])
            p.set_opacity(float(rng.uniform(0.03, 0.08)))
            p._spd = float(rng.uniform(0.012, 0.045))
            p._wig = float(rng.uniform(0.0, 0.016))
            p._phase = float(rng.uniform(0.0, 2 * np.pi))
            self.micro_particles.add(p)

        def _micro_upd(_, dt: float):
            if not self.active:
                return
            dt = float(max(0.0, dt))
            for p in self.micro_particles:
                y = p.get_center()[1] + p._spd * dt
                if y > p_top:
                    y = p_bottom + float(rng.uniform(0.0, 0.10))
                    x = float(rng.uniform(p_left, p_right))
                else:
                    x = p.get_center()[0] + np.sin(self._t * 1.2 + p._phase) * p._wig
                    x = float(np.clip(x, p_left, p_right))
                p.move_to([x, y, 0])

        self.micro_particles.add_updater(_micro_upd)

        # ---- 3) ultra subtle scanline ----
        self.scan = Rectangle(width=sf["w"] + 1.0, height=0.08).set_stroke(width=0).set_z_index(self.z + 2)
        self.scan.set_fill(WHITE, opacity=0.028)
        self.scan.move_to([cx, top - 0.65, 0])

        def _scan_upd(m: Mobject, dt: float):
            if not self.active:
                return
            m.shift(DOWN * 0.70 * float(max(0.0, dt)))
            if m.get_center()[1] < bottom - 0.6:
                m.move_to([cx, top + 0.6, 0])

        self.scan.add_updater(_scan_upd)

        # ---- 4) message pill (TOP) ----
        panel_w = min(7.0, sf["w"] * 0.78)
        panel_h = 0.72

        self.panel = RoundedRectangle(width=panel_w, height=panel_h, corner_radius=0.20).set_z_index(self.z + 3)
        self.panel.set_fill("#000000", opacity=0.38)
        self.panel.set_stroke(WHITE, width=1.6, opacity=0.12)

        y_msg = float(top - np.clip(self.msg_top_offset, 0.45, 1.35))
        self.panel.move_to([cx, y_msg, 0])

        self.msg = _text_with_fallback(
            "EXPLANATION IN PROGRESS",
            font_size=18,
            weight=BOLD,
            color=WHITE,
            z_index=self.z + 4,
        )
        try:
            self.msg.set_stroke(BLACK, width=1, opacity=0.32)
        except Exception:
            pass
        self.msg.move_to(self.panel.get_center())

        self.dots = _text_with_fallback("...", font_size=18, weight=BOLD, color=WHITE, z_index=self.z + 4)
        try:
            self.dots.set_stroke(BLACK, width=1, opacity=0.32)
        except Exception:
            pass
        self.dots.next_to(self.msg, RIGHT, buff=0.06)

        def _dots_upd(m: Mobject, dt: float):
            if not self.active:
                return
            if not hasattr(m, "_tt"):
                m._tt = 0.0
            m._tt += float(max(0.0, dt))
            phase = int(m._tt / 0.28) % 4
            txt = "." * phase
            new = _text_with_fallback(txt, font_size=18, weight=BOLD, color=WHITE, z_index=self.z + 4)
            try:
                new.set_stroke(BLACK, width=1, opacity=0.32)
            except Exception:
                pass
            new.move_to(m.get_center())
            m.become(new)

        self.dots.add_updater(_dots_upd)

        # ---- time ----
        def _time_upd(_, dt: float):
            if not self.active:
                return
            self._t += float(max(0.0, dt))

        self.add_updater(_time_upd)

        self.add(self.dim, self.streaks, self.micro_particles, self.scan, self.panel, self.msg, self.dots)
        self.set_opacity(0.0)

    def set_message(self, text: str) -> None:
        text = (text or "").strip() or "EXPLANATION IN PROGRESS"
        new = _text_with_fallback(text, font_size=18, weight=BOLD, color=WHITE, z_index=self.z + 4)
        try:
            new.set_stroke(BLACK, width=1, opacity=0.32)
        except Exception:
            pass
        new.move_to(self.panel.get_center())
        self.msg.become(new)
        self.dots.next_to(self.msg, RIGHT, buff=0.06)

    def play_for(self, scene: Scene, duration: float, text: str | None = None) -> None:
        d = float(max(0.0, duration))
        if d <= 0.001:
            return

        # anti-jarring
        if d < self.min_show_s:
            scene.wait(d)
            return

        if text:
            self.set_message(text)

        pre = min(0.26, d * 0.26)
        post = min(0.24, d * 0.24)
        hold = max(0.0, d - pre - post)

        self.active = True
        self._t = 0.0

        # two-stage easing avoids sudden overlay pop
        pre1 = max(0.08, pre * 0.55)
        pre2 = max(0.06, pre - pre1)
        scene.play(
            self.animate.set_opacity(0.72),
            self.dim.animate.set_fill(BLACK, opacity=self.dim_opacity * 0.72),
            run_time=pre1,
            rate_func=rf.ease_out_sine,
        )
        scene.play(
            self.animate.set_opacity(1.0),
            self.dim.animate.set_fill(BLACK, opacity=self.dim_opacity),
            run_time=pre2,
            rate_func=rf.ease_out_cubic,
        )

        scene.wait(hold)

        post1 = max(0.06, post * 0.48)
        post2 = max(0.06, post - post1)
        scene.play(
            self.animate.set_opacity(0.35),
            self.dim.animate.set_fill(BLACK, opacity=self.dim_opacity * 0.25),
            run_time=post1,
            rate_func=rf.ease_in_out_sine,
        )
        scene.play(
            self.animate.set_opacity(0.0),
            self.dim.animate.set_fill(BLACK, opacity=0.0),
            run_time=post2,
            rate_func=rf.ease_in_cubic,
        )
        self.active = False


# ------------------------------------------------------------
# INTERNAL: get/cached overlay on scene
# ------------------------------------------------------------
def _get_or_create_overlay(scene: Scene, sf: dict | None = None, z_index: int = 900) -> RetentionOverlay | None:
    if hasattr(scene, "_retention_overlay") and scene._retention_overlay is not None:
        return scene._retention_overlay

    # prefer scene-provided safe frame if present
    if sf is None:
        sf = getattr(scene, "_sf", None) or getattr(scene, "_SAFE_FRAME", None)

    if sf is None:
        # fallback compute
        sf = _get_safe_frame(margin=0.70)

    # optional scene override for top offset
    msg_top_offset = getattr(scene, "_retention_msg_top_offset", None)
    try:
        if msg_top_offset is not None:
            ov = RetentionOverlay(sf, z_index=z_index, msg_top_offset=float(msg_top_offset))
        else:
            ov = RetentionOverlay(sf, z_index=z_index)
    except Exception:
        return None

    scene.add(ov)
    scene._retention_overlay = ov
    return ov


# ------------------------------------------------------------
# PUBLIC: hold_breathing (used by bar_chart)
# ------------------------------------------------------------
def hold_breathing(scene: Scene, seconds: float, focus: Mobject | None = None, text: str = "EXPLANATION IN PROGRESS"):
    s = float(max(0.0, seconds))
    if s <= 0.001:
        return

    ov = _get_or_create_overlay(scene, z_index=900)

    # tiny focus glow (safe, optional)
    glow = None
    if focus is not None:
        try:
            glow = SurroundingRectangle(focus, corner_radius=0.16, buff=0.10).set_z_index(9999)
            glow.set_fill(opacity=0)
            glow.set_stroke(color=WHITE, width=3.0, opacity=0.0)

            def _g_upd(m, dt):
                t = float(scene.time)
                op = 0.10 + 0.10 * (np.sin(t * 2.0) * 0.5 + 0.5)
                m.set_stroke(opacity=float(np.clip(op, 0.05, 0.22)))

            glow.add_updater(_g_upd)
            scene.add(glow)
        except Exception:
            glow = None

    if ov is not None:
        ov.play_for(scene, s, text=text)
    else:
        scene.wait(s)

    if glow is not None:
        glow.clear_updaters()
        scene.remove(glow)


# ------------------------------------------------------------
# PUBLIC: banner_scan_hold (used by bar_chart)
# (keeps banner alive; DOES NOT show retention message)
# ------------------------------------------------------------
def banner_scan_hold(scene: Scene, banner: Mobject, seconds: float, color=WHITE):
    s = float(max(0.0, seconds))
    if s <= 0.001:
        return

    # subtle repeating scanline on banner
    try:
        scan = Rectangle(width=banner.width * 0.98, height=0.10).set_stroke(width=0)
        scan.set_fill(color, opacity=0.10)
        scan.set_z_index(getattr(banner, "z_index", 200) + 5)

        t0 = float(scene.time)

        def _upd(m, dt):
            # 0..1..0 pingpong along banner height
            t = float(scene.time) - t0
            a = 0.5 + 0.5 * np.sin(t * 2.2)
            y = banner.get_top()[1] - a * (banner.height - 0.20)
            m.move_to([banner.get_center()[0], y, 0])

        scan.add_updater(_upd)
        scene.add(scan)
        scene.wait(s)
        scan.clear_updaters()
        scene.remove(scan)
    except Exception:
        scene.wait(s)


__all__ = ["RetentionOverlay", "hold_breathing", "banner_scan_hold"]





