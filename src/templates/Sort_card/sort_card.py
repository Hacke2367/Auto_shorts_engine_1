# sort_card.py  (FINAL GOD POLISH - clean background, scanner ALWAYS ON, NO flash, route-lines glow, 6s/card, 1-line logs ">>")
# Manim Community v0.19.x compatible
#
# Run:
#   manim -pqh sort_card.py SortCardTribunalFinal
#
# CSV format (meta in first line):
#   # TITLE=TIER 1 vs TIER 2, SUB=AI TRIBUNAL SORT TEST
#   Image,Category,Reason
#
# Images:
#   assets/images/<Image>

import os
import sys
import math
import random
import re
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from manim import *
from manim import rate_functions as rf

# ============================================================
# PROJECT IMPORTS (preferred) + FALLBACK
# ============================================================
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    sys.path.append(project_root)

    from src.config import DATA_DIR, ASSETS_DIR, BACKGROUND_COLOR, Theme  # type: ignore
    from src.utils import IntroManager, get_branding_border  # type: ignore
except Exception:
    project_root = os.getcwd()
    DATA_DIR = os.path.join(project_root, "data")
    ASSETS_DIR = os.path.join(project_root, "assets")
    BACKGROUND_COLOR = "#050505"

    class Theme:
        NEON_BLUE = "#2DD4FF"
        NEON_PINK = "#FF4D8D"
        NEON_GREEN = "#00FF66"
        NEON_YELLOW = "#FFE86B"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#A9B1BC"

    def get_branding_border():
        border = Rectangle(height=config.frame_height, width=config.frame_width)
        border.set_stroke(width=8, color=[Theme.NEON_BLUE, Theme.NEON_PINK], opacity=0.55)
        border.set_fill(opacity=0)
        return border

    class IntroManager:
        @staticmethod
        def play_intro(
            scene,
            brand_title="BIGDATA LEAK",
            brand_sub="SYSTEM BREACH DETECTED",
            feed_text="FEED_SORT // TRIBUNAL",
            footer_text="CONFIDENTIAL // VERIFIED",
        ):
            rec = Text("● REC", font="Consolas", font_size=16, color=RED).to_corner(UL).shift(
                DOWN * 0.2 + RIGHT * 0.2
            )
            hdr = Text(feed_text, font="Consolas", font_size=14, color=Theme.TEXT_SUB).to_corner(UR).shift(
                DOWN * 0.2 + LEFT * 0.2
            )
            t1 = Text(brand_title, font="Montserrat", font_size=42, weight=BOLD, color=Theme.TEXT_MAIN).move_to(UP * 0.6)
            t2 = Text(brand_sub, font="Montserrat", font_size=18, color=Theme.TEXT_SUB).next_to(t1, DOWN, buff=0.2)
            foot = Text(footer_text, font="Consolas", font_size=12, color=Theme.TEXT_SUB).to_edge(DOWN, buff=0.35)
            scene.play(
                FadeIn(rec),
                FadeIn(hdr),
                FadeIn(t1, shift=UP * 0.15),
                FadeIn(t2, shift=UP * 0.12),
                FadeIn(foot),
                run_time=0.85,
                rate_func=rf.ease_out_cubic,
            )
            scene.play(
                FadeOut(t1, shift=UP * 0.10),
                FadeOut(t2, shift=UP * 0.10),
                FadeOut(foot),
                run_time=0.45,
                rate_func=rf.ease_in_out_sine,
            )
            return rec, hdr


# ============================================================
# HELPERS
# ============================================================
_META_RE = re.compile(r"([A-Za-z_]+)\s*=\s*([^,]+)")


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


def ellipsize(s: str, n: int = 28) -> str:
    s = str(s)
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def clamp(x: float, a: float, b: float) -> float:
    return float(max(a, min(b, x)))


def load_csv_with_meta(csv_path: str) -> Tuple[Dict[str, str], pd.DataFrame]:
    meta = {"TITLE": "TIER 1 vs TIER 2", "SUB": "AI TRIBUNAL SORT TEST"}
    if not os.path.exists(csv_path):
        df = pd.DataFrame(
            {
                "Image": ["python.jpg", "java.jpg", "html.jpg", "cpp.jpg"],
                "Category": [1, 2, 2, 1],
                "Reason": ["AI KING", "VERBOSE", "NOT CODE", "FAST AF"],
            }
        )
        return meta, df

    with open(csv_path, "r", encoding="utf-8") as f:
        first = f.readline().strip()

    if first.startswith("#"):
        first = first[1:].strip()
        for m in _META_RE.finditer(first):
            k = m.group(1).strip().upper()
            v = m.group(2).strip()
            meta[k] = v

    df = pd.read_csv(csv_path, comment="#")
    df.columns = [c.strip() for c in df.columns]
    if "Reason" not in df.columns:
        df["Reason"] = ["UNKNOWN"] * len(df)
    if "Category" not in df.columns:
        df["Category"] = [2] * len(df)
    if "Image" not in df.columns:
        df["Image"] = [""] * len(df)

    def _cat(x):
        try:
            return int(float(x))
        except Exception:
            return 2

    df["Category"] = df["Category"].apply(_cat)
    df["Reason"] = df["Reason"].astype(str).fillna("UNKNOWN")
    df["Image"] = df["Image"].astype(str).fillna("")
    return meta, df


# ============================================================
# BACKGROUND (CLEAN - NO RANDOM DOTS)
# ============================================================
def build_god_background() -> VGroup:
    W = float(config.frame_width)
    H = float(config.frame_height)

    g = VGroup()
    try:
        g.set_z_index(1)
    except Exception:
        pass

    nebula1 = Circle(radius=max(W, H) * 0.58).set_fill(Theme.NEON_BLUE, 0.06).set_stroke(width=0)
    nebula1.move_to([0.0, 0.5, 0])
    nebula2 = Circle(radius=max(W, H) * 0.45).set_fill(Theme.NEON_PINK, 0.035).set_stroke(width=0)
    nebula2.move_to([1.2, -0.2, 0])
    nebula3 = Circle(radius=max(W, H) * 0.40).set_fill(Theme.NEON_BLUE, 0.025).set_stroke(width=0)
    nebula3.move_to([-1.4, -0.6, 0])

    t = ValueTracker(0.0)

    def shimmer_updater(_, dt: float):
        t.increment_value(dt)
        v = float(t.get_value())
        nebula1.set_fill(opacity=0.055 + 0.012 * (0.5 + 0.5 * math.sin(v * 0.8)))
        nebula2.set_fill(opacity=0.030 + 0.010 * (0.5 + 0.5 * math.sin(v * 0.6 + 1.7)))
        nebula3.set_fill(opacity=0.022 + 0.008 * (0.5 + 0.5 * math.sin(v * 0.7 + 2.6)))

    g.add(nebula1, nebula2, nebula3)
    g.add_updater(shimmer_updater)

    grid = VGroup()
    step = 0.75
    x = -W / 2
    while x <= W / 2 + 1e-6:
        ln = Line([x, -H / 2, 0], [x, H / 2, 0]).set_stroke(Theme.NEON_BLUE, 1, 0.018)
        grid.add(ln)
        x += step
    y = -H / 2
    while y <= H / 2 + 1e-6:
        ln = Line([-W / 2, y, 0], [W / 2, y, 0]).set_stroke(Theme.NEON_BLUE, 1, 0.016)
        grid.add(ln)
        y += step
    g.add(grid)

    vign = VGroup(
        Rectangle(width=W * 1.30, height=H * 0.22).set_fill(BLACK, 0.22).set_stroke(width=0).move_to([0, H * 0.42, 0]),
        Rectangle(width=W * 1.30, height=H * 0.22).set_fill(BLACK, 0.24).set_stroke(width=0).move_to([0, -H * 0.42, 0]),
        Rectangle(width=W * 0.22, height=H * 1.30).set_fill(BLACK, 0.18).set_stroke(width=0).move_to([W * 0.46, 0, 0]),
        Rectangle(width=W * 0.22, height=H * 1.30).set_fill(BLACK, 0.18).set_stroke(width=0).move_to([-W * 0.46, 0, 0]),
    )
    g.add(vign)
    return g


# ============================================================
# HEADER (vs never disappears)
# ============================================================
def build_header(meta_title: str, meta_sub: str) -> Dict[str, Mobject]:
    blue = Theme.NEON_BLUE
    pink = Theme.NEON_PINK

    raw = (meta_title or "TIER 1 vs TIER 2").strip()
    parts = re.split(r"\s+vs\s+", raw, flags=re.IGNORECASE)

    left_txt = "TIER 1"
    right_txt = "TIER 2"
    if len(parts) == 2:
        left_txt = parts[0].strip() or "TIER 1"
        right_txt = parts[1].strip() or "TIER 2"

    left = safe_text(left_txt.upper(), font_size=46, color=blue, weight=BOLD)
    vs = safe_text("vs", font_size=30, color=GREY_B, weight=BOLD)
    right = safe_text(right_txt.upper(), font_size=46, color=pink, weight=BOLD)
    title = VGroup(left, vs, right).arrange(RIGHT, buff=0.22)

    try:
        title.set_z_index(500)
    except Exception:
        pass
    title.to_edge(UP, buff=0.78).shift(DOWN * 0.12)

    sub = safe_text(meta_sub, font_size=18, color=Theme.TEXT_SUB, weight=BOLD)
    try:
        sub.set_z_index(500)
    except Exception:
        pass
    sub.next_to(title, DOWN, buff=0.12)

    line_w = min(float(config.frame_width) * 0.76, 7.0)
    uL = Line(LEFT * line_w / 2, ORIGIN).set_stroke(color=blue, width=4, opacity=0.95)
    uR = Line(ORIGIN, RIGHT * line_w / 2).set_stroke(color=pink, width=4, opacity=0.95)
    underline = VGroup(uL, uR).arrange(RIGHT, buff=0)
    try:
        underline.set_z_index(500)
    except Exception:
        pass
    underline.next_to(sub, DOWN, buff=0.18)

    path = Line(underline.get_left(), underline.get_right()).set_stroke(width=0, opacity=0)
    dot = Dot(radius=0.045, color=blue).move_to(path.get_start())
    try:
        dot.set_z_index(520)
    except Exception:
        pass

    return {"title": title, "sub": sub, "underline": underline, "path": path, "dot": dot}


# ============================================================
# EVIDENCE INTAKE BOX
# ============================================================
def build_evidence_box(center: np.ndarray) -> Dict[str, Mobject]:
    blue = Theme.NEON_BLUE
    W = float(config.frame_width)

    w = min(W * 0.78, 6.3)
    h = 1.58

    outer = RoundedRectangle(width=w, height=h, corner_radius=0.22)
    outer.set_fill("#05080B", 0.48)
    outer.set_stroke(blue, 2.8, 0.74)
    outer.move_to(center)

    glow = outer.copy().set_fill(opacity=0).set_stroke(blue, 16, 0.10)

    inner = RoundedRectangle(width=w * 0.92, height=h * 0.70, corner_radius=0.18)
    inner.set_fill("#05080B", 0.55)
    inner.set_stroke(blue, 2.0, 0.28)
    inner.move_to(center + UP * 0.06)

    label = safe_text("evidence intake", font="Consolas", font_size=12, color=Theme.TEXT_SUB)
    label.set_opacity(0.9)
    label.next_to(outer, DOWN, buff=0.12)

    grp = VGroup(glow, outer, inner, label)
    try:
        grp.set_z_index(260)
        glow.set_z_index(258)
        outer.set_z_index(259)
        inner.set_z_index(260)
        label.set_z_index(261)
    except Exception:
        pass

    return {"group": grp, "outer": outer, "inner": inner, "glow": glow, "label": label}


# ============================================================
# SCANNER (ALWAYS-ON + SINGLE LOG LINE ">>")
# ============================================================
def build_scanner(center: np.ndarray) -> Dict[str, Mobject]:
    neutral = "#9FE9FF"
    neutral2 = "#78D8FF"
    r = 1.62

    halo_outer = Circle(radius=r * 1.62).set_fill(neutral2, 0.045).set_stroke(width=0).move_to(center)
    halo_inner = Circle(radius=r * 1.18).set_fill(neutral, 0.032).set_stroke(width=0).move_to(center)

    plate = Circle(radius=r * 0.80).set_fill("#05080B", 0.92).set_stroke(neutral, 2.2, 0.18).move_to(center)
    glass = Circle(radius=r * 0.84).set_fill(WHITE, 0.010).set_stroke(WHITE, 2.0, 0.085).move_to(center)

    ring1 = Circle(radius=r * 0.94).set_stroke(Theme.TEXT_SUB, 2, 0.13).set_fill(opacity=0).move_to(center)
    ring2 = Circle(radius=r * 1.08).set_stroke(Theme.TEXT_SUB, 2, 0.11).set_fill(opacity=0).move_to(center)
    ring3 = Circle(radius=r * 1.22).set_stroke(Theme.TEXT_SUB, 2, 0.095).set_fill(opacity=0).move_to(center)
    ring4 = Circle(radius=r * 1.36).set_stroke(Theme.TEXT_SUB, 2, 0.080).set_fill(opacity=0).move_to(center)

    dash = VGroup()
    dash_r = r * 1.44
    segs = 72
    for k in range(segs):
        a0 = (k / segs) * TAU
        a1 = a0 + TAU / segs * 0.38
        arc = Arc(radius=dash_r, start_angle=a0, angle=(a1 - a0), arc_center=center)
        arc.set_stroke(Theme.TEXT_SUB, 2, 0.075)
        dash.add(arc)

    sweep = AnnularSector(
        inner_radius=r * 0.92,
        outer_radius=r * 1.44,
        start_angle=0.0,
        angle=0.36,
        fill_color=neutral,
        fill_opacity=0.0,
        stroke_width=0,
    ).move_to(center)

    panel = RoundedRectangle(width=3.30, height=1.10, corner_radius=0.20)
    panel.set_fill("#05080B", 0.84)
    panel.set_stroke(neutral, 1.9, 0.32)
    panel.move_to(center + DOWN * 0.02)

    panel_glow = panel.copy().set_fill(opacity=0).set_stroke(neutral, 12, 0.075)

    highlight = RoundedRectangle(width=3.00, height=0.22, corner_radius=0.10)
    highlight.set_fill(WHITE, 0.0)
    highlight.set_stroke(width=0)
    highlight.rotate(-18 * DEGREES)
    highlight.move_to(panel.get_center() + UP * 0.12)

    sparks = VGroup()
    rng = np.random.default_rng(11)
    for _ in range(12):
        ang = float(rng.uniform(0, TAU))
        rr = float(rng.uniform(r * 0.90, r * 1.52))
        p = np.array([math.cos(ang) * rr, math.sin(ang) * rr, 0]) + center
        d = Dot(p, radius=float(rng.uniform(0.016, 0.030)), color=neutral)
        d.set_opacity(float(rng.uniform(0.03, 0.08)))
        sparks.add(d)

    t_top = safe_text("AI TRIBUNAL", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD)
    t_main = safe_text("SCANNING", font="Montserrat", font_size=20, color=Theme.TEXT_MAIN, weight=BOLD)

    d1 = safe_text(".", font="Montserrat", font_size=20, color=Theme.TEXT_MAIN, weight=BOLD).set_opacity(0.0)
    d2 = safe_text(".", font="Montserrat", font_size=20, color=Theme.TEXT_MAIN, weight=BOLD).set_opacity(0.0)
    d3 = safe_text(".", font="Montserrat", font_size=20, color=Theme.TEXT_MAIN, weight=BOLD).set_opacity(0.0)
    dots = VGroup(d1, d2, d3).arrange(RIGHT, buff=0.04).next_to(t_main, RIGHT, buff=0.06)
    scan_line = VGroup(t_main, dots).arrange(RIGHT, buff=0.06)

    # Single readable log line (fits inside panel)
    log1 = safe_text(">> awaiting evidence…", font="Consolas", font_size=11, color=Theme.TEXT_SUB, weight=BOLD)
    log1.set_opacity(0.95)

    text_group = VGroup(t_top, scan_line, log1).arrange(DOWN, buff=0.07)
    text_group.move_to(panel.get_center() + DOWN * 0.01)

    time_t = ValueTracker(0.0)
    scan_strength = ValueTracker(0.0)
    sweep_ang = ValueTracker(0.0)

    base = VGroup(
        halo_outer, halo_inner,
        ring4, dash, sweep, ring3, ring2, ring1,
        plate, glass, sparks,
        panel_glow, panel, highlight,
    )

    try:
        base.set_z_index(320)
        text_group.set_z_index(560)
    except Exception:
        pass

    dot_t = ValueTracker(0.0)

    def dots_updater(_, dt):
        dot_t.increment_value(dt)
        v = float(dot_t.get_value())
        phase = int((v * 2.25) % 4)
        d1.set_opacity(1.0 if phase >= 1 else 0.0)
        d2.set_opacity(1.0 if phase >= 2 else 0.0)
        d3.set_opacity(1.0 if phase >= 3 else 0.0)

    text_group.add_updater(dots_updater)

    def tick(_, dt):
        time_t.increment_value(dt)
        if float(scan_strength.get_value()) > 0.001:
            sweep_ang.increment_value(dt * (2.0 + 2.6 * float(scan_strength.get_value())))

    base.add_updater(tick)

    def ring_breathe(base_op, freq, phase):
        def up(m: VMobject, dt):
            t = float(time_t.get_value())
            s = float(scan_strength.get_value())
            op = base_op + 0.05 * (0.5 + 0.5 * math.sin(t * freq + phase)) + 0.10 * s
            m.set_stroke(opacity=float(np.clip(op, 0.06, 0.32)))
        return up

    ring1.add_updater(ring_breathe(0.13, 1.8, 0.0))
    ring2.add_updater(ring_breathe(0.11, 1.5, 1.2))
    ring3.add_updater(ring_breathe(0.095, 1.2, 2.0))
    ring4.add_updater(ring_breathe(0.080, 1.0, 2.7))

    def dash_fx(m: VGroup, dt):
        t = float(time_t.get_value())
        s = float(scan_strength.get_value())
        n = max(1, len(m))
        m.rotate((0.05 + 0.14 * s) * dt, about_point=center)
        for i, a in enumerate(m):
            ph = (i / n) * TAU
            window = 0.5 + 0.5 * math.sin(t * 1.15 + ph)
            op = 0.05 + 0.06 * window + 0.15 * s * (0.35 + 0.65 * window)
            a.set_stroke(opacity=float(np.clip(op, 0.045, 0.36)))

    dash.add_updater(dash_fx)

    prev = {"a": 0.0}

    def sweep_fx(m: Mobject, dt):
        s = float(scan_strength.get_value())
        ang = float(sweep_ang.get_value()) % TAU
        m.set_fill(opacity=clamp(0.055 * s, 0.0, 0.085))
        da = ang - prev["a"]
        prev["a"] = ang
        m.rotate(da, about_point=center)

    sweep.add_updater(sweep_fx)

    def panel_fx(_, dt):
        s = float(scan_strength.get_value())
        t = float(time_t.get_value())

        panel_glow.set_stroke(opacity=0.07 + 0.14 * s)
        panel.set_stroke(neutral, 1.9 + 0.7 * s, 0.32 + 0.18 * s)

        highlight.set_fill(WHITE, 0.00 + 0.10 * s * (0.5 + 0.5 * math.sin(t * 2.2)))
        highlight.move_to(
            panel.get_center()
            + UP * (0.10 + 0.05 * math.sin(t * 1.45))
            + RIGHT * (0.15 * math.sin(t * 1.10))
        )

        halo_outer.set_fill(opacity=0.040 + 0.028 * s)
        halo_inner.set_fill(opacity=0.028 + 0.020 * s)

        for k, d in enumerate(sparks):
            base_op = 0.03 + 0.04 * (0.5 + 0.5 * math.sin(t * 1.6 + k))
            d.set_opacity(float(np.clip(base_op + 0.22 * s, 0.02, 0.40)))

    panel.add_updater(panel_fx)

    return {
        "group": base,
        "text_group": text_group,
        "panel": panel,
        "panel_glow": panel_glow,
        "ring1": ring1,
        "ring2": ring2,
        "ring3": ring3,
        "ring4": ring4,
        "scan_strength": scan_strength,
        "log1": log1,
        "center": np.array(center),
        "radius": r,
        "neutral": neutral,
    }


# ============================================================
# COUNTER
# ============================================================
def build_counter(center: np.ndarray, accent: str) -> Dict[str, Mobject]:
    bg = RoundedRectangle(width=1.70, height=0.72, corner_radius=0.20)
    bg.set_fill("#05080B", 0.78)
    bg.set_stroke(accent, 2.2, 0.72)
    bg.move_to(center)

    glow = bg.copy().set_fill(opacity=0).set_stroke(accent, 16, 0.10)

    dot = Dot(radius=0.07, color=accent).set_opacity(0.9)
    dot.move_to(bg.get_left() + RIGHT * 0.28)

    num = safe_text("0", font="Consolas", font_size=34, color=WHITE, weight=BOLD).move_to(center + RIGHT * 0.18)

    grp = VGroup(glow, bg, dot, num)
    try:
        grp.set_z_index(430)
        glow.set_z_index(425)
        bg.set_z_index(426)
        dot.set_z_index(427)
        num.set_z_index(428)
    except Exception:
        pass

    return {"group": grp, "num": num, "glow": glow, "bg": bg, "dot": dot}


# ============================================================
# CONTAINER
# ============================================================
def build_container(center: np.ndarray, accent: str, label: str) -> Dict[str, Mobject]:
    w, h = 3.85, 2.28

    outer = RoundedRectangle(width=w, height=h, corner_radius=0.22)
    outer.set_fill("#05080B", 0.28)
    outer.set_stroke(accent, 3.3, 0.82)
    outer.move_to(center)

    glow = outer.copy().set_fill(opacity=0).set_stroke(accent, 18, 0.12)

    inner = RoundedRectangle(width=w * 0.90, height=h * 0.70, corner_radius=0.18)
    inner.set_fill("#05080B", 0.54)
    inner.set_stroke(accent, 2.0, 0.25)
    inner.move_to(center + UP * 0.03)

    brackets = VGroup()
    b = 0.35
    lw = 2.3
    op = 0.45
    corners = [
        (outer.get_left() + RIGHT * 0.18 + UP * (h / 2 - 0.18), RIGHT, DOWN),
        (outer.get_right() + LEFT * 0.18 + UP * (h / 2 - 0.18), LEFT, DOWN),
        (outer.get_left() + RIGHT * 0.18 + DOWN * (h / 2 - 0.18), RIGHT, UP),
        (outer.get_right() + LEFT * 0.18 + DOWN * (h / 2 - 0.18), LEFT, UP),
    ]
    for p, dir1, dir2 in corners:
        l1 = Line(p, p + dir1 * b).set_stroke(accent, lw, op)
        l2 = Line(p, p + dir2 * b).set_stroke(accent, lw, op)
        brackets.add(l1, l2)

    inner_lines = VGroup(
        Line(inner.get_left(), inner.get_right()).set_stroke(accent, 1.5, 0.06),
        Line(inner.get_bottom(), inner.get_top()).set_stroke(accent, 1.5, 0.05),
    )
    inner_lines[0].shift(UP * 0.18)
    inner_lines[1].shift(RIGHT * 0.15)

    tab = RoundedRectangle(width=2.05, height=0.56, corner_radius=0.18)
    tab.set_fill("#05080B", 0.90)
    tab.set_stroke(accent, 2.3, 0.82)
    tab.move_to(outer.get_top() + DOWN * 0.26)

    lbl = safe_text(label.upper(), font_size=20, color=WHITE, weight=BOLD).move_to(tab.get_center())

    grp = VGroup(glow, outer, inner, inner_lines, brackets, tab, lbl)
    try:
        grp.set_z_index(300)
        glow.set_z_index(295)
        outer.set_z_index(296)
        inner.set_z_index(297)
        inner_lines.set_z_index(298)
        brackets.set_z_index(299)
        tab.set_z_index(305)
        lbl.set_z_index(306)
    except Exception:
        pass

    return {
        "group": grp,
        "inner": inner,
        "items": [],
        "outer": outer,
        "glow": glow,
        "brackets": brackets,
        "inner_lines": inner_lines,
        "tab": tab,
        "lbl": lbl,
    }


# ============================================================
# CARD
# ============================================================
def build_card(img_path: str, accent: str, fallback_label: str) -> Group:
    plate = RoundedRectangle(width=1.85, height=1.25, corner_radius=0.18)
    plate.set_fill("#070A0C", 0.92)
    plate.set_stroke(accent, 2.6, 0.82)

    glow = plate.copy().set_fill(opacity=0).set_stroke(accent, 14, 0.10)
    shadow = plate.copy().set_fill(BLACK, 0.30).set_stroke(width=0).shift(DOWN * 0.08 + RIGHT * 0.06)

    if img_path and os.path.exists(img_path):
        im = ImageMobject(img_path)
        im.scale_to_fit_width(1.18)
    else:
        im = safe_text((fallback_label[:1] or "?").upper(), font_size=64, color=WHITE, weight=BOLD)

    im.move_to(plate.get_center())

    grp = Group(shadow, glow, plate, im)
    try:
        grp.set_z_index(380)
        glow.set_z_index(376)
        plate.set_z_index(377)
        im.set_z_index(378)
    except Exception:
        pass
    return grp


# ============================================================
# PACKING
# ============================================================
def pack_positions(inner_rect: Mobject, n: int, cols: int = 3) -> List[np.ndarray]:
    if n <= 0:
        return []
    rows = int(math.ceil(n / cols))

    left = inner_rect.get_left()[0]
    right = inner_rect.get_right()[0]
    top = inner_rect.get_top()[1]
    bottom = inner_rect.get_bottom()[1]

    pad_x = 0.18
    pad_y = 0.16
    W = (right - left) - 2 * pad_x
    H = (top - bottom) - 2 * pad_y

    cell_w = W / cols
    cell_h = H / max(1, rows)

    pos = []
    for i in range(n):
        r = i // cols
        c = i % cols
        x = (left + pad_x) + (c + 0.5) * cell_w
        y = (top - pad_y) - (r + 0.5) * cell_h
        pos.append(np.array([x, y, 0]))
    return pos


# ============================================================
# MAIN SCENE
# ============================================================
class SortCardTribunalFinal(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR

        # Intro
        try:
            IntroManager.play_intro(
                self,
                brand_title="BIGDATA LEAK",
                brand_sub="SYSTEM BREACH DETECTED",
                feed_text="FEED_SORT // TRIBUNAL",
                footer_text="CONFIDENTIAL // VERIFIED",
            )
        except Exception:
            try:
                IntroManager.play_intro(self)
            except Exception:
                pass

        W = float(config.frame_width)
        H = float(config.frame_height)

        # Layers
        bg_layer = VGroup()
        hud_layer = VGroup()
        items_layer = Group()
        ui_layer = VGroup()
        try:
            bg_layer.set_z_index(1)
            hud_layer.set_z_index(200)
            items_layer.set_z_index(380)
            ui_layer.set_z_index(500)
        except Exception:
            pass
        self.add(bg_layer, hud_layer, items_layer, ui_layer)

        # Background (clean)
        bg_layer.add(build_god_background())

        # Branding border
        try:
            bb = get_branding_border().move_to(ORIGIN)
            try:
                bb.set_z_index(650)
            except Exception:
                pass
            ui_layer.add(bb)
        except Exception:
            pass

        # Data
        csv_path = os.path.join(DATA_DIR, "sort_data.csv")
        meta, df = load_csv_with_meta(csv_path)

        # Blueprint positions (locked)
        UI_DY = 0.28
        shift_vec = DOWN * UI_DY

        evidence_center = (np.array([0.0, H / 2 - 3.45, 0]) + shift_vec)
        scanner_center = (np.array([0.0, 0.30, 0]) + shift_vec)

        counters_y = float(scanner_center[1] - 2.35)
        left_counter_pos = np.array([-W / 2 + 1.55, counters_y, 0])
        right_counter_pos = np.array([W / 2 - 1.55, counters_y, 0])

        bins_y = -H / 2 + 2.05
        left_bin_pos = np.array([-2.25, bins_y, 0])
        right_bin_pos = np.array([2.25, bins_y, 0])

        # Build UI blocks
        header = build_header(meta.get("TITLE", "TIER 1 vs TIER 2"), meta.get("SUB", "AI TRIBUNAL SORT TEST"))
        title = header["title"]
        sub = header["sub"]
        underline = header["underline"]
        dot = header["dot"]

        evidence = build_evidence_box(evidence_center)
        scanner = build_scanner(scanner_center)
        left_counter = build_counter(left_counter_pos, Theme.NEON_BLUE)
        right_counter = build_counter(right_counter_pos, Theme.NEON_PINK)
        left_bin = build_container(left_bin_pos, Theme.NEON_BLUE, "Tier 1")
        right_bin = build_container(right_bin_pos, Theme.NEON_PINK, "Tier 2")

        # Connector lines (subtle baseline)
        line_ev = Line(evidence_center + DOWN * 0.05, scanner_center + UP * 1.55).set_stroke(Theme.NEON_BLUE, 2.2, 0.10)
        line_lc = Line(scanner_center + LEFT * 1.25 + DOWN * 1.45, left_counter_pos + RIGHT * 0.65).set_stroke(Theme.NEON_BLUE, 2.0, 0.10)
        line_rc = Line(scanner_center + RIGHT * 1.25 + DOWN * 1.45, right_counter_pos + LEFT * 0.65).set_stroke(Theme.NEON_PINK, 2.0, 0.10)
        line_lb = Line(left_counter_pos + DOWN * 0.45, left_bin_pos + UP * 1.10).set_stroke(Theme.NEON_BLUE, 2.0, 0.10)
        line_rb = Line(right_counter_pos + DOWN * 0.45, right_bin_pos + UP * 1.10).set_stroke(Theme.NEON_PINK, 2.0, 0.10)
        for ln in [line_ev, line_lc, line_rc, line_lb, line_rb]:
            try:
                ln.set_z_index(240)
            except Exception:
                pass

        # Dynamic evidence->scanner glow link (only this one as dynamic)
        ev_to_sc = Line(evidence_center + DOWN * 0.05, scanner_center + UP * 1.55)
        ev_to_sc.set_stroke(scanner["neutral"], 3.0, 0.0)
        try:
            ev_to_sc.set_z_index(360)
        except Exception:
            pass

        # Add layers
        ui_layer.add(title, sub, underline, dot, scanner["text_group"], left_counter["group"], right_counter["group"])
        hud_layer.add(
            evidence["group"], scanner["group"],
            left_bin["group"], right_bin["group"],
            line_ev, line_lc, line_rc, line_lb, line_rb,
            ev_to_sc
        )

        # =====================================================
        # PERFECT ENTRANCE (vs fixed)
        # =====================================================
        tL, tVS, tR = title[0], title[1], title[2]
        tL_final = tL.get_center()
        tR_final = tR.get_center()

        tL.shift(LEFT * 3.0)
        tR.shift(RIGHT * 3.0)

        tVS.scale(0.72)
        tVS.set_opacity(0.0)

        sub.save_state()
        underline.save_state()
        dot.save_state()
        sub.set_opacity(0.0)
        underline.set_opacity(0.0)
        dot.set_opacity(0.0)

        evidence["group"].save_state()
        evidence["group"].set_opacity(0.0)

        scanner["group"].save_state()
        scanner["text_group"].save_state()
        scanner["group"].set_opacity(0.0)
        scanner["text_group"].set_opacity(0.0)

        left_counter["group"].save_state()
        right_counter["group"].save_state()
        left_counter["group"].set_opacity(0.0)
        right_counter["group"].set_opacity(0.0)

        left_bin["group"].save_state()
        right_bin["group"].save_state()
        left_bin["group"].shift(DOWN * 1.15).set_opacity(0.0)
        right_bin["group"].shift(DOWN * 1.15).set_opacity(0.0)

        for ln in [line_ev, line_lc, line_rc, line_lb, line_rb]:
            ln.save_state()
            ln.set_opacity(0.0)

        scan_line = Rectangle(width=float(scanner["radius"]) * 3.4, height=0.10)
        scan_line.set_fill(scanner["neutral"], 0.14)
        scan_line.set_stroke(width=0)
        scan_line.rotate(-18 * DEGREES)
        scan_line.move_to(scanner_center + UP * (float(scanner["radius"]) * 1.65))
        try:
            scan_line.set_z_index(600)
        except Exception:
            pass
        hud_layer.add(scan_line)
        scan_line.set_opacity(0.0)

        self.play(
            LaggedStart(
                AnimationGroup(
                    tL.animate.move_to(tL_final),
                    tR.animate.move_to(tR_final),
                    tVS.animate.set_opacity(1.0).scale(1 / 0.72),
                    run_time=0.52,
                    rate_func=rf.ease_out_cubic,
                ),
                AnimationGroup(Restore(evidence["group"]), run_time=0.46, rate_func=rf.ease_out_cubic),
                AnimationGroup(
                    Restore(scanner["group"]),
                    Restore(scanner["text_group"]),
                    FadeIn(scan_line),
                    scan_line.animate.move_to(scanner_center + DOWN * (float(scanner["radius"]) * 1.65)),
                    FadeOut(scan_line),
                    run_time=0.56,
                    rate_func=rf.ease_in_out_sine,
                ),
                AnimationGroup(Restore(sub), run_time=0.22, rate_func=rf.ease_out_cubic),
                AnimationGroup(Restore(underline), Restore(dot), run_time=0.24, rate_func=rf.ease_out_cubic),
                AnimationGroup(
                    Restore(line_ev),
                    Restore(line_lc),
                    Restore(line_rc),
                    Restore(line_lb),
                    Restore(line_rb),
                    run_time=0.28,
                    rate_func=rf.ease_out_cubic,
                ),
                AnimationGroup(Restore(left_counter["group"]), Restore(right_counter["group"]), run_time=0.26, rate_func=rf.ease_out_cubic),
                AnimationGroup(Restore(left_bin["group"]), Restore(right_bin["group"]), run_time=0.42, rate_func=rf.ease_out_cubic),
                lag_ratio=0.06,
            ),
            run_time=1.05,
        )

        self.play(
            MoveAlongPath(dot, Line(underline.get_left(), underline.get_right())),
            run_time=0.38,
            rate_func=rf.ease_in_out_sine,
        )

        # Save baseline states for route glow restore
        line_lc.save_state()
        line_lb.save_state()
        line_rc.save_state()
        line_rb.save_state()

        # =====================================================
        # ALWAYS-ON SCANNER (IMPORTANT)
        # =====================================================
        BASE_STRENGTH = 0.72   # stays ON forever (no fade-out)
        SPIKE_STRENGTH = 1.00  # quick spike during scan-start
        scanner["scan_strength"].set_value(BASE_STRENGTH)

        # =====================================================
        # STATE + HELPERS
        # =====================================================
        c1, c2 = 0, 0

        def set_log(mobj: Mobject, text: str, color=Theme.TEXT_SUB):
            new = safe_text(text, font="Consolas", font_size=11, color=color, weight=BOLD).move_to(mobj.get_center())
            mobj.become(new)

        def counter_pop(counter: Dict[str, Mobject], value: int, accent: str):
            old = counter["num"]
            new = safe_text(str(value), font="Consolas", font_size=34, color=WHITE, weight=BOLD).move_to(old.get_center())
            self.play(
                Transform(old, new),
                counter["glow"].animate.set_stroke(accent, 18, 0.18),
                counter["bg"].animate.set_stroke(accent, 2.6, 0.85),
                run_time=0.18,
                rate_func=rf.ease_out_cubic,
            )
            self.play(counter["group"].animate.scale(1.06), run_time=0.10, rate_func=rf.ease_out_cubic)
            self.play(
                counter["group"].animate.scale(1 / 1.06),
                counter["glow"].animate.set_stroke(accent, 16, 0.10),
                counter["bg"].animate.set_stroke(accent, 2.2, 0.72),
                run_time=0.14,
                rate_func=rf.ease_in_out_sine,
            )

        def repack(bin_ref: Dict[str, Mobject]):
            items = bin_ref["items"]
            inner = bin_ref["inner"]
            n = len(items)
            if n <= 0:
                return
            cols = 3
            pos = pack_positions(inner, n, cols=cols)
            target_w = float(inner.width / (cols + 0.70))

            anims = []
            for i, card in enumerate(items):
                cw = float(card.width) if float(card.width) > 1e-6 else 1.0
                factor = max(0.55, min(1.25, target_w / cw))
                anims.append(card.animate.move_to(pos[i]).scale(factor))
            self.play(LaggedStart(*anims, lag_ratio=0.03), run_time=0.35, rate_func=rf.ease_out_cubic)

        def glow_route(is_left: bool):
            if is_left:
                return [
                    line_lc.animate.set_stroke(Theme.NEON_BLUE, 3.2, 0.55),
                    line_lb.animate.set_stroke(Theme.NEON_BLUE, 3.2, 0.55),
                ]
            return [
                line_rc.animate.set_stroke(Theme.NEON_PINK, 3.2, 0.55),
                line_rb.animate.set_stroke(Theme.NEON_PINK, 3.2, 0.55),
            ]

        def restore_route(is_left: bool):
            if is_left:
                return [Restore(line_lc), Restore(line_lb)]
            return [Restore(line_rc), Restore(line_rb)]

        # Entry point + holds
        entry = np.array([W / 2 + 1.8, evidence_center[1] + 0.10, 0])
        evidence_hold = evidence["inner"].get_center()

        # Short, readable logs only (big logs intentionally avoided)
        scan_log_pool = [
            "hashing evidence…",
            "syncing tribunal cores…",
            "decrypting vibes…",
            "checking plot armor…",
            "running sarcasm check…",
            "validating inputs…",
            "mapping to tier grid…",
            "building verdict packet…",
            "cross-checking signals…",
            "verifying consistency…",
            "indexing proof…",
            "locking decision path…",
            "sanity-check complete…",
            "scanning noise floor…",
        ]

        def pick_short_log(max_len: int = 34) -> str:
            # Prefer short logs; ignore long logs.
            for _ in range(16):
                s = random.choice(scan_log_pool).strip()
                s2 = f">> {s}"
                if len(s2) <= max_len:
                    return s2
            # Worst case, ellipsize (still safe)
            return f">> {ellipsize(random.choice(scan_log_pool).strip(), max_len - 3)}"

        # Timing: fixed 6s from card appear -> card reaches bin top
        TOTAL_CARD_TIME = 6.0

        # =====================================================
        # SORT LOOP
        # =====================================================
        for _, row in df.iterrows():
            t_card_start = self.renderer.time  # manim internal time

            img_name = str(row.get("Image", "")).strip()
            reason = str(row.get("Reason", "UNKNOWN")).strip()
            try:
                cat = int(row.get("Category", 2))
            except Exception:
                cat = 2

            is_left = (cat == 1)
            accent = Theme.NEON_BLUE if is_left else Theme.NEON_PINK
            bin_ref = left_bin if is_left else right_bin

            img_path = os.path.join(ASSETS_DIR, "images", img_name)
            fallback_label = img_name.split(".")[0] if img_name else "X"

            # Create card
            card = build_card(img_path, accent, fallback_label)
            card.move_to(entry).rotate(6 * DEGREES)
            items_layer.add(card)
            self.play(FadeIn(card, shift=LEFT * 0.35), run_time=0.22, rate_func=rf.ease_out_cubic)

            # Slide into evidence
            self.play(
                card.animate.rotate(-6 * DEGREES).move_to(evidence_hold),
                run_time=0.45,
                rate_func=rf.ease_out_cubic,
            )

            # Reason pill
            pill_w = min(W * 0.72, 5.4)
            pill_bg = RoundedRectangle(width=pill_w, height=0.74, corner_radius=0.18)
            pill_bg.set_fill("#05080B", 0.88)
            pill_bg.set_stroke(accent, 2.3, 0.75)
            pill_bg.move_to(evidence["outer"].get_top() + UP * 0.62)

            pill_t = safe_text("REASON", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD)
            pill_m = safe_text(ellipsize(reason.upper(), 30), font_size=22, color=accent, weight=BOLD)
            pill_txt = VGroup(pill_t, pill_m).arrange(DOWN, buff=0.06).move_to(pill_bg.get_center())
            pill = VGroup(pill_bg, pill_txt)
            try:
                pill.set_z_index(620)
            except Exception:
                pass
            ui_layer.add(pill)
            self.play(DrawBorderThenFill(pill_bg), Write(pill_txt), run_time=0.22, rate_func=rf.ease_out_cubic)

            # -----------------------------
            # SCAN START (scanner never turns off)
            # -----------------------------
            set_log(scanner["log1"], pick_short_log(), color=Theme.TEXT_SUB)

            ev_to_sc.set_stroke(scanner["neutral"], 3.0, 0.0)
            self.play(
                ev_to_sc.animate.set_opacity(0.65),
                evidence["glow"].animate.set_stroke(scanner["neutral"], 18, 0.16),
                scanner["panel_glow"].animate.set_stroke(scanner["neutral"], 12, 0.14),
                scanner["scan_strength"].animate.set_value(SPIKE_STRENGTH),
                run_time=0.22,
                rate_func=rf.ease_out_cubic,
            )
            self.play(
                scanner["scan_strength"].animate.set_value(BASE_STRENGTH),
                run_time=0.16,
                rate_func=rf.ease_in_out_sine,
            )

            # -----------------------------
            # SCAN DWELL (readable log rotation for ~3.4s)
            # -----------------------------
            dwell_total = 3.4
            hold = 0.95  # readable
            n_steps = max(1, int(dwell_total / hold))

            for i in range(n_steps):
                set_log(scanner["log1"], pick_short_log(), color=Theme.TEXT_SUB)
                # tiny "text refresh" motion (very subtle, no flicker)
                self.wait(hold)

            # Hide pill (scan continues; no decision flash)
            self.play(
                FadeOut(pill, shift=UP * 0.06),
                run_time=0.16,
                rate_func=rf.ease_in_cubic,
            )
            ui_layer.remove(pill)

            # -----------------------------
            # ROUTE MOMENT (only lines show destination)
            # -----------------------------
            # boost the correct route lines (scanner->counter and counter->bin)
            self.play(*glow_route(is_left), run_time=0.18, rate_func=rf.ease_out_cubic)

            # optionally update log line to “routing…” (still neutral)
            set_log(scanner["log1"], ">> routing packet…", color=Theme.TEXT_SUB)

            # Move to container
            inner = bin_ref["inner"]
            to_top = inner.get_top() + DOWN * 0.20
            bend = (evidence_hold + to_top) / 2 + DOWN * 0.60 + (LEFT if is_left else RIGHT) * 0.75
            path_move = CubicBezier(evidence_hold, bend, bend, to_top).set_stroke(width=0, opacity=0)

            self.play(
                MoveAlongPath(card, path_move),
                card.animate.scale(0.80),
                run_time=1.05,
                rate_func=rf.ease_in_out_sine,
            )

            # restore baseline route lines + end scan link
            self.play(
                *restore_route(is_left),
                ev_to_sc.animate.set_opacity(0.0),
                evidence["glow"].animate.set_stroke(Theme.NEON_BLUE, 16, 0.10),
                scanner["panel_glow"].animate.set_stroke(scanner["neutral"], 12, 0.08),
                run_time=0.22,
                rate_func=rf.ease_in_out_sine,
            )

            # Place into bin and pack
            bin_ref["items"].append(card)
            repack(bin_ref)

            # Counters
            if is_left:
                c1 += 1
                counter_pop(left_counter, c1, Theme.NEON_BLUE)
            else:
                c2 += 1
                counter_pop(right_counter, c2, Theme.NEON_PINK)

            # --- HARD guarantee: keep total time per card approx 6s
            # If some machines render slightly faster, we pad with wait.
            t_now = self.renderer.time
            elapsed = float(t_now - t_card_start)
            pad = TOTAL_CARD_TIME - elapsed
            if pad > 0.01:
                self.wait(pad)

        self.wait(2.0)
