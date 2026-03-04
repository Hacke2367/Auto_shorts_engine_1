

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
    HUD Telemetry Ghost Overlay (10/10 Standard)
    - Adaptive Brackets: 4 L-shaped corners pulsing and breathing
    - Hex-Data Stream: Vertical scrolling randomized hex (0xDEADBEEF)
    - Bit-Oscillators: Horizontal sine wave freq visualizer
    """

    def __init__(
        self,
        sf: dict,
        z_index: int = 900,
        seed: int = 42,
        dim_opacity: float = 0.25,
        min_show_s: float = 0.50,  # Strict complexity logic
    ):
        super().__init__()
        self.sf = sf
        self.z = int(z_index)
        self.dim_opacity = float(dim_opacity)
        self.min_show_s = float(min_show_s)

        self.active = False
        self._t = 0.0

        rng = np.random.RandomState(seed)

        cx, cy = float(sf.get("cx", 0.0)), float(sf.get("cy", 0.0))
        left = float(sf["left"])
        right = float(sf["right"])
        top = float(sf["top"])
        bottom = float(sf["bottom"])
        w = float(sf["w"])
        h = float(sf["h"])

        # ---- 1) Dim Background ----
        self.dim = Rectangle(width=config.frame_width + 1.0, height=config.frame_height + 1.0)
        self.dim.set_stroke(width=0).set_z_index(self.z).set_fill(BLACK, opacity=0.0)

        # ---- 2) Adaptive Brackets (Corners) ----
        self.brackets = VGroup().set_z_index(self.z + 2)
        bw, bh = 0.8, 0.8  # bracket arm lengths
        thick = 4.0
        col = "#00F0FF"

        def make_L(x, y, dx, dy):
            lines = VGroup(
                Line([x, y, 0], [x + dx, y, 0]),
                Line([x, y, 0], [x, y + dy, 0])
            )
            # Add neon glow
            glow = lines.copy().set_stroke(col, width=thick * 2.5, opacity=0.15)
            core = lines.copy().set_stroke(WHITE, width=thick, opacity=0.8)
            res = VGroup(glow, core)
            res.base_pos = np.array([x, y, 0])
            res.dir = np.array([np.sign(dx), np.sign(dy), 0])
            return res

        # TL, TR, BL, BR
        pad = 0.25
        b_tl = make_L(left + pad, top - pad, bw, -bh)
        b_tr = make_L(right - pad, top - pad, -bw, -bh)
        b_bl = make_L(left + pad, bottom + pad, bw, bh)
        b_br = make_L(right - pad, bottom + pad, -bw, bh)
        
        self.brackets.add(b_tl, b_tr, b_bl, b_br)

        def _brackets_upd(_, dt):
            if not self.active: return
            # Breathe opacity (0.1 to 0.4) and scale (1.0 to 1.05) using sine
            pulse = (np.sin(self._t * 3.0) + 1.0) / 2.0  # 0.0 to 1.0
            
            new_op = 0.1 + (0.3 * pulse)
            scale_fac = 1.0 + (0.05 * pulse)

            for b in self.brackets:
                b.set_opacity(new_op)
                # scale outward from frame center
                offset = (b.dir * 0.15 * pulse)
                b.move_to(b.base_pos + offset)
                
        self.brackets.add_updater(_brackets_upd)

        # ---- 3) Hex-Data Stream (Sides) ----
        self.streams = VGroup().set_z_index(self.z + 1)
        
        def g_hex():
            return f"0x{rng.randint(0, 0xFFFFFFFF):08X}"

        # Left and Right text columns
        txt_L = _text_with_fallback("\n".join([g_hex() for _ in range(15)]), font_size=12, color="#8899AA")
        txt_R = _text_with_fallback("\n".join([g_hex() for _ in range(15)]), font_size=12, color="#8899AA")
        
        for t in (txt_L, txt_R):
            t.set_opacity(0.50)
        
        txt_L.move_to([left + 0.6, cy, 0])
        txt_R.move_to([right - 0.6, cy, 0])
        self.streams.add(txt_L, txt_R)

        def _streams_upd(_, dt):
            if not self.active: return
            # Vertical scrolling + randomized refresh
            for t in self.streams:
                t.shift(DOWN * 0.4 * dt)
                if t.get_top()[1] < top - 2.0:
                    t.become(_text_with_fallback("\n".join([g_hex() for _ in range(15)]), font_size=12, color="#8899AA"))
                    t.set_opacity(0.15)
                    # Snap back to top
                    t.move_to([t.get_center()[0], cy + 0.5, 0])
        
        self.streams.add_updater(_streams_upd)

        # ---- 4) Bit-Oscillators (Bottom) ----
        self.oscillators = VGroup().set_z_index(self.z + 2)
        base_y = bottom + 0.6
        width = w * 0.4
        
        line1 = Line([cx - width/2, base_y, 0], [cx + width/2, base_y, 0]).set_stroke("#FF0055", width=2, opacity=0.3)
        line2 = Line([cx - width/2, base_y - 0.12, 0], [cx + width/2, base_y - 0.12, 0]).set_stroke("#00F0FF", width=2, opacity=0.3)
        self.oscillators.add(line1, line2)

        def _osc_upd(_, dt):
            if not self.active: return
            # Fake sine visualization on the lines
            # Note: updating line points directly is expensive, so we'll just scale Y-axis rapidly to fake it
            y_scale1 = 1.0 + 15.0 * np.abs(np.sin(self._t * 8.0))
            y_scale2 = 1.0 + 10.0 * np.abs(np.cos(self._t * 6.5))
            
            line1.stretch_to_fit_height(y_scale1 * 0.05 + 0.01)
            line1.move_to([cx, base_y, 0])
            
            line2.stretch_to_fit_height(y_scale2 * 0.05 + 0.01)
            line2.move_to([cx, base_y - 0.12, 0])

        self.oscillators.add_updater(_osc_upd)

        # ---- Timer ----
        def _time_upd(_, dt):
            if not self.active: return
            self._t += max(0.0, dt)
        self.add_updater(_time_upd)

        self.add(self.dim, self.brackets, self.streams, self.oscillators)
        self.set_opacity(0.0)

    def set_message(self, text: str) -> None:
        pass # message pills removed from this layout

    def play_for(self, scene: Scene, duration: float, text: str | None = None) -> None:
        d = float(max(0.0, duration))
        if d <= 0.001: return

        # Exact complexity skip logic
        if d < self.min_show_s:
            scene.wait(d)
            return

        pre = min(0.2, d * 0.2)
        post = min(0.2, d * 0.2)
        hold = max(0.0, d - pre - post)

        self.active = True
        self._t = 0.0

        # Boot sequence
        scene.play(
            self.animate.set_opacity(1.0),
            self.dim.animate.set_fill(BLACK, opacity=self.dim_opacity),
            run_time=pre,
            rate_func=rf.ease_out_cubic,
        )

        scene.wait(hold)

        # Shutdown sequence
        scene.play(
            self.animate.set_opacity(0.0),
            self.dim.animate.set_fill(BLACK, opacity=0.0),
            run_time=post,
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

    try:
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





