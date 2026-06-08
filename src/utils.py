# utils.py
# Legacy implementation removed — see git history for the commented-out block.

from manim import *
import numpy as np
import random
import os

# ============================================================
# CONFIG + THEME IMPORT (project) with safe fallback
# ============================================================
try:
    from src.config import *  # expects: Theme, BACKGROUND_COLOR, etc.
except Exception:
    BACKGROUND_COLOR = "#050505"
    FONT_DISPLAY = "Montserrat"

    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_GREEN = "#00FF66"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#AEB7C2"
        AXIS_COLOR = "#00F0FF"

    config.frame_height = 16.0
    config.frame_width = 9.0


# ============================================================
# ✅ SYSTEM RULE: SAFE-FRAME FIRST (no overflow ever)
# ============================================================
def get_safe_frame(margin=0.60):
    half_w = config.frame_width / 2
    half_h = config.frame_height / 2
    return {
        "left": -half_w + margin,
        "right": half_w - margin,
        "top": half_h - margin,
        "bottom": -half_h + margin,
        "w": config.frame_width - (2 * margin),
        "h": config.frame_height - (2 * margin),
        "cx": 0.0,
        "cy": 0.0,
    }


def clamp_x(x, mob_width=0.0, margin=0.60):
    sf = get_safe_frame(margin)
    half = float(mob_width) / 2
    return float(np.clip(x, sf["left"] + half, sf["right"] - half))


def clamp_y(y, mob_height=0.0, margin=0.60):
    sf = get_safe_frame(margin)
    half = float(mob_height) / 2
    return float(np.clip(y, sf["bottom"] + half, sf["top"] - half))


# ============================================================
# BRAND COLORS (single source of truth for utils layer)
# ============================================================
class Brand:
    CYAN = getattr(Theme, "NEON_BLUE", "#00F0FF")
    PINK = getattr(Theme, "NEON_PINK", "#FF0055")
    PURPLE = getattr(Theme, "NEON_PURPLE", "#BD00FF")
    GREEN = getattr(Theme, "NEON_GREEN", "#00FF66")
    WHITE = "#FFFFFF"
    BLACK = "#000000"
    TEXT_MAIN = getattr(Theme, "TEXT_MAIN", "#FFFFFF")
    TEXT_SUB = getattr(Theme, "TEXT_SUB", "#AEB7C2")


# ============================================================
# ✅ BRANDING BORDER (4 lines for premium animation)
# ============================================================
def get_branding_border_lines(inset=0.25, stroke_w=6, opacity=1.0):
    h = config.frame_height - inset
    w = config.frame_width - inset

    tl = np.array([-w / 2, h / 2, 0])
    tr = np.array([w / 2, h / 2, 0])
    br = np.array([w / 2, -h / 2, 0])
    bl = np.array([-w / 2, -h / 2, 0])

    top_line = Line(tl, tr)
    right_line = Line(tr, br)
    bottom_line = Line(br, bl)
    left_line = Line(bl, tl)

    top_line.set_stroke(width=stroke_w, color=Brand.PINK, opacity=opacity)
    right_line.set_stroke(width=stroke_w, color=Brand.CYAN, opacity=opacity)
    bottom_line.set_stroke(width=stroke_w, color=Brand.PINK, opacity=opacity)
    left_line.set_stroke(width=stroke_w, color=Brand.CYAN, opacity=opacity)

    for ln in (top_line, right_line, bottom_line, left_line):
        ln.set_z_index(300)

    return top_line, right_line, bottom_line, left_line


def get_branding_border():
    t, r, b, l = get_branding_border_lines()
    return VGroup(t, r, b, l)


# ============================================================
# ✅ CINEMATIC OVERLAY (REC + TIMER + FEED + FOOTER)
# ============================================================
def _format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def get_cinematic_overlay(scene,
                          feed_text="FEED_BAR // MARKET",
                          footer_text="CONFIDENTIAL // LEAKED_SOURCE",
                          margin=0.60):
    sf = get_safe_frame(margin)

    overlay = VGroup()
    overlay.set_z_index(250)

    # Vignette — soft layered falloff (stacked dark strokes ≈ radial gradient)
    vignette = VGroup()
    for _w_px, _op in ((180, 0.22), (110, 0.16), (60, 0.10)):
        _v = Rectangle(width=config.frame_width + 2, height=config.frame_height + 2)
        _v.set_fill(color=BLACK, opacity=0)
        _v.set_stroke(color=BLACK, width=_w_px, opacity=_op)
        vignette.add(_v)
    vignette.set_z_index(240)

    # Scanlines
    scanlines = VGroup()
    lines_n = 46
    for i in range(lines_n):
        y = sf["bottom"] + (i * (sf["h"] / lines_n))
        ln = Line(LEFT * (config.frame_width), RIGHT * (config.frame_width))
        ln.set_y(y)
        ln.set_stroke(color=Brand.CYAN, width=1, opacity=0.05)
        scanlines.add(ln)
    scanlines.set_z_index(241)

    overlay.add(vignette, scanlines)

    # REC top-left
    rec_dot = Dot(color=Brand.PINK, radius=0.06)
    rec_dot.move_to([sf["left"] + 0.35, sf["top"] - 0.28, 0])

    rec_label = Text("REC", font="Montserrat", weight=BOLD, font_size=18, color=Brand.TEXT_MAIN)
    rec_label.next_to(rec_dot, RIGHT, buff=0.12).align_to(rec_dot, DOWN)

    def _blink(m, dt):
        if not hasattr(m, "_t"):
            m._t = 0.0
        m._t += dt
        m.set_opacity(0.35 + 0.65 * (0.5 + 0.5 * np.sin(6.0 * m._t)))

    rec_dot.add_updater(_blink)

    # TIMER top-right
    timer = Text("00:00", font="Montserrat", weight=BOLD, font_size=16, color=Brand.TEXT_MAIN)
    timer.move_to([sf["right"] - 0.55, sf["top"] - 0.28, 0])
    timer.set_opacity(0.9)

    timer._last_str = "00:00"

    def _update_timer(m):
        # Throttle: only rebuild the Text mobject when the displayed MM:SS changes
        # (previously rebuilt a full Text every frame for the entire video).
        new_str = _format_time(getattr(scene, "time", 0.0))
        if new_str == getattr(m, "_last_str", None):
            return
        m._last_str = new_str
        m.become(
            Text(new_str,
                 font="Montserrat", weight=BOLD, font_size=16, color=Brand.TEXT_MAIN)
            .move_to([sf["right"] - 0.55, sf["top"] - 0.28, 0])
            .set_opacity(0.9)
        )

    timer.add_updater(_update_timer)

    # FEED label top-right
    feed = Text(feed_text, font="Montserrat", font_size=12, color=Brand.TEXT_SUB)
    feed.move_to([sf["right"] - 1.45, sf["top"] - 0.10, 0])
    feed.set_opacity(0.75)

    # Footer bottom-left
    footer = Text(footer_text, font="Montserrat", font_size=12, color=Brand.CYAN)
    footer.move_to([sf["left"] + 1.75, sf["bottom"] + 0.22, 0])
    footer.set_opacity(0.7)

    overlay.add(rec_dot, rec_label, timer, feed, footer)
    return overlay


# ============================================================
# ✅ WATERMARK (bottom-right rotating target)
# ============================================================
def get_rotating_watermark(margin=0.60):
    sf = get_safe_frame(margin)

    ring = DashedVMobject(
        Circle(radius=0.7, color=Brand.CYAN, stroke_width=2),
        num_dashes=12
    )
    cross = VGroup(
        Line(UP * 0.32, DOWN * 0.32),
        Line(LEFT * 0.32, RIGHT * 0.32),
    ).set_stroke(color=Brand.TEXT_MAIN, width=1.2, opacity=0.6)

    wm = VGroup(ring, cross)
    wm.move_to([sf["right"] - 0.75, sf["bottom"] + 0.65, 0])
    wm.set_opacity(0.55)
    wm.set_z_index(255)

    wm.add_updater(lambda m, dt: m.rotate(-0.45 * dt))
    return wm


# ============================================================
# ✅ PARTICLES (reusable)
# ============================================================
def make_floating_particles(n=30,
                            color=None,
                            radius_range=(0.02, 0.05),
                            opacity_range=(0.10, 0.25),
                            drift=0.04,
                            margin=0.60,
                            accent=None,
                            twinkle=True,
                            parallax=True):
    """
    Floating ambient particles (backward-compatible signature).

    Upgrades, all inside ONE O(n) VGroup updater (same render-cost class):
      - twinkle: gentle per-particle opacity pulse (precomputed phase)
      - parallax: two depth bands (near = bigger/brighter/faster)
      - colour variety: brand cyan + optional template accent + a few whites
      - soft edge wrap: recycle particles to the bottom once they exit the top
    """
    sf = get_safe_frame(margin)
    base_color = color or Brand.CYAN

    palette = [base_color]
    if accent and accent != base_color:
        palette.append(accent)
    palette.append(Brand.WHITE)

    top = sf["top"]
    bottom = sf["bottom"]

    lo_r, hi_r = radius_range
    mid_r = (lo_r + hi_r) / 2.0
    lo_o, hi_o = opacity_range
    mid_o = (lo_o + hi_o) / 2.0

    particles = VGroup()
    meta = []  # (base_opacity, phase, speed_factor)
    for _ in range(n):
        near = (random.random() < 0.5) if parallax else True
        if near:
            r = random.uniform(mid_r, hi_r)
            op = random.uniform(mid_o, hi_o)
            sp = random.uniform(1.0, 1.6)
        else:
            r = random.uniform(lo_r, mid_r)
            op = random.uniform(lo_o, mid_o)
            sp = random.uniform(0.5, 0.9)

        p = Dot(radius=r, color=random.choice(palette))
        p.move_to([random.uniform(sf["left"], sf["right"]),
                   random.uniform(bottom, top), 0])
        p.set_opacity(op)
        particles.add(p)
        meta.append((op, random.uniform(0.0, 2.0 * np.pi), sp))

    clock = {"t": 0.0}

    def _upd(m, dt):
        clock["t"] += dt
        t = clock["t"]
        for p, (base_op, phase, sp) in zip(m.submobjects, meta):
            p.shift(UP * drift * sp * dt)
            if p.get_y() > top + 0.10:
                p.move_to([random.uniform(sf["left"], sf["right"]), bottom - 0.10, 0])
            if twinkle:
                tw = 0.75 + 0.25 * np.sin(t * 1.4 * sp + phase)
                p.set_opacity(float(np.clip(base_op * tw, 0.0, 1.0)))

    particles.add_updater(_upd)
    particles.set_z_index(5)
    return particles


# ============================================================
# ✅ CINEMATIC BACKGROUND (premium atmosphere — replaces dead-flat fill)
#   - additive + sync-safe: only scene.add() + at most ONE cheap updater
#   - base vertical gradient plate + layered accent "glow pool"
#   - optional slow breathing drift ("dynamic background shift")
# ============================================================
def add_cinematic_background(scene, accent=None, breathing=True):
    """
    Adds a premium atmospheric backdrop behind everything (z far below content).

    Sync-safe by construction: no scene.play / no run_time — just scene.add()
    plus (optionally) ONE lightweight sine updater on the glow group, the same
    cost class as the existing subtle-flicker effect.

    Returns the background VGroup (callers may remove it; not required).
    """
    accent = accent or Brand.CYAN

    try:
        grp = VGroup()

        # --- base gradient plate (full frame, slightly oversized) ---
        base = Rectangle(width=config.frame_width + 2, height=config.frame_height + 2)
        base.set_stroke(width=0)
        try:
            base.set_color_by_gradient("#0E1116", "#090C10", "#050608")
            base.set_fill(opacity=1.0)
        except Exception:
            base.set_fill(color="#0A0D11", opacity=1.0)
        base.set_stroke(width=0)
        base.set_z_index(-100)
        grp.add(base)

        # --- radial brand "glow pool" (layered ellipses ≈ soft gaussian) ---
        glow = VGroup()
        glow_cy = config.frame_height * 0.12
        glow_specs = ((1.70, 0.95, 0.034), (1.20, 0.65, 0.024), (0.75, 0.42, 0.015))
        glow_base = []
        for (sw, sh, op) in glow_specs:
            e = Ellipse(width=config.frame_width * sw, height=config.frame_height * sh)
            e.set_fill(color=accent, opacity=op)
            e.set_stroke(width=0)
            e.move_to([0.0, glow_cy, 0.0])
            glow.add(e)
            glow_base.append(op)
        glow.set_z_index(-90)
        grp.add(glow)

        scene.add(grp)

        # --- optional breathing drift: ONE cheap sine updater ---
        if breathing:
            def _bg_breathe(m, dt):
                t = float(getattr(scene, "time", 0.0))
                f = 0.75 + 0.45 * (0.5 + 0.5 * np.sin(t * 0.40))   # ~0.75 .. 1.20
                dy = 0.18 * np.sin(t * 0.27)
                for ell, b_op in zip(m.submobjects, glow_base):
                    ell.set_fill(opacity=float(np.clip(b_op * f, 0.0, 0.14)))
                m.move_to([0.0, glow_cy + dy, 0.0])

            glow.add_updater(_bg_breathe)

        return grp

    except Exception:
        # Never let atmosphere break a render — degrade to the flat camera fill.
        return None


# ============================================================
# ✅ INTRO MANAGER (premium + SINGLE SOURCE OF TRUTH)
#   - prevents double intro calls per Scene
#   - prevents duplicate overlay/border/watermark per Scene
#   - FIXED: no overlap between sub & title (they are shown separately)
#   - ADDED: glitch fadeout for sub
#   - ✅ ADDED: SAFE SFX marks (intro_glitch, intro_rise, intro_hit)
# ============================================================
class IntroManager:
    @staticmethod
    def _ensure_branding(scene,
                         feed_text="FEED_BAR // MARKET",
                         footer_text="CONFIDENTIAL // LEAKED_SOURCE"):
        if getattr(scene, "_branding_attached", False):
            return getattr(scene, "_branding_objs", {})

        top, right, bottom, left = get_branding_border_lines(stroke_w=6, opacity=1.0)
        overlay = get_cinematic_overlay(scene, feed_text=feed_text, footer_text=footer_text)
        watermark = get_rotating_watermark()

        scene.add(top, right, bottom, left, overlay, watermark)

        scene._branding_attached = True
        scene._branding_objs = {
            "top": top, "right": right, "bottom": bottom, "left": left,
            "overlay": overlay, "watermark": watermark
        }
        return scene._branding_objs

    @staticmethod
    def _glitch_fade_out(scene, mob: Mobject, total_time=0.20, amp=0.08, steps=7):
        """
        Tiny jitter + opacity flicker then fade out.
        Keeps intro duration almost same.
        """
        rng = np.random.RandomState(7)
        per = total_time / max(1, steps + 1)

        for i in range(steps):
            dx, dy = rng.uniform(-amp, amp, size=2)
            target_op = 0.85 if (i % 2 == 0) else 0.25
            scene.play(
                mob.animate.shift([dx, dy, 0]).set_opacity(target_op),
                run_time=per,
                rate_func=linear,
            )

        scene.play(FadeOut(mob), run_time=per, rate_func=linear)

    # ✅ SAFE SFX MARK WRAPPER (3.9-safe)
    @staticmethod
    def _sfx(scene, key, gain_db=0.0, offset=0.0, meta=None):
        fn = getattr(scene, "sfx_mark", None)
        if callable(fn):
            try:
                fn(key, gain_db=gain_db, offset=offset, meta=meta)
            except Exception:
                pass

    @staticmethod
    def play_intro(scene,
                   brand_title="BIGDATA LEAK",
                   brand_sub="SYSTEM BREACH DETECTED",
                   feed_text="FEED_BAR // MARKET",
                   footer_text="CONFIDENTIAL // LEAKED_SOURCE"):

        # Intro plays only once per Scene
        if getattr(scene, "_intro_played", False):
            IntroManager._ensure_branding(scene, feed_text=feed_text, footer_text=footer_text)
            return
        scene._intro_played = True

        # full-screen cover
        cover = Rectangle(width=50, height=50, color=BLACK, fill_opacity=1).set_stroke(width=0)
        cover.set_z_index(500)
        scene.add(cover)

        # SUB (alone)
        sub = Text(f"> {brand_sub}", font="Consolas", font_size=22, color=Brand.PINK)
        sub.set_z_index(501)
        sub.move_to(ORIGIN)

        # TITLE (alone)
        title = Text(brand_title, font=FONT_DISPLAY, weight=BOLD, font_size=54)
        title.set_color_by_gradient(Brand.CYAN, Brand.TEXT_MAIN)
        title.set_z_index(501)
        title.move_to(ORIGIN)

        # 1) show sub only
        IntroManager._sfx(scene, "intro_glitch", gain_db=-8, meta={"at": "intro_sub_in"})
        scene.play(FadeIn(sub, shift=UP * 0.05), run_time=0.30)
        scene.wait(0.05)

        # 2) glitch fade out sub
        IntroManager._glitch_fade_out(scene, sub, total_time=0.20, amp=0.09, steps=7)
        scene.remove(sub)

        # 3) show title only
        IntroManager._sfx(scene, "intro_rise", gain_db=-10, meta={"at": "intro_title_in"})
        scene.play(FadeIn(title, shift=UP * 0.10), run_time=0.35)

        IntroManager._sfx(scene, "intro_hit", gain_db=-12, meta={"at": "intro_flash"})
        scene.play(Flash(title, color=Brand.CYAN, line_length=0.6), run_time=0.20)

        # attach persistent branding exactly once
        branding = IntroManager._ensure_branding(scene, feed_text=feed_text, footer_text=footer_text)

        top = branding["top"]
        right = branding["right"]
        bottom = branding["bottom"]
        left = branding["left"]

        # Reveal scene (keep timing stable)
        scene.play(
            FadeOut(cover),
            FadeOut(title),
            Create(top), Create(right), Create(bottom), Create(left),
            run_time=0.85,
            rate_func=rate_functions.ease_out_cubic
        )

        # HARD safety remove
        scene.remove(title, cover)


# ============================================================
# OPTIONAL: brand plate
# ============================================================
def get_brand_plate(text="DATA VERIFIED", margin=0.60):
    sf = get_safe_frame(margin)
    plate = RoundedRectangle(width=2.4, height=0.55, corner_radius=0.12)
    plate.set_fill(color="#0B0B0B", opacity=0.85)
    plate.set_stroke(color=Brand.CYAN, width=1.5, opacity=0.7)
    plate.move_to([sf["left"] + 1.35, sf["bottom"] + 0.65, 0])

    t = Text(text, font="Montserrat", weight=BOLD, font_size=14, color=Brand.TEXT_MAIN)
    t.move_to(plate)

    grp = VGroup(plate, t)
    grp.set_z_index(260)
    return grp
