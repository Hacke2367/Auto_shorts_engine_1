# scanner_lab.py  (Scanner-only sandbox, 9:16)
# Manim Community v0.19.x
#
# Run:
#   manim -pqh scanner_lab.py ScannerLab
#
# IMPORTANT:
# - Output is forced to 9:16 (vertical) like your main template.
# - Scanner has a REAL "start scanning" moment (idle -> active) with visible motion.
# - Scan phase is NEUTRAL (no blue/pink verdict hint).
# - No global set_opacity(1). Only per-element stroke/fill opacity.

import math
import random
import numpy as np
from manim import *
from manim import rate_functions as rf

# -------------------------
# Force 9:16 output (vertical)
# -------------------------
config.pixel_width = 1080
config.pixel_height = 1920
config.frame_width = 8.0
config.frame_height = 14.2222


class Theme:
    BG = "#050505"
    TEXT_MAIN = "#FFFFFF"
    TEXT_SUB = "#A9B1BC"

    # neutral scanner palette (no tier hint)
    NEUTRAL = "#9FE9FF"     # cool cyan-white
    NEUTRAL_2 = "#78D8FF"   # deeper cyan
    SOFT_PINK = "#FF4D8D"   # only as micro sparkle (very low)
    SOFT_BLUE = "#2DD4FF"   # only as micro sparkle (very low)
    SOFT_GREEN = "#7CFFB2"  # for subtle "processing" vibe


def safe_text(
    s: str,
    font: str = "Montserrat",
    font_size: int = 24,
    color=WHITE,
    weight=None,
) -> Text:
    try:
        if weight is None:
            return Text(str(s), font=font, font_size=font_size, color=color)
        return Text(str(s), font=font, font_size=font_size, color=color, weight=weight)
    except Exception:
        return Text(str(s), font_size=font_size, color=color)


def clamp(x: float, a: float, b: float) -> float:
    return float(max(a, min(b, x)))


# -------------------------
# Background (active but subtle)
# -------------------------
def build_lab_bg() -> VGroup:
    W = float(config.frame_width)
    H = float(config.frame_height)

    g = VGroup()
    try:
        g.set_z_index(1)
    except Exception:
        pass

    # soft nebula
    n1 = Circle(radius=max(W, H) * 0.62).set_fill(Theme.SOFT_BLUE, 0.045).set_stroke(width=0).move_to([0, 1.2, 0])
    n2 = Circle(radius=max(W, H) * 0.48).set_fill(Theme.SOFT_PINK, 0.020).set_stroke(width=0).move_to([1.5, 0.2, 0])
    n3 = Circle(radius=max(W, H) * 0.45).set_fill(Theme.SOFT_BLUE, 0.020).set_stroke(width=0).move_to([-1.6, -1.4, 0])

    t = ValueTracker(0.0)

    def shimmer(_, dt):
        t.increment_value(dt)
        v = float(t.get_value())
        n1.set_fill(opacity=0.040 + 0.016 * (0.5 + 0.5 * math.sin(v * 0.55)))
        n2.set_fill(opacity=0.016 + 0.010 * (0.5 + 0.5 * math.sin(v * 0.42 + 1.6)))
        n3.set_fill(opacity=0.016 + 0.010 * (0.5 + 0.5 * math.sin(v * 0.48 + 2.2)))

    g.add(n1, n2, n3)
    g.add_updater(shimmer)

    # faint grid (very subtle)
    grid = VGroup()
    step = 0.85
    x = -W / 2
    while x <= W / 2 + 1e-6:
        ln = Line([x, -H / 2, 0], [x, H / 2, 0]).set_stroke(Theme.SOFT_BLUE, 1, 0.015)
        grid.add(ln)
        x += step
    y = -H / 2
    while y <= H / 2 + 1e-6:
        ln = Line([-W / 2, y, 0], [W / 2, y, 0]).set_stroke(Theme.SOFT_BLUE, 1, 0.012)
        grid.add(ln)
        y += step
    g.add(grid)

    # moving dust particles (active feel)
    rng = np.random.default_rng(9)
    dust = VGroup()
    for _ in range(64):
        d = Dot(
            point=np.array(
                [
                    rng.uniform(-W / 2 + 0.3, W / 2 - 0.3),
                    rng.uniform(-H / 2 + 0.3, H / 2 - 0.3),
                    0,
                ]
            ),
            radius=float(rng.uniform(0.010, 0.030)),
            color=WHITE,
        )
        d.set_opacity(float(rng.uniform(0.02, 0.09)))
        vel = np.array([rng.uniform(-0.020, 0.020), rng.uniform(0.012, 0.045), 0])

        def make_updater(v):
            def up(m: Mobject, dt: float):
                m.shift(v * dt)
                x0, y0, _ = m.get_center()
                if y0 > H / 2 + 0.2:
                    m.move_to([x0, -H / 2 - 0.1, 0])
                if x0 > W / 2 + 0.2:
                    m.move_to([-W / 2 - 0.1, y0, 0])
                if x0 < -W / 2 - 0.2:
                    m.move_to([W / 2 + 0.1, y0, 0])
            return up

        d.add_updater(make_updater(vel))
        dust.add(d)

    g.add(dust)

    # vignette
    vign = VGroup(
        Rectangle(width=W * 1.30, height=H * 0.25).set_fill(BLACK, 0.24).set_stroke(width=0).move_to([0, H * 0.42, 0]),
        Rectangle(width=W * 1.30, height=H * 0.25).set_fill(BLACK, 0.26).set_stroke(width=0).move_to([0, -H * 0.42, 0]),
        Rectangle(width=W * 0.25, height=H * 1.30).set_fill(BLACK, 0.18).set_stroke(width=0).move_to([W * 0.46, 0, 0]),
        Rectangle(width=W * 0.25, height=H * 1.30).set_fill(BLACK, 0.18).set_stroke(width=0).move_to([-W * 0.46, 0, 0]),
    )
    g.add(vign)
    return g


# -------------------------
# Scanner (premium, real start/active feel)
# -------------------------
def build_scanner(center: np.ndarray, radius: float = 2.05) -> dict:
    neutral = Theme.NEUTRAL
    neutral2 = Theme.NEUTRAL_2
    r = radius

    # --- base glow layers (soft, not cartoon) ---
    halo_outer = Circle(radius=r * 1.62).set_fill(neutral2, 0.045).set_stroke(width=0).move_to(center)
    halo_inner = Circle(radius=r * 1.18).set_fill(neutral, 0.032).set_stroke(width=0).move_to(center)

    # --- base plate + glass ---
    plate = Circle(radius=r * 0.80).set_fill("#05080B", 0.92).set_stroke(neutral, 2.2, 0.18).move_to(center)
    glass = Circle(radius=r * 0.84).set_fill(WHITE, 0.010).set_stroke(WHITE, 2.0, 0.085).move_to(center)

    # --- rings ---
    ring1 = Circle(radius=r * 0.94).set_stroke(Theme.TEXT_SUB, 2, 0.13).set_fill(opacity=0).move_to(center)
    ring2 = Circle(radius=r * 1.08).set_stroke(Theme.TEXT_SUB, 2, 0.11).set_fill(opacity=0).move_to(center)
    ring3 = Circle(radius=r * 1.22).set_stroke(Theme.TEXT_SUB, 2, 0.095).set_fill(opacity=0).move_to(center)
    ring4 = Circle(radius=r * 1.36).set_stroke(Theme.TEXT_SUB, 2, 0.080).set_fill(opacity=0).move_to(center)

    # --- segmented tick ring (flicker + slow rotation) ---
    dash = VGroup()
    dash_r = r * 1.44
    segs = 72
    for k in range(segs):
        a0 = (k / segs) * TAU
        a1 = a0 + TAU / segs * 0.38
        arc = Arc(radius=dash_r, start_angle=a0, angle=(a1 - a0), arc_center=center)
        arc.set_stroke(Theme.TEXT_SUB, 2, 0.075)
        dash.add(arc)

    # --- radar sector (VERY subtle, only while scanning) ---
    sweep = AnnularSector(
        inner_radius=r * 0.92,
        outer_radius=r * 1.44,
        start_angle=0.0,
        angle=0.36,
        fill_color=neutral,
        fill_opacity=0.0,   # IMPORTANT: never becomes a blob
        stroke_width=0,
    ).move_to(center)

    # --- center HUD panel ---
    panel = RoundedRectangle(width=3.75, height=1.15, corner_radius=0.20)
    panel.set_fill("#05080B", 0.84)
    panel.set_stroke(neutral, 1.9, 0.32)
    panel.move_to(center + DOWN * 0.02)

    panel_glow = panel.copy().set_fill(opacity=0).set_stroke(neutral, 12, 0.075)

    # --- lens highlight (subtle streak) ---
    highlight = RoundedRectangle(width=3.45, height=0.22, corner_radius=0.10)
    highlight.set_fill(WHITE, 0.0)
    highlight.set_stroke(width=0)
    highlight.rotate(-18 * DEGREES)
    highlight.move_to(panel.get_center() + UP * 0.12)

    # --- micro sparks ---
    sparks = VGroup()
    rng = np.random.default_rng(11)
    for _ in range(14):
        ang = float(rng.uniform(0, TAU))
        rr = float(rng.uniform(r * 0.90, r * 1.52))
        p = np.array([math.cos(ang) * rr, math.sin(ang) * rr, 0]) + center
        d = Dot(p, radius=float(rng.uniform(0.016, 0.030)), color=neutral)
        d.set_opacity(float(rng.uniform(0.03, 0.08)))
        sparks.add(d)

    # --- text (top + scanning + dots + 2 logs) ---
    t_top = safe_text("AI TRIBUNAL", font="Consolas", font_size=14, color=Theme.TEXT_SUB, weight=BOLD)
    t_main = safe_text("SCANNING", font_size=34, color=Theme.TEXT_MAIN, weight=BOLD)

    d1 = safe_text(".", font_size=34, color=Theme.TEXT_MAIN, weight=BOLD).set_opacity(0.0)
    d2 = safe_text(".", font_size=34, color=Theme.TEXT_MAIN, weight=BOLD).set_opacity(0.0)
    d3 = safe_text(".", font_size=34, color=Theme.TEXT_MAIN, weight=BOLD).set_opacity(0.0)
    dots = VGroup(d1, d2, d3).arrange(RIGHT, buff=0.06).next_to(t_main, RIGHT, buff=0.06)
    scan_line = VGroup(t_main, dots).arrange(RIGHT, buff=0.06)

    t_log1 = safe_text("awaiting evidence…", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD)
    t_log2 = safe_text("stand by // calibrating", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD)
    logs = VGroup(t_log1, t_log2).arrange(DOWN, buff=0.02)

    text_group = VGroup(t_top, scan_line, logs).arrange(DOWN, buff=0.10)
    text_group.move_to(panel.get_center() + DOWN * 0.02)

    # --- trackers ---
    time_t = ValueTracker(0.0)
    scan_strength = ValueTracker(0.0)   # 0 idle, 1 scanning
    sweep_ang = ValueTracker(0.0)

    # --- group (order matters for depth) ---
    base = VGroup(
        halo_outer,
        halo_inner,
        ring4,
        dash,
        sweep,
        ring3,
        ring2,
        ring1,
        plate,
        glass,
        sparks,
        panel_glow,
        panel,
        highlight,
    )

    # expose refs for entrance control + scan kick
    refs = {
        "halo_outer": halo_outer,
        "halo_inner": halo_inner,
        "ring1": ring1,
        "ring2": ring2,
        "ring3": ring3,
        "ring4": ring4,
        "dash": dash,
        "sweep": sweep,
        "plate": plate,
        "glass": glass,
        "sparks": sparks,
        "panel_glow": panel_glow,
        "panel": panel,
        "highlight": highlight,
    }

    try:
        base.set_z_index(120)
        text_group.set_z_index(260)
    except Exception:
        pass

    # --- animated dots ---
    dot_t = ValueTracker(0.0)

    def dots_updater(_, dt):
        dot_t.increment_value(dt)
        v = float(dot_t.get_value())
        phase = int((v * 2.25) % 4)
        d1.set_opacity(1.0 if phase >= 1 else 0.0)
        d2.set_opacity(1.0 if phase >= 2 else 0.0)
        d3.set_opacity(1.0 if phase >= 3 else 0.0)

    text_group.add_updater(dots_updater)

    # --- time tick updater ---
    def tick(_, dt):
        time_t.increment_value(dt)
        if float(scan_strength.get_value()) > 0.001:
            sweep_ang.increment_value(dt * (2.2 + 2.2 * float(scan_strength.get_value())))

    base.add_updater(tick)

    # --- ring breathe (always) + stronger when scanning ---
    def ring_breathe(base_op, freq, phase):
        def up(m: VMobject, dt):
            t = float(time_t.get_value())
            s = float(scan_strength.get_value())
            op = base_op + 0.05 * (0.5 + 0.5 * math.sin(t * freq + phase)) + 0.10 * s
            m.set_stroke(opacity=float(np.clip(op, 0.05, 0.30)))
        return up

    ring1.add_updater(ring_breathe(0.13, 1.8, 0.0))
    ring2.add_updater(ring_breathe(0.11, 1.5, 1.2))
    ring3.add_updater(ring_breathe(0.095, 1.2, 2.0))
    ring4.add_updater(ring_breathe(0.080, 1.0, 2.7))

    # --- dash flicker pattern + slow rotation ---
    def dash_fx(m: VGroup, dt):
        t = float(time_t.get_value())
        s = float(scan_strength.get_value())
        n = max(1, len(m))

        # very slow rotation for "machine" feel
        m.rotate((0.05 + 0.15 * s) * dt, about_point=center)

        for i, a in enumerate(m):
            ph = (i / n) * TAU
            window = 0.5 + 0.5 * math.sin(t * 1.15 + ph)
            op = 0.05 + 0.06 * window + 0.16 * s * (0.35 + 0.65 * window)
            a.set_stroke(opacity=float(np.clip(op, 0.035, 0.36)))

    dash.add_updater(dash_fx)

    # --- sweep sector (only during scan) ---
    prev_ang = {"a": 0.0}

    def sweep_fx_safe(m: Mobject, dt):
        s = float(scan_strength.get_value())
        ang = float(sweep_ang.get_value()) % TAU

        # HARD CLAMP: never allow a fill that can blob the whole area
        m.set_fill(opacity=clamp(0.0 + 0.055 * s, 0.0, 0.080))

        # rotate by delta only (no snapping)
        da = ang - prev_ang["a"]
        prev_ang["a"] = ang
        m.rotate(da, about_point=center)

    sweep.add_updater(sweep_fx_safe)

    # --- panel + highlight + sparks react to scan ---
    def panel_fx(_, dt):
        s = float(scan_strength.get_value())
        t = float(time_t.get_value())

        panel_glow.set_stroke(opacity=0.06 + 0.14 * s)
        panel.set_stroke(neutral, 1.9 + 0.7 * s, 0.30 + 0.18 * s)

        # highlight shimmer (more visible during scan)
        highlight.set_fill(WHITE, 0.00 + 0.10 * s * (0.5 + 0.5 * math.sin(t * 2.2)))
        highlight.move_to(
            panel.get_center()
            + UP * (0.10 + 0.05 * math.sin(t * 1.45))
            + RIGHT * (0.15 * math.sin(t * 1.10))
        )

        # halo intensifies a bit during scan (still subtle)
        halo_outer.set_fill(opacity=0.040 + 0.028 * s)
        halo_inner.set_fill(opacity=0.028 + 0.020 * s)

        # sparks breathe + boost
        for k, d in enumerate(sparks):
            base_op = 0.03 + 0.04 * (0.5 + 0.5 * math.sin(t * 1.6 + k))
            d.set_opacity(float(np.clip(base_op + 0.22 * s, 0.02, 0.38)))

    panel.add_updater(panel_fx)

    return {
        "group": base,
        "text": text_group,
        "panel": panel,
        "panel_glow": panel_glow,
        "scan_strength": scan_strength,
        "t_log1": t_log1,
        "t_log2": t_log2,
        "center": np.array(center),
        "radius": r,
        "neutral": neutral,
        "refs": refs,
    }


# -------------------------
# Entrance + Scan controls
# -------------------------
def play_scanner_entrance(scene: Scene, sc: dict):
    g = sc["group"]
    txt = sc["text"]
    R = sc["refs"]

    # Add sequentially (no "already on screen" feel)
    scene.add(R["halo_outer"], R["halo_inner"])
    scene.play(
        FadeIn(R["halo_outer"], scale=0.985),
        FadeIn(R["halo_inner"], scale=0.985),
        run_time=0.28,
        rate_func=rf.ease_out_cubic,
    )

    # rings draw
    scene.add(R["ring4"], R["ring3"], R["ring2"], R["ring1"])
    scene.play(LaggedStart(Create(R["ring4"]), Create(R["ring3"]), lag_ratio=0.10),
               run_time=0.35, rate_func=rf.ease_out_cubic)
    scene.play(LaggedStart(Create(R["ring2"]), Create(R["ring1"]), lag_ratio=0.10),
               run_time=0.35, rate_func=rf.ease_out_cubic)

    # dash + plate/glass + sweep (sweep stays invisible until scan_strength>0)
    scene.add(R["dash"], R["plate"], R["glass"], R["sweep"])
    scene.play(
        FadeIn(R["dash"], shift=UP * 0.05),
        FadeIn(R["plate"], scale=0.985),
        FadeIn(R["glass"], scale=0.985),
        run_time=0.32,
        rate_func=rf.ease_out_cubic,
    )

    # panel snap-in + text boot
    scene.add(R["panel_glow"], R["panel"], R["highlight"])
    scene.play(
        FadeIn(R["panel_glow"], scale=0.99),
        FadeIn(R["panel"], shift=DOWN * 0.03),
        FadeIn(txt, shift=UP * 0.05),
        run_time=0.34,
        rate_func=rf.ease_out_cubic,
    )

    # sparks last (micro life)
    scene.add(R["sparks"])
    scene.play(FadeIn(R["sparks"]), run_time=0.18, rate_func=rf.ease_out_cubic)


def start_scan(scene: Scene, sc: dict):
    # Strong "scanner turned ON" feel: strength ramps + DOUBLE ripple (stroke-only)
    center = sc["center"]
    neutral = sc["neutral"]
    r = float(sc["radius"])

    p1 = Circle(radius=r * 1.10).move_to(center).set_fill(opacity=0).set_stroke(neutral, 3.2, 0.0)
    p2 = Circle(radius=r * 1.26).move_to(center).set_fill(opacity=0).set_stroke(neutral, 2.6, 0.0)
    try:
        p1.set_z_index(115)
        p2.set_z_index(115)
    except Exception:
        pass
    scene.add(p1, p2)

    # micro kick: dash + panel glow pop (very small, premium)
    R = sc["refs"]
    scene.play(
        sc["scan_strength"].animate.set_value(1.0),
        R["panel_glow"].animate.set_stroke(opacity=0.15),
        run_time=0.18,
        rate_func=rf.ease_out_cubic,
    )

    scene.play(
        p1.animate.scale(1.32).set_stroke(opacity=0.32),
        p2.animate.scale(1.36).set_stroke(opacity=0.24),
        run_time=0.22,
        rate_func=rf.ease_out_cubic,
    )
    scene.play(
        p1.animate.scale(1.20).set_stroke(opacity=0.0),
        p2.animate.scale(1.18).set_stroke(opacity=0.0),
        R["panel_glow"].animate.set_stroke(opacity=0.075),
        run_time=0.42,
        rate_func=rf.ease_in_out_sine,
    )

    scene.remove(p1, p2)


def stop_scan(scene: Scene, sc: dict):
    scene.play(sc["scan_strength"].animate.set_value(0.0), run_time=0.28, rate_func=rf.ease_in_out_sine)


# -------------------------
# Demo Scene (scanner-only, vertical)
# -------------------------
class ScannerLab(Scene):
    def construct(self):
        self.camera.background_color = Theme.BG

        bg = build_lab_bg()
        self.add(bg)

        # scanner center for 9:16 (slightly above true center)
        center = np.array([0.0, 0.4, 0.0])
        sc = build_scanner(center=center, radius=2.15)

        # Proper entrance (build in front of eyes)
        play_scanner_entrance(self, sc)
        self.wait(0.25)

        # simulate: "image arrives -> scanning starts"
        start_scan(self, sc)

        scan_lines = [
            "ok ok, focus… scanning",
            "checking patterns // entropy",
            "indexing evidence…",
            "cross-validating…",
            "verifying checksum…",
            "signal lock: stable",
            "finalizing verdict…",
            "noise floor: nominal",
            "calibrating lens…",
        ]

        def set_logs(l1: str, l2: str):
            # log1 = active tint (green), log2 = sub
            new1 = safe_text(l1, font="Consolas", font_size=12, color=Theme.SOFT_GREEN, weight=BOLD).move_to(sc["t_log1"].get_center())
            new2 = safe_text(l2, font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD).move_to(sc["t_log2"].get_center())
            self.play(
                Transform(sc["t_log1"], new1),
                Transform(sc["t_log2"], new2),
                run_time=0.16,
                rate_func=rf.ease_out_cubic,
            )

        for _ in range(6):
            a = random.choice(scan_lines)
            b = random.choice([x for x in scan_lines if x != a])
            set_logs(a, b)
            self.wait(0.14)

        # Verdict demo (IMPORTANT FIX):
        # Do NOT Transform(sc["text"], verdict) because sc["text"] has dot-updater;
        # It can conflict and cause weird visuals. Use overlay instead.
        verdict = VGroup(
            safe_text("VERDICT", font="Consolas", font_size=14, color=Theme.TEXT_SUB, weight=BOLD),
            safe_text("TIER 1", font_size=34, color=Theme.SOFT_GREEN, weight=BOLD),
        ).arrange(DOWN, buff=0.08).move_to(sc["panel"].get_center() + UP * 0.02)
        try:
            verdict.set_z_index(400)
        except Exception:
            pass

        self.play(FadeIn(verdict, scale=0.98), run_time=0.18, rate_func=rf.ease_out_cubic)
        self.wait(0.25)
        self.play(FadeOut(verdict, scale=1.02), run_time=0.18, rate_func=rf.ease_in_cubic)

        # back to scanning
        set_logs("awaiting evidence…", "signal lock: stable")
        self.wait(0.20)

        stop_scan(self, sc)
        self.wait(1.2)
