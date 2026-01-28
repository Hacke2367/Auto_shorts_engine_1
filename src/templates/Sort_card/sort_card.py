# sort_card_tribunal_final.py
# FINAL "SORT CARD TRIBUNAL" — GOD-TIER PREMIUM (robust + no random NameError)
# Manim Community v0.19.x
#
# Run:
#   manim -pqh sort_card_tribunal_final.py SortCardTribunalFinal --disable_caching
#
# CSV (first line meta):
#   # TITLE=TIER 1 vs TIER 2, SUB=AI TRIBUNAL SORT TEST, FEED=FEED_SORT // TRIBUNAL
#   Image,Category,Reason

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

# -------------------------
# PATH SETUP
# -------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

# project imports (utils.py is LOCKED)
from src.config import DATA_DIR, ASSETS_DIR, BACKGROUND_COLOR, Theme
from src.utils import IntroManager, get_safe_frame, make_floating_particles

# -------------------------
# DATA
# -------------------------
_META_RE = re.compile(r"([A-Za-z_]+)\s*=\s*([^,]+)")


def _safe_text(s: str, font="Montserrat", font_size=24, color=WHITE, weight=None) -> Text:
    try:
        if weight is None:
            return Text(str(s), font=font, font_size=font_size, color=color)
        return Text(str(s), font=font, font_size=font_size, color=color, weight=weight)
    except Exception:
        return Text(str(s), font_size=font_size, color=color)


def ellipsize(s: str, n: int = 18) -> str:
    s = str(s)
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def load_csv_with_meta(csv_path: str) -> Tuple[Dict[str, str], pd.DataFrame]:
    meta = {"TITLE": "TIER 1 vs TIER 2", "SUB": "AI TRIBUNAL SORT TEST", "FEED": "FEED_SORT // TRIBUNAL"}
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
    df = df.head(10).reset_index(drop=True)  # max 10
    return meta, df


# -------------------------
# FIT HELPERS
# -------------------------
def fit_mobject_to_box(m: Mobject, max_w: float, max_h: float):
    try:
        w = float(m.width)
        h = float(m.height)
        if w <= 1e-6 or h <= 1e-6:
            return
        s = min(max_w / w, max_h / h)
        if s < 0.999 or s > 1.001:
            m.scale(s)
    except Exception:
        pass


# -------------------------
# PREMIUM PANEL STYLE HELPERS
# -------------------------
def _apply_sheen(m: VMobject, sheen: float = 0.25):
    # Safe: if method not available, ignore
    try:
        m.set_sheen_factor(sheen)
        m.set_sheen_direction(RIGHT + UP)
    except Exception:
        pass


def premium_box_layers(base_rect: RoundedRectangle, accent: str, fill_hex="#05070B", fill_op=0.52):
    """
    Returns (glow, main, glass, highlight_strip) as separate mobjects.
    Keeps it robust: all are plain VMobjects, no gradients required.
    """
    # Glow outline
    glow = base_rect.copy()
    glow.set_fill(opacity=0)
    glow.set_stroke(color=accent, width=16, opacity=0.09)

    # Main outline
    main = base_rect.copy()
    main.set_fill(color=fill_hex, opacity=fill_op)
    main.set_stroke(color=accent, width=2.6, opacity=0.62)
    _apply_sheen(main, 0.22)

    # Inner glass panel
    glass = base_rect.copy()
    glass.scale(0.88)
    glass.set_fill(color=BLACK, opacity=0.18)
    glass.set_stroke(color=WHITE, width=1.2, opacity=0.08)
    _apply_sheen(glass, 0.18)

    # Highlight strip (fake gradient hint)
    strip = RoundedRectangle(
        width=main.width * 0.86,
        height=max(0.10, main.height * 0.08),
        corner_radius=0.10,
    )
    strip.set_fill(color=accent, opacity=0.10)
    strip.set_stroke(width=0)
    strip.move_to(main.get_top() + DOWN * (strip.height * 0.7))
    strip.set_z_index(main.z_index + 1 if hasattr(main, "z_index") else 0)

    # Align
    glass.move_to(main.get_center())
    glow.move_to(main.get_center())

    return glow, main, glass, strip


# -------------------------
# BACKGROUND (god-tier alive but subtle)
# -------------------------
def build_background(sf) -> VGroup:
    bg = VGroup().set_z_index(1)

    # base wash
    base = Rectangle(width=sf["w"] + 2.5, height=sf["h"] + 2.5)
    base.set_fill(color="#05070B", opacity=1.0)
    base.set_stroke(width=0)
    base.move_to([sf["cx"], sf["cy"], 0]).set_z_index(0)
    bg.add(base)

    # subtle grid
    grid = VGroup().set_z_index(1)
    step = 0.85
    x = sf["left"]
    while x <= sf["right"] + 1e-6:
        ln = Line([x, sf["bottom"], 0], [x, sf["top"], 0])
        ln.set_stroke(color=Theme.NEON_BLUE, width=1, opacity=0.018)
        grid.add(ln)
        x += step

    y = sf["bottom"]
    while y <= sf["top"] + 1e-6:
        ln = Line([sf["left"], y, 0], [sf["right"], y, 0])
        ln.set_stroke(color=Theme.NEON_BLUE, width=1, opacity=0.014)
        grid.add(ln)
        y += step

    # vignette edges (cinematic)
    vignette = VGroup(
        Rectangle(width=sf["w"] + 2.4, height=1.7)
        .set_fill(color=BLACK, opacity=0.24)
        .set_stroke(width=0)
        .move_to([sf["cx"], sf["top"] + 0.55, 0]),
        Rectangle(width=sf["w"] + 2.4, height=1.7)
        .set_fill(color=BLACK, opacity=0.24)
        .set_stroke(width=0)
        .move_to([sf["cx"], sf["bottom"] - 0.55, 0]),
        Rectangle(width=2.0, height=sf["h"] + 2.4)
        .set_fill(color=BLACK, opacity=0.22)
        .set_stroke(width=0)
        .move_to([sf["left"] - 0.60, sf["cy"], 0]),
        Rectangle(width=2.0, height=sf["h"] + 2.4)
        .set_fill(color=BLACK, opacity=0.22)
        .set_stroke(width=0)
        .move_to([sf["right"] + 0.60, sf["cy"], 0]),
    ).set_z_index(3)

    # soft diagonal beams
    beams = VGroup().set_z_index(0)
    for ang, op, yoff in [(-12, 0.016, -0.25), (-12, 0.012, -0.75), (-12, 0.010, 0.35)]:
        b = Rectangle(width=sf["w"] * 0.98, height=sf["h"] * 0.22)
        b.set_fill(color=Theme.NEON_BLUE, opacity=op)
        b.set_stroke(width=0)
        b.rotate(ang * DEGREES)
        b.move_to([sf["cx"], sf["cy"] + yoff, 0])
        beams.add(b)

    # soft radial glows
    glow1 = Circle(radius=3.25).set_fill(Theme.NEON_BLUE, 0.030).set_stroke(width=0).set_z_index(0)
    glow1.move_to([sf["cx"], sf["cy"] - 0.3, 0])

    glow2 = Circle(radius=2.70).set_fill(Theme.NEON_PINK, 0.018).set_stroke(width=0).set_z_index(0)
    glow2.move_to([sf["cx"], sf["cy"] - 0.9, 0])

    bg.add(beams, glow1, glow2, grid, vignette)
    return bg


# -------------------------
# HEADER (comparison vibe)
# -------------------------
def build_header(sf, title_text: str, sub_text: str) -> Dict[str, Mobject]:
    left = _safe_text("TIER 1", font_size=46, color=WHITE, weight=BOLD)
    right = _safe_text("TIER 2", font_size=46, color=WHITE, weight=BOLD)
    vs = _safe_text("vs", font_size=30, color=GREY_B, weight=BOLD)

    try:
        left.set_stroke(Theme.NEON_BLUE, width=2.0, opacity=0.72)
        right.set_stroke(Theme.NEON_PINK, width=2.0, opacity=0.72)
    except Exception:
        pass

    title = VGroup(left, vs, right).arrange(RIGHT, buff=0.24).set_z_index(220)
    title.move_to([sf["cx"], sf["top"] - 1.05, 0])

    sub = _safe_text(sub_text, font_size=18, color=Theme.TEXT_SUB, weight=BOLD).set_z_index(220)
    sub.next_to(title, DOWN, buff=0.12)

    line_w = min(sf["w"] * 0.82, title.width + 1.0)
    uL = Line(LEFT * line_w / 2, ORIGIN).set_stroke(color=Theme.NEON_BLUE, width=4, opacity=0.70)
    uR = Line(ORIGIN, RIGHT * line_w / 2).set_stroke(color=Theme.NEON_PINK, width=4, opacity=0.70)
    underline = VGroup(uL, uR).arrange(RIGHT, buff=0).next_to(sub, DOWN, buff=0.16).set_z_index(220)

    return {"title": title, "sub": sub, "underline": underline}


# -------------------------
# EVIDENCE BOX (premium, no harsh flash)
# -------------------------
def build_evidence_box(center: np.ndarray, accent=Theme.NEON_BLUE) -> Dict[str, Mobject]:
    w, h = 3.20, 1.70
    base = RoundedRectangle(width=w, height=h, corner_radius=0.22)

    glow, outer, inner, hi = premium_box_layers(base, accent, fill_hex="#05070B", fill_op=0.60)
    # inner returned by premium_box_layers is a scaled copy of base (glass). We'll use it as "inner"
    inner.set_fill(color=BLACK, opacity=0.16)
    inner.set_stroke(color=WHITE, width=1.2, opacity=0.07)

    # bottom micro label
    label = _safe_text("EVIDENCE INTAKE", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD)
    label.set_opacity(0.82)
    label.move_to(outer.get_bottom() + UP * 0.22)

    grp = VGroup(glow, outer, inner, hi, label).move_to(center).set_z_index(140)

    return {"group": grp, "outer": outer, "inner": inner, "glow": glow, "hi": hi, "label": label, "accent": accent}


# -------------------------
# SCANNER (old design back, more alive, halo fixed)
# -------------------------
def build_scanner(center: np.ndarray, radius: float = 1.15, accent=Theme.NEON_BLUE) -> Dict[str, Mobject]:
    # halo just slightly bigger than scanner (NOT huge)
    halo = Circle(radius=radius * 1.10).set_fill(accent, 0.035).set_stroke(width=0)
    _apply_sheen(halo, 0.10)

    ring1 = Circle(radius=radius * 1.00).set_stroke(color=Theme.TEXT_SUB, width=2, opacity=0.14).set_fill(opacity=0)
    ring2 = Circle(radius=radius * 1.18).set_stroke(color=Theme.TEXT_SUB, width=2, opacity=0.11).set_fill(opacity=0)
    ring3 = Circle(radius=radius * 1.36).set_stroke(color=Theme.TEXT_SUB, width=2, opacity=0.09).set_fill(opacity=0)

    dash_base = Circle(radius=radius * 1.48).set_stroke(color=accent, width=2.6, opacity=0.34).set_fill(opacity=0)
    dash_ring = DashedVMobject(dash_base, num_dashes=22).set_z_index(1)

    ticks = VGroup()
    tick_r = radius * 1.52
    for ang in np.linspace(0, TAU, 44, endpoint=False):
        p1 = np.array([math.cos(ang) * (tick_r - 0.10), math.sin(ang) * (tick_r - 0.10), 0])
        p2 = np.array([math.cos(ang) * tick_r, math.sin(ang) * tick_r, 0])
        ln = Line(p1, p2).set_stroke(color=Theme.TEXT_SUB, width=2, opacity=0.08)
        ticks.add(ln)

    core = RegularPolygon(n=6, radius=radius * 0.62)
    core.set_fill(color="#05070B", opacity=0.92)
    core.set_stroke(color=accent, width=2.6, opacity=0.34)
    _apply_sheen(core, 0.22)

    glass = Circle(radius=radius * 0.52).set_fill(color=WHITE, opacity=0.012).set_stroke(color=WHITE, width=2, opacity=0.05)

    chevs = VGroup()
    for sx, sy in [(-1, 1), (1, 1), (-1, -1), (1, -1)]:
        a = np.array([sx * radius * 0.78, sy * radius * 0.78, 0])
        b = np.array([sx * radius * 0.92, sy * radius * 0.78, 0])
        c = np.array([sx * radius * 0.78, sy * radius * 0.92, 0])
        ch1 = Line(a, b).set_stroke(color=accent, width=3, opacity=0.22)
        ch2 = Line(a, c).set_stroke(color=accent, width=3, opacity=0.22)
        chevs.add(ch1, ch2)

    grp = VGroup(halo, ring1, ring2, ring3, dash_ring, ticks, core, glass, chevs).move_to(center).set_z_index(120)

    # center text ALWAYS visible (NO extra line/plate)
    top = _safe_text("AI TRIBUNAL", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD).set_opacity(0.90)
    mid = _safe_text("SCAN CORE", font_size=18, color=WHITE, weight=BOLD)
    bot = _safe_text("ready", font="Consolas", font_size=11, color=Theme.TEXT_SUB)
    label = VGroup(top, mid, bot).arrange(DOWN, buff=0.06).move_to(center + DOWN * 0.02).set_z_index(230)

    return {
        "group": grp,
        "halo": halo,
        "rings": VGroup(ring1, ring2, ring3),
        "dash": dash_ring,
        "ticks": ticks,
        "core": core,
        "label": label,
        "center": center,
        "radius": radius,
        "accent": accent,
    }


def scanner_set_accent(scanner: Dict[str, Mobject], accent: str):
    scanner["accent"] = accent
    scanner["dash"].set_stroke(color=accent, opacity=0.38)
    scanner["core"].set_stroke(color=accent, opacity=0.38)
    scanner["halo"].set_fill(color=accent, opacity=0.035)


# -------------------------
# COUNTERS (premium, no harsh colors)
# -------------------------
def build_border_counter(pos: np.ndarray, accent: str) -> Dict[str, Mobject]:
    base = RoundedRectangle(width=0.92, height=0.60, corner_radius=0.18)
    glow, outer, glass, strip = premium_box_layers(base, accent, fill_hex="#05070B", fill_op=0.55)

    txt = _safe_text("0", font="Consolas", font_size=28, color=WHITE, weight=BOLD)
    txt.move_to(outer.get_center())

    grp = VGroup(glow, outer, glass, strip, txt).move_to(pos).set_z_index(240)
    return {"group": grp, "outer": outer, "glass": glass, "txt": txt, "accent": accent, "value": 0}


# -------------------------
# CARDS (Group, safe for ImageMobject)
# -------------------------
def build_sprite(img_path: str, accent: str) -> Group:
    if img_path and os.path.exists(img_path):
        im = ImageMobject(img_path)
        im.set_z_index(3)
    else:
        im = _safe_text("?", font_size=72, color=WHITE, weight=BOLD)

    aura = Circle(radius=0.55)
    aura.set_fill(color=accent, opacity=0.09)
    aura.set_stroke(color=accent, width=10, opacity=0.10)
    aura.set_z_index(2)

    core_glow = Circle(radius=0.42)
    core_glow.set_fill(color=accent, opacity=0.05)
    core_glow.set_stroke(width=0)
    core_glow.set_z_index(2)

    g = Group(aura, core_glow, im)
    g.set_z_index(160)
    g.move_to(ORIGIN)
    return g


# -------------------------
# CONTAINERS (Vault Bay, premium)
# -------------------------
def build_vault_bay(center: np.ndarray, accent: str, label: str) -> Dict[str, Mobject]:
    w, h = 3.55, 2.55
    base = RoundedRectangle(width=w, height=h, corner_radius=0.26)

    glow, body, inner_glass, strip = premium_box_layers(base, accent, fill_hex="#05070B", fill_op=0.40)

    # inner area where items pack
    inner = RoundedRectangle(width=w * 0.86, height=h * 0.70, corner_radius=0.20)
    inner.set_fill(color=BLACK, opacity=0.20)
    inner.set_stroke(color=WHITE, width=1.2, opacity=0.07)
    inner.move_to(body.get_center() + UP * 0.08)
    _apply_sheen(inner, 0.18)

    mouth = RoundedRectangle(width=w * 0.62, height=0.18, corner_radius=0.09)
    mouth.set_fill(color=accent, opacity=0.08)
    mouth.set_stroke(color=accent, width=1.8, opacity=0.26)
    mouth.move_to(body.get_top() + DOWN * 0.22)

    locks = VGroup()
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = body.get_center() + np.array([sx * (w / 2 - 0.35), sy * (h / 2 - 0.35), 0])
            r = RoundedRectangle(width=0.40, height=0.28, corner_radius=0.10)
            r.set_fill(color=accent, opacity=0.06)
            r.set_stroke(color=accent, width=2.0, opacity=0.18)
            r.move_to(p)
            locks.add(r)

    chevs = VGroup()
    for dy, op in [(0.22, 0.07), (-0.10, 0.05), (-0.42, 0.07)]:
        ln = Line(inner.get_left() + RIGHT * 0.18, inner.get_right() + LEFT * 0.18)
        ln.move_to(inner.get_center() + UP * dy)
        ln.set_stroke(color=accent, width=2.5, opacity=op)
        chevs.add(ln)

    lbl = _safe_text(label.upper(), font_size=20, color=WHITE, weight=BOLD).set_z_index(230)
    lbl.move_to(center + DOWN * (h / 2 + 0.55))

    back = VGroup(glow, body, inner, strip, mouth, locks, chevs).move_to(center).set_z_index(90)

    return {"group": back, "body": body, "inner": inner, "mouth": mouth, "label": lbl, "accent": accent, "items": []}


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


# -------------------------
# MAIN SCENE
# -------------------------
class SortCardTribunalFinal(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        sf = get_safe_frame(margin=0.70)

        # Data
        csv_path = os.path.join(DATA_DIR, "sort_data.csv")
        meta, df = load_csv_with_meta(csv_path)

        # Intro (LOCKED)
        try:
            IntroManager.play_intro(
                self,
                brand_title="BIGDATA LEAK",
                brand_sub="SYSTEM BREACH DETECTED",
                feed_text=str(meta.get("FEED", "FEED_SORT // TRIBUNAL")),
                footer_text="CONFIDENTIAL // VERIFIED",
            )
        except Exception:
            IntroManager.play_intro(self)

        # Layers
        bg_layer = VGroup().set_z_index(1)
        mid_layer = VGroup().set_z_index(150)
        ui_layer = VGroup().set_z_index(240)

        containers_layer = Group().set_z_index(110)
        items_layer = Group().set_z_index(160)

        self.add(bg_layer, containers_layer, mid_layer, items_layer, ui_layer)

        # Background
        bg = build_background(sf)
        bg_layer.add(bg)

        # Alive scanlines (subtle, safe)
        t = ValueTracker(0.0)
        t.add_updater(lambda m, dt: m.increment_value(dt))

        scanline = always_redraw(
            lambda: Rectangle(width=sf["w"] + 2.0, height=0.12)
            .set_fill(color=Theme.NEON_BLUE, opacity=0.018)
            .set_stroke(width=0)
            .move_to([sf["cx"], sf["bottom"] + (t.get_value() * 0.9) % (sf["h"] + 1.4), 0])
            .set_z_index(2)
        )
        bg_layer.add(scanline)
        self.add(t)  # ensure updater runs

        try:
            bg_layer.add(
                make_floating_particles(
                    n=14,
                    color=Theme.NEON_BLUE,
                    radius_range=(0.018, 0.042),
                    opacity_range=(0.05, 0.14),
                    drift=0.028,
                    margin=0.75,
                )
            )
        except Exception:
            pass

        # Header
        header = build_header(sf, meta.get("TITLE", "TIER 1 vs TIER 2"), meta.get("SUB", "AI TRIBUNAL SORT TEST"))
        title = header["title"]
        sub = header["sub"]
        underline = header["underline"]

        # Layout anchors
        header_bottom_y = underline.get_bottom()[1]
        evidence_center = np.array([sf["cx"], header_bottom_y - 1.85, 0])
        scanner_center = np.array([sf["cx"], evidence_center[1] - 2.85, 0])

        containers_y = sf["bottom"] + 2.55
        left_bin_center = np.array([sf["cx"] - 2.25, containers_y, 0])
        right_bin_center = np.array([sf["cx"] + 2.25, containers_y, 0])

        # Helper: invisible entry state (no flash)
        def prep_in(m: Mobject, shift_vec=ORIGIN, scale_factor: float = 1.0):
            try:
                if scale_factor != 1.0:
                    m.scale(scale_factor)
            except Exception:
                pass
            try:
                # robust shift check
                sv = np.array(shift_vec, dtype=float)
                if np.linalg.norm(sv) > 1e-6:
                    m.shift(shift_vec)
            except Exception:
                pass
            try:
                m.set_opacity(0.0)
            except Exception:
                # if a mobject doesn't support opacity well, ignore
                pass
            return m

        # Evidence
        evidence = build_evidence_box(evidence_center, accent=Theme.NEON_BLUE)
        evidence_grp = evidence["group"]

        # Scanner
        scanner = build_scanner(scanner_center, radius=1.15, accent=Theme.NEON_BLUE)
        scanner_grp = scanner["group"]
        scanner_label = scanner["label"]

        # Beam connector
        beam_alpha = ValueTracker(0.0)

        def beam_start():
            return evidence_grp.get_bottom() + DOWN * 0.14

        def beam_end():
            return scanner_grp.get_top() + UP * 0.14

        beam = always_redraw(
            lambda: VGroup(
                Line(beam_start(), beam_end()).set_stroke(
                    color=scanner["accent"], width=10, opacity=float(0.12 * beam_alpha.get_value())
                ),
                Line(beam_start(), beam_end()).set_stroke(
                    color=scanner["accent"], width=2.8, opacity=float(0.55 * beam_alpha.get_value())
                ),
            ).set_z_index(170)
        )

        # Containers
        left_bin = build_vault_bay(left_bin_center, Theme.NEON_BLUE, "Tier 1")
        right_bin = build_vault_bay(right_bin_center, Theme.NEON_PINK, "Tier 2")

        # Route lines
        routeL_alpha = ValueTracker(0.0)
        routeR_alpha = ValueTracker(0.0)

        def _route_points(is_left: bool):
            start = scanner_grp.get_bottom() + UP * 0.05 + (LEFT if is_left else RIGHT) * 0.85
            mid1 = start + DOWN * 0.85 + (LEFT if is_left else RIGHT) * 0.55
            target = (left_bin["group"] if is_left else right_bin["group"]).get_top() + DOWN * 0.18
            mid2 = np.array([mid1[0], target[1] + 0.55, 0])
            end = np.array([target[0], target[1] + 0.10, 0])
            return [start, mid1, mid2, end]

        routeL = always_redraw(
            lambda: VGroup(
                VMobject().set_points_as_corners(_route_points(True)).set_stroke(Theme.NEON_BLUE, 2.2, opacity=0.08),
                VMobject().set_points_as_corners(_route_points(True)).set_stroke(
                    Theme.NEON_BLUE, 9, opacity=0.16 * routeL_alpha.get_value()
                ),
            ).set_z_index(115)
        )

        routeR = always_redraw(
            lambda: VGroup(
                VMobject().set_points_as_corners(_route_points(False)).set_stroke(Theme.NEON_PINK, 2.2, opacity=0.08),
                VMobject().set_points_as_corners(_route_points(False)).set_stroke(
                    Theme.NEON_PINK, 9, opacity=0.16 * routeR_alpha.get_value()
                ),
            ).set_z_index(115)
        )

        # Counters
        cL = build_border_counter(np.array([sf["left"] + 0.20, sf["cy"] + 0.45, 0]), Theme.NEON_BLUE)
        cR = build_border_counter(np.array([sf["right"] - 0.20, sf["cy"] + 0.45, 0]), Theme.NEON_PINK)

        # -------------------------
        # Reason tag (ON TOP BORDER)
        # -------------------------
        reason_glow = RoundedRectangle(width=evidence["outer"].width * 0.62, height=0.32, corner_radius=0.14)
        reason_glow.set_fill(opacity=0)
        reason_glow.set_stroke(color=Theme.NEON_BLUE, width=14, opacity=0.08).set_z_index(203)

        reason_plate = RoundedRectangle(width=evidence["outer"].width * 0.62, height=0.32, corner_radius=0.14)
        reason_plate.set_fill(color="#05070B", opacity=0.78)
        reason_plate.set_stroke(color=Theme.NEON_BLUE, width=2.2, opacity=0.70).set_z_index(204)
        _apply_sheen(reason_plate, 0.18)

        reason_txt = _safe_text("", font="Consolas", font_size=15, color=WHITE, weight=BOLD).set_z_index(205)

        def place_reason_tag():
            # sits on/just above top border (premium tag)
            anchor = evidence["outer"].get_top()
            y = anchor[1] + 0.02
            x = evidence["outer"].get_center()[0]
            pos = np.array([x, y, 0])
            reason_plate.move_to(pos)
            reason_glow.move_to(pos)
            reason_txt.move_to(pos + DOWN * 0.005)

        place_reason_tag()

        # -------------------------
        # Scanner sweep (subtle, alive)
        # -------------------------
        sweep = AnnularSector(
            inner_radius=scanner["radius"] * 0.20,
            outer_radius=scanner["radius"] * 0.62,
            angle=22 * DEGREES,
            start_angle=0,
        ).set_fill(color=WHITE, opacity=0.045).set_stroke(width=0)
        sweep.move_to(scanner_center).set_z_index(125)

        # -------------------------
        # ADD everything INVISIBLE first (no flash)
        # -------------------------
        prep_in(title, shift_vec=UP * 0.15)
        prep_in(sub, shift_vec=UP * 0.10)
        prep_in(underline, shift_vec=UP * 0.08)
        ui_layer.add(title, sub, underline)

        prep_in(evidence_grp, shift_vec=UP * 0.12, scale_factor=0.985)
        prep_in(scanner_grp, scale_factor=0.97)
        prep_in(scanner_label, shift_vec=UP * 0.06)
        prep_in(sweep)
        mid_layer.add(evidence_grp, scanner_grp, beam, routeL, routeR, sweep)
        ui_layer.add(scanner_label)

        prep_in(reason_glow, shift_vec=UP * 0.05)
        prep_in(reason_plate, shift_vec=UP * 0.05)
        prep_in(reason_txt, shift_vec=UP * 0.05)
        ui_layer.add(reason_glow, reason_plate, reason_txt)

        prep_in(left_bin["group"], shift_vec=DOWN * 0.20, scale_factor=0.988)
        prep_in(right_bin["group"], shift_vec=DOWN * 0.20, scale_factor=0.988)
        prep_in(left_bin["label"], shift_vec=DOWN * 0.08)
        prep_in(right_bin["label"], shift_vec=DOWN * 0.08)
        containers_layer.add(left_bin["group"], right_bin["group"])
        ui_layer.add(left_bin["label"], right_bin["label"])

        prep_in(cL["group"], shift_vec=LEFT * 0.28)
        prep_in(cR["group"], shift_vec=RIGHT * 0.28)
        ui_layer.add(cL["group"], cR["group"])

        # -------------------------
        # ENTRANCE ANIMS (premium, not too fast)
        # -------------------------
        self.play(
            AnimationGroup(
                title.animate.set_opacity(1.0).shift(DOWN * 0.15),
                sub.animate.set_opacity(1.0).shift(DOWN * 0.10),
                underline.animate.set_opacity(1.0).shift(DOWN * 0.08),
                lag_ratio=0.12,
            ),
            run_time=0.70,
            rate_func=rf.ease_out_cubic,
        )

        self.play(
            AnimationGroup(
                evidence_grp.animate.set_opacity(1.0).shift(DOWN * 0.12).scale(1 / 0.985),
                scanner_grp.animate.set_opacity(1.0).scale(1 / 0.97),
                scanner_label.animate.set_opacity(1.0).shift(DOWN * 0.06),
                lag_ratio=0.10,
            ),
            run_time=0.60,
            rate_func=rf.ease_out_cubic,
        )

        self.play(
            AnimationGroup(
                left_bin["group"].animate.set_opacity(1.0).shift(UP * 0.20).scale(1 / 0.988),
                right_bin["group"].animate.set_opacity(1.0).shift(UP * 0.20).scale(1 / 0.988),
                left_bin["label"].animate.set_opacity(1.0).shift(UP * 0.08),
                right_bin["label"].animate.set_opacity(1.0).shift(UP * 0.08),
                lag_ratio=0.07,
            ),
            run_time=0.58,
            rate_func=rf.ease_out_cubic,
        )

        self.play(
            AnimationGroup(
                cL["group"].animate.set_opacity(1.0).shift(RIGHT * 0.28),
                cR["group"].animate.set_opacity(1.0).shift(LEFT * 0.28),
                lag_ratio=0.0,
            ),
            run_time=0.36,
            rate_func=rf.ease_out_cubic,
        )

        # -------------------------
        # LOOP ITEMS (LOCKED FLOW)
        # -------------------------
        entry = np.array([sf["right"] + 1.6, evidence_center[1] + 0.18, 0])

        scan_phrases = [
            "scanning evidence…",
            "validating intent…",
            "cross-checking logs…",
            "finalizing verdict…",
            "matching pattern…",
        ]

        # base idle label (reused)
        def make_scanner_label(line: str):
            g = VGroup(
                _safe_text("AI TRIBUNAL", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD),
                _safe_text("SCAN CORE", font_size=18, color=WHITE, weight=BOLD),
                _safe_text(line, font="Consolas", font_size=11, color=Theme.TEXT_SUB),
            ).arrange(DOWN, buff=0.06).move_to(scanner_center + DOWN * 0.02).set_z_index(230)
            if g.width > scanner["radius"] * 1.7:
                g.scale_to_fit_width(scanner["radius"] * 1.7)
            return g

        # smooth pulse instead of harsh flash
        def evidence_pulse(accent: str):
            self.play(
                evidence["outer"].animate.set_stroke(color=accent, width=3.2, opacity=0.90),
                run_time=0.10,
                rate_func=rf.ease_out_cubic,
            )
            self.play(
                evidence["outer"].animate.set_stroke(color=accent, width=2.6, opacity=0.62),
                run_time=0.12,
                rate_func=rf.ease_in_out_sine,
            )

        for _, row in df.iterrows():
            img_name = str(row.get("Image", "")).strip()
            reason = str(row.get("Reason", "UNKNOWN")).strip()
            try:
                cat = int(row.get("Category", 2))
            except Exception:
                cat = 2

            is_left = (cat == 1)
            accent = Theme.NEON_BLUE if is_left else Theme.NEON_PINK
            bin_ref = left_bin if is_left else right_bin
            counter_ref = cL if is_left else cR

            img_path = os.path.join(ASSETS_DIR, "images", img_name)

            sprite = build_sprite(img_path, accent=accent)
            sprite.move_to(entry)
            sprite.set_opacity(1.0)
            items_layer.add(sprite)

            # fit sprite into evidence
            fit_mobject_to_box(sprite, evidence["inner"].width * 0.78, evidence["inner"].height * 0.72)

            # accents
            evidence["outer"].set_stroke(color=accent, opacity=0.62)
            evidence["glow"].set_stroke(color=accent, opacity=0.09)
            scanner_set_accent(scanner, accent)

            # update reason tag (top border)
            text_obj = _safe_text(ellipsize(reason.upper(), 26), font="Consolas", font_size=15, color=WHITE, weight=BOLD)
            reason_txt.become(text_obj)
            reason_txt.set_z_index(205)

            # width based on text (clamped)
            w_cap = evidence["outer"].width * 0.86
            w_min = evidence["outer"].width * 0.48
            target_w = max(w_min, min(w_cap, reason_txt.width + 0.55))
            reason_plate.set_width(target_w)
            reason_glow.set_width(target_w)
            place_reason_tag()
            reason_txt.scale_to_fit_width(reason_plate.width * 0.90)
            reason_txt.move_to(reason_plate.get_center() + DOWN * 0.005)

            # ENTRY -> EVIDENCE (tiny anticipation + smooth)
            self.play(sprite.animate.shift(LEFT * 0.10), run_time=0.10, rate_func=rf.ease_out_cubic)
            self.play(
                AnimationGroup(
                    sprite.animate.move_to(evidence_center),
                    beam_alpha.animate.set_value(1.0),
                    reason_glow.animate.set_opacity(1.0),
                    reason_plate.animate.set_opacity(1.0),
                    reason_txt.animate.set_opacity(1.0),
                    lag_ratio=0.0,
                ),
                run_time=0.40,
                rate_func=rf.ease_out_cubic,
            )

            # SCAN (alive: rings rotate opposite, sweep subtle)
            sweep.set_opacity(1.0)
            for msg in random.sample(scan_phrases, k=3):
                new_label = make_scanner_label(msg)
                self.play(
                    AnimationGroup(
                        Transform(scanner_label, new_label),
                        Rotate(scanner["ticks"], angle=TAU * 0.14, about_point=scanner_center),
                        Rotate(scanner["dash"], angle=-TAU * 0.12, about_point=scanner_center),
                        Rotate(sweep, angle=TAU * 0.28, about_point=scanner_center),
                        lag_ratio=0.0,
                    ),
                    run_time=0.30,
                    rate_func=rf.ease_in_out_sine,
                )

            # VERDICT (premium pulse, no harsh flash)
            verdict = "GO LEFT" if is_left else "GO RIGHT"
            verdict_label = VGroup(
                _safe_text("VERDICT", font="Consolas", font_size=12, color=Theme.TEXT_SUB, weight=BOLD),
                _safe_text(verdict, font_size=22, color=accent, weight=BOLD),
                _safe_text("route locked", font="Consolas", font_size=11, color=Theme.TEXT_SUB),
            ).arrange(DOWN, buff=0.06).move_to(scanner_center + DOWN * 0.02).set_z_index(230)

            if verdict_label.width > scanner["radius"] * 1.7:
                verdict_label.scale_to_fit_width(scanner["radius"] * 1.7)

            self.play(Transform(scanner_label, verdict_label), run_time=0.22, rate_func=rf.ease_out_cubic)
            evidence_pulse(accent)

            # ROUTE glow ON + beam OFF
            self.play(beam_alpha.animate.set_value(0.0), run_time=0.12, rate_func=rf.ease_in_out_sine)
            if is_left:
                self.play(routeL_alpha.animate.set_value(1.0), run_time=0.14, rate_func=rf.ease_out_cubic)
            else:
                self.play(routeR_alpha.animate.set_value(1.0), run_time=0.14, rate_func=rf.ease_out_cubic)

            # MOVE card EVIDENCE -> BIN (smoother, scale late)
            start = evidence_center
            side = scanner_center + (LEFT * 1.75 if is_left else RIGHT * 1.75) + DOWN * 0.55
            end = (left_bin["mouth"] if is_left else right_bin["mouth"]).get_center() + DOWN * 0.05

            path = VMobject()
            path.set_points_smoothly([start, side, end])
            path.set_stroke(width=0, opacity=0)

            self.play(
                AnimationGroup(
                    MoveAlongPath(sprite, path, rate_func=rf.ease_in_out_cubic),
                    AnimationGroup(
                        Wait(0.22),
                        sprite.animate.scale(0.72),
                        lag_ratio=0.0,
                    ),
                    reason_txt.animate.set_opacity(0.0),
                    reason_plate.animate.set_opacity(0.0),
                    reason_glow.animate.set_opacity(0.0),
                    lag_ratio=0.0,
                ),
                run_time=0.58,
                rate_func=rf.ease_in_out_cubic,
            )

            # route glow OFF
            if is_left:
                self.play(routeL_alpha.animate.set_value(0.0), run_time=0.14, rate_func=rf.ease_in_out_sine)
            else:
                self.play(routeR_alpha.animate.set_value(0.0), run_time=0.14, rate_func=rf.ease_in_out_sine)

            sweep.set_opacity(0.0)

            # STORE inside container (grid pack)
            bin_ref["items"].append(sprite)
            n = len(bin_ref["items"])
            positions = pack_positions(bin_ref["inner"], n, cols=3)

            rows = int(math.ceil(n / 3))
            cell_w = bin_ref["inner"].width / 3
            cell_h = bin_ref["inner"].height / max(1, rows)
            max_w = cell_w * 0.78
            max_h = cell_h * 0.82

            self.play(
                LaggedStart(*[bin_ref["items"][i].animate.move_to(positions[i]) for i in range(n)], lag_ratio=0.03),
                run_time=0.26,
                rate_func=rf.ease_out_cubic,
            )
            for sp in bin_ref["items"]:
                fit_mobject_to_box(sp, max_w, max_h)

            # confirm pulse (soft)
            self.play(bin_ref["body"].animate.set_stroke(width=3.4, opacity=0.88), run_time=0.12, rate_func=rf.ease_out_cubic)
            self.play(bin_ref["body"].animate.set_stroke(width=2.6, opacity=0.62), run_time=0.14, rate_func=rf.ease_in_out_sine)

            # Counter increment
            counter_ref["value"] += 1
            new_txt = _safe_text(str(counter_ref["value"]), font="Consolas", font_size=28, color=WHITE, weight=BOLD)
            new_txt.move_to(counter_ref["txt"].get_center())
            self.play(Transform(counter_ref["txt"], new_txt), run_time=0.16, rate_func=rf.ease_out_cubic)
            self.play(counter_ref["outer"].animate.set_stroke(width=3.2, opacity=0.88), run_time=0.10, rate_func=rf.ease_out_cubic)
            self.play(counter_ref["outer"].animate.set_stroke(width=2.6, opacity=0.62), run_time=0.12, rate_func=rf.ease_in_out_sine)

            # back to idle
            idle = make_scanner_label("ready")
            self.play(Transform(scanner_label, idle), run_time=0.18, rate_func=rf.ease_out_cubic)

            # reset evidence neutral
            evidence["outer"].set_stroke(color=Theme.NEON_BLUE, opacity=0.62)
            evidence["glow"].set_stroke(color=Theme.NEON_BLUE, opacity=0.07)

        # WINNER HIGHLIGHT
        left_count = cL["value"]
        right_count = cR["value"]
        if left_count != right_count:
            win_bin = left_bin if left_count > right_count else right_bin
            win_counter = cL if left_count > right_count else cR
            win_accent = Theme.NEON_BLUE if left_count > right_count else Theme.NEON_PINK

            self.play(
                AnimationGroup(
                    win_bin["group"].animate.scale(1.02),
                    win_bin["body"].animate.set_stroke(color=win_accent, width=3.6, opacity=0.92),
                    lag_ratio=0.0,
                ),
                run_time=0.24,
                rate_func=rf.ease_out_cubic,
            )
            self.play(win_counter["outer"].animate.set_stroke(width=3.4, opacity=0.92), run_time=0.12, rate_func=rf.ease_out_cubic)
            self.play(win_counter["outer"].animate.set_stroke(width=2.6, opacity=0.62), run_time=0.14, rate_func=rf.ease_in_out_sine)
            self.play(
                win_bin["body"].animate.set_stroke(color=win_accent, width=2.6, opacity=0.62),
                run_time=0.18,
                rate_func=rf.ease_in_out_sine,
            )

        self.wait(1.2)
