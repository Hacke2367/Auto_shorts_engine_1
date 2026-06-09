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

    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_GREEN = "#00FF66"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"
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
    TEXT_SUB = getattr(Theme, "TEXT_SUB", "#B8B8B8")


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

    # Vignette
    vignette = Rectangle(width=config.frame_width + 2, height=config.frame_height + 2)
    vignette.set_fill(color=BLACK, opacity=0)
    vignette.set_stroke(color=BLACK, width=140, opacity=0.45)
    vignette.set_z_index(240)

    # Scanlines
    scanlines = VGroup()
    lines_n = 46
    for i in range(lines_n):
        y = sf["bottom"] + (i * (sf["h"] / lines_n))
        ln = Line(LEFT * (config.frame_width), RIGHT * (config.frame_width))
        ln.set_y(y)
        ln.set_stroke(color=Brand.CYAN, width=1, opacity=0.02)
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

    def _update_timer(m):
        m.become(
            Text(_format_time(getattr(scene, "time", 0.0)),
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
                            palette=None,
                            twinkle=True,
                            parallax=True):
    """
    Atmospheric floating-particle field (shared by every template).

    Backward-compatible: the original 6 args behave exactly as before. The
    premium upgrade lives entirely inside the SAME single O(n) VGroup updater
    (no new per-frame mobjects — same render-cost class as the old one-line
    shift updater):
      - twinkle      : per-particle opacity pulse on a precomputed phase offset
      - depth parallax: two bands (near = larger/brighter/faster, far =
                        smaller/dimmer/slower) for a subtle 3D feel
      - colour variety: optional small accent palette instead of one flat colour
                        (default = the requested accent + brand cyan)
      - soft edge wrap: particles drifting past the top safe edge recycle to the
                        bottom so the cloud never empties on longer videos
    """
    sf = get_safe_frame(margin)
    color = color or Brand.CYAN

    # Colour variety: default = requested accent + brand cyan. Passing a single
    # colour (or palette=[c]) collapses back to the old flat look.
    if palette is None:
        palette = [color, Brand.CYAN]
    if not palette:
        palette = [color]

    top, bottom = sf["top"], sf["bottom"]
    left, right = sf["left"], sf["right"]

    r_lo, r_hi = radius_range
    o_lo, o_hi = opacity_range
    r_mid = (r_lo + r_hi) / 2.0
    o_mid = (o_lo + o_hi) / 2.0

    particles = VGroup()
    phases, base_ops, speeds, amps = [], [], [], []  # per-particle state (closure)

    for _ in range(n):
        # Two depth bands. ~45% near (foreground), rest far (background).
        near = parallax and (random.random() < 0.45)
        if near:
            # near = clear foreground: noticeably larger + a touch brighter so
            # the eye actually reads them (feedback: particles were too small).
            r = random.uniform(r_hi, r_hi * 1.7)
            base_op = random.uniform(o_mid, min(o_hi * 1.15, 0.32))
            speed = drift * random.uniform(1.2, 1.6)
            amp = 0.45
        else:
            r = random.uniform(r_lo, r_mid) if parallax else random.uniform(r_lo, r_hi)
            base_op = random.uniform(o_lo, o_mid) if parallax else random.uniform(o_lo, o_hi)
            speed = drift * (random.uniform(0.5, 0.85) if parallax else 1.0)
            amp = 0.30

        p = Dot(radius=r, color=random.choice(palette))
        p.move_to([random.uniform(left, right),
                   random.uniform(bottom, top), 0])
        p.set_opacity(base_op)
        particles.add(p)

        phases.append(random.uniform(0.0, 2.0 * np.pi))
        base_ops.append(base_op)
        speeds.append(speed)
        amps.append(amp if twinkle else 0.0)

    clock = [0.0]
    twinkle_freq = 1.6

    def _update(group, dt):
        # Single O(n) updater — drift + soft-wrap + twinkle. Fail-safe so a
        # decoration error can never crash a render.
        try:
            clock[0] += dt
            t = clock[0]
            for idx, p in enumerate(group.submobjects):
                p.shift(UP * speeds[idx] * dt)
                if p.get_center()[1] > top + 0.15:        # recycle off the top
                    p.move_to([random.uniform(left, right), bottom - 0.10, 0])
                if amps[idx]:                              # twinkle around base
                    op = base_ops[idx] * (1.0 + amps[idx] * np.sin(t * twinkle_freq + phases[idx]))
                    p.set_opacity(op if op > 0.02 else 0.02)
        except Exception:
            pass

    particles.add_updater(_update)
    particles.set_z_index(5)
    return particles


# ============================================================
# ✅ CINEMATIC BACKGROUND (shared atmosphere: gradient + brand glow)
#   - additive only: instant scene.add() + ONE lightweight breathing
#     updater (same render-cost class as the existing flicker/particles)
#   - fully fail-safe: any error degrades to the current flat background
#     and never crashes a render
# ============================================================
def add_cinematic_background(scene, accent=None, breathing=True):
    """
    Premium background atmosphere shared by every template.

    Draws a subtle vertical gradient (cool charcoal -> near-black) plus a soft
    radial brand-tinted glow ("pool of light") just above frame centre, and
    optionally attaches a single slow breathing updater (opacity sway + tiny
    drift) in the same render-cost class as the existing particle/flicker
    updaters.

    Sync-safe: no ``self.play()`` / ``run_time`` and no timeline math — only an
    instant ``scene.add(...)`` plus at most one lightweight updater. Returns the
    background ``VGroup`` (callers may ``.remove()`` it; not required) or ``None``
    if anything fails.
    """
    try:
        accent = accent or Brand.CYAN

        W = config.frame_width + 2
        H = config.frame_height + 2

        # --- Base vertical gradient: cool charcoal (top) -> near-black (bottom).
        # Stacked full-width strips guarantee a clean top->bottom gradient and
        # stay fully static (zero per-frame Python cost).
        strips = VGroup()
        n_strips = 24
        strip_h = H / n_strips
        for i in range(n_strips):
            strip = Rectangle(width=W, height=strip_h + 0.03, stroke_width=0)
            strip.set_fill(opacity=1.0)
            strip.move_to([0.0, (H / 2.0) - strip_h * (i + 0.5), 0.0])
            strips.add(strip)
        strips.set_color_by_gradient("#0E1116", "#050608")
        strips.set_z_index(-100)

        # --- Radial brand glow: concentric low-opacity ellipses approximate a
        # soft gaussian pool of light with zero per-frame cost.
        glow_center = np.array([0.0, config.frame_height * 0.12, 0.0])
        glow_specs = [
            (config.frame_width * 1.50, config.frame_height * 0.90, 0.060),
            (config.frame_width * 1.05, config.frame_height * 0.62, 0.045),
            (config.frame_width * 0.65, config.frame_height * 0.40, 0.030),
        ]
        glow = VGroup()
        base_ops = []
        for w, h, op in glow_specs:
            e = Ellipse(width=w, height=h, stroke_width=0)
            e.set_fill(color=accent, opacity=op)
            e.move_to(glow_center)
            glow.add(e)
            base_ops.append(op)
        glow.set_z_index(-90)

        bg = VGroup(strips, glow)
        scene.add(bg)

        # --- Breathing drift: the ONE allowed updater (flicker cost class).
        # Gently sways glow opacity (~+-25% of base) and nudges it a few
        # hundredths in Y on a slow sine. O(3) per frame.
        if breathing:
            def _breathe(m, dt):
                phase = np.sin(getattr(scene, "time", 0.0) * 0.4)
                for e, base_op in zip(m.submobjects, base_ops):
                    e.set_fill(opacity=base_op * (1.0 + 0.25 * phase))
                m.move_to(glow_center + np.array([0.0, 0.06 * phase, 0.0]))
            glow.add_updater(_breathe)

        return bg
    except Exception:
        # Decoration must never break a render.
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
        title = Text(brand_title, font="Montserrat", weight=BOLD, font_size=54)
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
