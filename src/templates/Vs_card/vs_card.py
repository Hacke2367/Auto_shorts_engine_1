# vs_card.py  (VS CARD - GOD TIER BLUEPRINT IMPLEMENTATION | ALL PATCHES FINAL)
# Manim Community v0.19.x compatible
#
# Run:
#   manim -pqh vs_card.py VsCardFinal --disable_caching
#
# CSV format (meta in first line, then header row):
#   # TITLE=ABHISHEK vs PANDEY, SUB=AI ARENA // VS CARD, P1_NAME=ABHISHEK, P2_NAME=PANDEY, P1_IMG=player1.png, P2_IMG=player2.png
#   Metric,P1_Value,P2_Value,Winner,Emoji,Notes,Weight,Category
#
# NOTE:
# - Winner: 0=draw, 1=P1, 2=P2
# - Emoji/Notes/Weight/Category optional (auto-filled if missing)

import os
import sys
import math
import random
import re
from typing import Dict, Tuple, List

import numpy as np
import pandas as pd
from manim import *
from manim import rate_functions as rf

# ============================================================
# 1) PROJECT PATH SETUP + IMPORTS (same style as sort_card)
# ============================================================
import json
from pathlib import Path

try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    sys.path.append(project_root)

    from src.config import DATA_DIR, ASSETS_DIR, BACKGROUND_COLOR, Theme  # type: ignore
    from src.utils import IntroManager  # type: ignore
except Exception:
    project_root = os.getcwd()
    DATA_DIR = os.path.join(project_root, "data")
    ASSETS_DIR = os.path.join(project_root, "assets")
    BACKGROUND_COLOR = "#050505"

    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_GREEN = "#00FF66"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"

    class IntroManager:
        @staticmethod
        def play_intro(
            scene,
            brand_title="VS TRIBUNAL",
            brand_sub="HEAD-TO-HEAD PROTOCOL",
            feed_text="FEED_VS // TRIBUNAL",
            footer_text="CONFIDENTIAL // VERIFIED",
        ):
            t1 = Text(brand_title, font="Montserrat", weight=BOLD, font_size=48, color=WHITE).move_to(UP * 0.25)
            t2 = Text(brand_sub, font="Consolas", font_size=20, color=GREY_B).next_to(t1, DOWN, buff=0.25)
            scene.play(FadeIn(t2, shift=UP * 0.08), run_time=0.25)
            scene.play(FadeIn(t1, shift=UP * 0.10), run_time=0.35)
            scene.play(FadeOut(t1), FadeOut(t2), run_time=0.35)

# --- SYNC HELPERS ---
from src.sync.job import load_job
from src.sync.timeline import Timeline, clamp as _tl_clamp
from src.sfx.engine import SFXEngine
try:
    from src.sync.retention import hold_breathing, banner_scan_hold, register_template_accent
    from src.sync.retention_accents import retain_accent_vs_card
except Exception:
    def hold_breathing(scene, seconds: float, focus=None, text: str = ""):
        if seconds > 0:
            scene.wait(seconds)
    def register_template_accent(scene, fn):
        pass
    def retain_accent_vs_card(scene, focus, seconds, **kw):
        return lambda: None
    def banner_scan_hold(scene, banner, seconds: float, color=None):
        if seconds > 0:
            scene.wait(seconds)


# ============================================================
# 2) DATA LOADING (meta first line supported)
# ============================================================
_META_RE = re.compile(r"([A-Za-z_]+)\s*=\s*([^,]+)")


def load_vs_csv(csv_path: str) -> Tuple[Dict[str, str], pd.DataFrame]:
    if not os.path.exists(csv_path):
        meta = {
            "TITLE": "ABHISHEK vs PANDEY",
            "SUB": "AI ARENA // VS CARD",
            "P1_NAME": "ABHISHEK",
            "P2_NAME": "PANDEY",
            "P1_IMG": "player1.png",
            "P2_IMG": "player2.png",
        }
        df = pd.DataFrame(
            {
                "Metric": ["NET WORTH", "OVER CONFIDENCE", "LOYALTY", "GIRLFRIENDS"],
                "P1_Value": ["10 Lakhs", "No", "No", "1"],
                "P2_Value": ["0", "Yes", "No", "0"],
                "Winner": [1, 2, 0, 1],
                "Emoji": ["💰", "😤", "🛡️", "💘"],
                "Notes": ["", "", "", ""],
                "Weight": [1, 1, 1, 1],
                "Category": ["FINANCE", "BEHAVIOR", "TRAITS", "LIFE"],
            }
        )
        return meta, df

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        first = (f.readline() or "").strip()

    meta: Dict[str, str] = {}
    skip_first = False
    if first.startswith("#"):
        skip_first = True
        meta_line = first[1:].strip()
        for m in _META_RE.finditer(meta_line):
            meta[m.group(1).strip().upper()] = m.group(2).strip()

    df = pd.read_csv(csv_path, encoding="utf-8-sig", skiprows=1 if skip_first else 0)
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]

    required = ["Metric", "P1_Value", "P2_Value", "Winner"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}\n"
            f"Columns found in file: {df.columns.tolist()}\n"
            f"File used: {csv_path}"
        )

    for opt in ["Emoji", "Notes", "Weight", "Category"]:
        if opt not in df.columns:
            df[opt] = ""

    df["Metric"] = df["Metric"].astype(str).fillna("").str.strip().str.upper()
    df["P1_Value"] = df["P1_Value"].astype(str).fillna("").str.strip()
    df["P2_Value"] = df["P2_Value"].astype(str).fillna("").str.strip()
    df["Winner"] = pd.to_numeric(df["Winner"], errors="coerce").fillna(0).astype(int).clip(0, 2)

    df["Emoji"] = df["Emoji"].astype(str).fillna("").str.strip()
    # IMPORTANT: stop "nan" leaking into UI
    df["Notes"] = df["Notes"].astype(str).fillna("").replace("nan", "").replace("NAN", "").str.strip()
    df["Category"] = df["Category"].astype(str).fillna("").str.strip().str.upper()
    df["Weight"] = pd.to_numeric(df["Weight"], errors="coerce").fillna(1.0)

    df = df[(df["Metric"] != "") & (df["Metric"].str.upper() != "NAN")].reset_index(drop=True)
    return meta, df


# ============================================================
# 3) SMALL SAFE HELPERS
# ============================================================
def clamp(x: float, a: float, b: float) -> float:
    return float(max(a, min(b, x)))


def safe_text(
    s: str,
    font: str = "Montserrat",
    font_size: int = 24,
    color=WHITE,
    weight=BOLD,
) -> Text:
    try:
        return Text(str(s), font=font, font_size=font_size, color=color, weight=weight)
    except Exception:
        return Text(str(s), font_size=font_size, color=color)


def ellipsize(s: str, n: int = 34) -> str:
    s = str(s)
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def fmt_pts(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.1f}"


def get_safe_frame(W: float, H: float, *, m_top=0.90, m_bottom=0.80, m_side=0.62) -> Dict[str, float]:
    """
    Safe UI area so elements never collide with IntroManager border/overlay.
    """
    left = -W / 2 + m_side
    right = W / 2 - m_side
    top = H / 2 - m_top
    bottom = -H / 2 + m_bottom
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "width": right - left,
        "height": top - bottom,
    }


# ============================================================
# PATCH #6: SMART IMAGE RESOLVER (CSV meta -> assets/images)
# ============================================================
def resolve_player_image_path(img_filename: str, *, fallback_index: int = 0) -> str:
    """
    Smart resolver for assets/images:
    - supports png/jpg/jpeg/webp
    - fixes wrong extensions (player1.png -> player1.jpg)
    - case-insensitive match
    - fallback: pick first two images from folder (sorted) for P1/P2
    """
    images_dir = os.path.join(ASSETS_DIR, "images")
    if not os.path.isdir(images_dir):
        return ""

    def exists(p: str) -> bool:
        try:
            return bool(p) and os.path.exists(p)
        except Exception:
            return False

    # 1) exact
    if img_filename:
        p = os.path.join(images_dir, img_filename)
        if exists(p):
            return p

        # 2) same basename + common extensions
        base, _ext = os.path.splitext(img_filename)
        common_exts = [".png", ".jpg", ".jpeg", ".webp"]
        if base:
            for e in common_exts:
                p2 = os.path.join(images_dir, base + e)
                if exists(p2):
                    return p2

        # 3) case-insensitive exact match
        low = img_filename.lower()
        try:
            for fn in os.listdir(images_dir):
                if fn.lower() == low:
                    p3 = os.path.join(images_dir, fn)
                    if exists(p3):
                        return p3
        except Exception:
            pass

        # 4) fuzzy contains match (basename)
        lowb = base.lower().strip() if base else ""
        if lowb:
            try:
                for fn in os.listdir(images_dir):
                    if lowb in fn.lower():
                        p4 = os.path.join(images_dir, fn)
                        if exists(p4):
                            return p4
            except Exception:
                pass

    # 5) fallback: first N images (sorted)
    try:
        all_files = sorted(os.listdir(images_dir))
    except Exception:
        return ""

    valid = []
    for fn in all_files:
        low = fn.lower()
        if low.endswith((".png", ".jpg", ".jpeg", ".webp")):
            full = os.path.join(images_dir, fn)
            if exists(full):
                valid.append(full)

    if not valid:
        return ""

    idx = int(max(0, fallback_index))
    if idx >= len(valid):
        idx = len(valid) - 1
    return valid[idx]


# ============================================================
# 4) VISUAL BUILDERS (ALL PATCHED)
# ============================================================
def build_background(W: float, H: float, c_left: str, c_right: str, c_mid: str) -> Group:
    """
    Tribunal background with alive depth (NO dull screen):
    - stronger ambient blooms
    - neutral scan rings
    - particles + subtle streaks
    """
    g = Group()

    left_glow = Circle(radius=max(W, H) * 0.70).set_fill(c_left, 0.095).set_stroke(width=0).move_to([-1.85, 0.75, 0])
    right_glow = Circle(radius=max(W, H) * 0.70).set_fill(c_right, 0.085).set_stroke(width=0).move_to([+1.85, 0.65, 0])
    mid_glow = Circle(radius=max(W, H) * 0.62).set_fill(c_mid, 0.040).set_stroke(width=0).move_to([0.0, -0.25, 0])
    g.add(left_glow, right_glow, mid_glow)

    rings = VGroup()
    for r, op, w in [(2.45, 0.09, 2), (3.05, 0.065, 2), (3.65, 0.050, 2)]:
        ring = DashedVMobject(Circle(radius=r), num_dashes=90)
        ring.set_stroke(color=WHITE, width=w, opacity=op)
        rings.add(ring)
    rings.set_z_index(3)
    rings.add_updater(lambda m, dt: m.rotate(0.10 * dt))

    grid = NumberPlane(
        x_range=[-20, 20, 1],
        y_range=[-20, 20, 1],
        background_line_style={"stroke_color": c_left, "stroke_width": 1, "stroke_opacity": 0.017},
        axis_config={"stroke_opacity": 0},
    )
    grid.add_updater(lambda m, dt: m.shift(UL * 0.020 * dt))

    rng = np.random.default_rng(13)
    particles = VGroup()
    for _ in range(30):
        p = Dot(radius=float(rng.uniform(0.018, 0.045)), color=WHITE)
        p.set_opacity(float(rng.uniform(0.08, 0.20)))
        p.move_to([float(rng.uniform(-W / 2, W / 2)), float(rng.uniform(-H / 2, H / 2)), 0])
        p.v = UP * float(rng.uniform(0.06, 0.14))
        particles.add(p)

    def upd_particles(mob, dt):
        for p in mob:
            p.shift(p.v * dt)
            if p.get_y() > (H / 2 + 0.7):
                p.move_to([float(rng.uniform(-W / 2, W / 2)), -H / 2 - 0.7, 0])

    particles.add_updater(upd_particles)
    particles.set_z_index(4)

    streaks = VGroup()
    for _ in range(20):
        length = float(rng.uniform(0.22, 0.58))
        ln = Line(ORIGIN, UP * length)
        ln.set_stroke(
            width=float(rng.uniform(1.0, 2.2)),
            color=random.choice([c_left, c_right, GREY_B]),
            opacity=float(rng.uniform(0.10, 0.24)),
        )
        ln.move_to([float(rng.uniform(-W / 2, W / 2)), float(rng.uniform(-H / 2, H / 2)), 0])
        ln.velocity = DOWN * float(rng.uniform(1.1, 2.2))
        streaks.add(ln)

    def update_streaks(mob, dt):
        for ln in mob:
            ln.shift(ln.velocity * dt)
            if ln.get_y() < (-H / 2 - 0.8):
                ln.move_to([float(rng.uniform(-W / 2, W / 2)), (H / 2 + 0.8), 0])
                ln.velocity = DOWN * float(rng.uniform(1.1, 2.2))

    streaks.add_updater(update_streaks)
    streaks.set_z_index(5)

    vign = Rectangle(width=W * 1.35, height=H * 1.35).set_fill(BLACK, 0).set_stroke(BLACK, 140, 0.22)
    vign.set_z_index(6)

    g.add(grid, rings, particles, streaks, vign)
    try:
        g.set_z_index(1)
    except Exception:
        pass
    return g


def build_energy_spine(center: np.ndarray, W: float, c_left: str, c_right: str) -> VGroup:
    x, y, _ = center

    vline = Line([x, y + 2.6, 0], [x, y - 3.0, 0]).set_stroke(WHITE, 3, 0.11)
    vglow = vline.copy().set_stroke(c_left, 18, 0.07)

    node = Dot([x, y, 0], radius=0.06, color=WHITE).set_opacity(0.68)
    ring = DashedVMobject(Circle(radius=0.24), num_dashes=20)
    ring.move_to(node.get_center()).set_stroke(c_left, 2, 0.24)

    hl = Line([x - W * 0.18, y, 0], [x, y, 0]).set_stroke(c_left, 3, 0.11)
    hr = Line([x, y, 0], [x + W * 0.18, y, 0]).set_stroke(c_right, 3, 0.11)
    hgl = hl.copy().set_stroke(c_left, 14, 0.06)
    hgr = hr.copy().set_stroke(c_right, 14, 0.06)

    t = ValueTracker(0.0)

    def pulse(_, dt):
        t.increment_value(dt)
        v = float(t.get_value())
        base = 0.05 + 0.03 * (0.5 + 0.5 * math.sin(v * 1.5))
        vglow.set_stroke(opacity=base)
        hgl.set_stroke(opacity=base)
        hgr.set_stroke(opacity=base)
        node.set_opacity(0.55 + 0.25 * (0.5 + 0.5 * math.sin(v * 2.4)))
        ring.rotate(-0.95 * dt)
        ring.set_stroke(opacity=0.18 + 0.10 * (0.5 + 0.5 * math.sin(v * 1.7)))

    grp = VGroup(vglow, vline, hgl, hgr, hl, hr, ring, node)
    grp.add_updater(pulse)
    grp.set_z_index(160)
    return grp


def build_elbow_connector(a: np.ndarray, b: np.ndarray, color: str, opacity: float = 0.20, lock_x: float | None = None) -> VGroup:
    """
    PATCH #1: Use elbow connectors to avoid ugly diagonals.
    If lock_x is provided, we force a vertical segment at lock_x (looks "straight" & premium).
    """
    ax, ay, _ = a
    bx, by, _ = b
    x = float(lock_x) if lock_x is not None else float(ax)

    p1 = np.array([ax, ay, 0.0])
    p2 = np.array([x, ay, 0.0])
    p3 = np.array([x, by, 0.0])
    p4 = np.array([bx, by, 0.0])

    seg1 = Line(p1, p2).set_stroke(color=color, width=2, opacity=opacity)
    seg2 = Line(p2, p3).set_stroke(color=color, width=2, opacity=opacity)
    seg3 = Line(p3, p4).set_stroke(color=color, width=2, opacity=opacity)

    glow1 = seg1.copy().set_stroke(color=color, width=10, opacity=max(0.06, opacity * 0.35))
    glow2 = seg2.copy().set_stroke(color=color, width=10, opacity=max(0.06, opacity * 0.35))
    glow3 = seg3.copy().set_stroke(color=color, width=10, opacity=max(0.06, opacity * 0.35))

    d1 = Dot(p1, radius=0.03, color=color).set_opacity(min(0.9, opacity + 0.35))
    d2 = Dot(p4, radius=0.03, color=color).set_opacity(min(0.9, opacity + 0.35))

    grp = VGroup(glow1, glow2, glow3, seg1, seg2, seg3, d1, d2)
    grp.set_z_index(155)
    return grp


# ============================================================
# PATCH #6 APPLIED HERE: create_player_card (smart image + safe fit)
# ============================================================
def create_player_card(
    name: str,
    accent: str,
    img_filename: str,
    center: np.ndarray,
    frame_w: float,
    frame_h: float,
    *,
    fallback_index: int = 0,  # NEW (P1=0, P2=1)
) -> Dict[str, Mobject]:
    bg = RoundedRectangle(width=frame_w, height=frame_h, corner_radius=0.18).set_fill("#050505", 0.94).set_stroke(width=0)
    bg.move_to(center)

    img_path = resolve_player_image_path(img_filename, fallback_index=fallback_index)

    if img_path and os.path.exists(img_path):
        portrait = ImageMobject(img_path)

        inner_w = frame_w - 0.18
        inner_h = frame_h - 0.18

        portrait.scale_to_fit_width(inner_w)
        if portrait.height > inner_h:
            portrait.scale_to_fit_height(inner_h)
    else:
        portrait = safe_text((name[:1] or "?").upper(), font_size=96, color=accent, weight=BOLD)

    portrait.move_to(bg.get_center())

    frame = RoundedRectangle(width=frame_w, height=frame_h, corner_radius=0.18).set_fill(opacity=0)
    frame.set_stroke(accent, 2.9, 0.93).move_to(bg.get_center())
    glow = frame.copy().set_stroke(accent, 22, 0.22)

    c_len = 0.40
    corners = VGroup(
        VGroup(Line(ORIGIN, RIGHT * c_len), Line(ORIGIN, DOWN * c_len)).move_to(bg.get_corner(UL)),
        VGroup(Line(ORIGIN, LEFT * c_len), Line(ORIGIN, DOWN * c_len)).move_to(bg.get_corner(UR)),
        VGroup(Line(ORIGIN, RIGHT * c_len), Line(ORIGIN, UP * c_len)).move_to(bg.get_corner(DL)),
        VGroup(Line(ORIGIN, LEFT * c_len), Line(ORIGIN, UP * c_len)).move_to(bg.get_corner(DR)),
    )
    corners.set_stroke(accent, 5.4, 0.96)

    plate = RoundedRectangle(width=frame_w * 0.86, height=0.52, corner_radius=0.14)
    plate.set_fill("#070A0C", 0.92).set_stroke(accent, 2.2, 0.78)
    plate.move_to(bg.get_bottom() + UP * 0.42)
    label = safe_text(name.upper(), font_size=22, color=accent, weight=BOLD).move_to(plate.get_center())

    badge = Circle(radius=0.30).set_fill("#0F0F0F", 1.0).set_stroke(WHITE, 2.0, 0.93)
    badge.move_to(bg.get_top() + DOWN * 0.16)
    score = safe_text("0", font="Consolas", font_size=22, color=WHITE, weight=BOLD).move_to(badge.get_center())
    pts_tag = safe_text("PTS", font="Consolas", font_size=10, color=GREY_C, weight=BOLD)
    pts_tag.next_to(badge.get_bottom(), UP, buff=0.06)

    group = Group(bg, portrait, glow, frame, corners, plate, label, badge, score, pts_tag)
    group.set_z_index(260)

    return {
        "group": group,
        "frame": frame,
        "glow": glow,
        "corners": corners,
        "badge": badge,
        "score": score,
        "pts_tag": pts_tag,
        "name": name,
        "accent": accent,
        "bg": bg,
        "plate": plate,
        "label": label,
        "portrait": portrait,
    }


def build_value_box(center: np.ndarray, accent: str) -> Dict[str, Mobject]:
    box = RoundedRectangle(width=2.25, height=0.86, corner_radius=0.22)
    box.set_fill("#000000", 0.92)
    box.set_stroke(accent, 4.0, 0.92)
    box.move_to(center)

    glow = box.copy().set_fill(opacity=0).set_stroke(accent, 22, 0.20)
    txt = safe_text("-", font_size=30, color=WHITE, weight=BOLD).move_to(center)
    txt.set_opacity(1.0)

    grp = VGroup(glow, box, txt)
    grp.set_z_index(255)
    return {"group": grp, "box": box, "glow": glow, "txt": txt}


def build_announcement_box(center: np.ndarray, width: float, c_left: str, c_right: str) -> Dict[str, Mobject]:
    outer = RoundedRectangle(width=width, height=1.30, corner_radius=0.24)
    outer.set_fill("#070A0C", 0.92)
    outer.set_stroke(color=[c_left, c_right], width=3.4, opacity=0.95)
    outer.move_to(center)

    glow = outer.copy().set_fill(opacity=0).set_stroke(color=[c_left, c_right], width=26, opacity=0.22)

    top_line = safe_text(
        "ROUND 1/1   |   CATEGORY: —",
        font="Consolas",
        font_size=14,
        color=getattr(Theme, "TEXT_SUB", "#B8B8B8"),
        weight=BOLD,
    )
    main_line = safe_text("🔥 METRIC", font="Montserrat", font_size=36, color=WHITE, weight=BOLD)
    sub_line = safe_text(
        "Weight: 1.0",
        font="Consolas",
        font_size=14,
        color=getattr(Theme, "TEXT_SUB", "#B8B8B8"),
        weight=BOLD,
    )

    text = VGroup(top_line, main_line, sub_line).arrange(DOWN, buff=0.08)
    text.move_to(outer.get_center() + DOWN * 0.02)

    grp = VGroup(glow, outer, text)
    grp.set_z_index(320)
    return {"group": grp, "outer": outer, "glow": glow, "top": top_line, "main": main_line, "sub": sub_line, "text": text}


def build_decision_terminal(center: np.ndarray, w: float, h: float, accent: str, sub: str) -> Dict[str, Mobject]:
    plate = RoundedRectangle(width=w, height=h, corner_radius=0.18)
    plate.set_fill("#06090B", 0.96)
    plate.set_stroke(accent, 3.0, 0.96)
    plate.move_to(center)

    glow = plate.copy().set_fill(opacity=0).set_stroke(accent, 26, 0.22)

    head = RoundedRectangle(width=w - 0.18, height=0.26, corner_radius=0.10)
    head.set_fill("#0B1116", 1.0).set_stroke(width=0)
    head.move_to(plate.get_top() + DOWN * 0.20)

    dot = Dot(radius=0.04, color=accent).set_opacity(0.85)
    dot.move_to(head.get_left() + RIGHT * 0.22)

    head_txt = safe_text("DECISION TERMINAL", font="Consolas", font_size=12, color=sub, weight=BOLD)
    head_txt.move_to(head.get_center() + LEFT * (w * 0.12))

    line1 = safe_text("AI TRIBUNAL SCANNING", font="Consolas", font_size=18, color=WHITE, weight=BOLD)
    line2 = safe_text("log: awaiting input...", font="Consolas", font_size=14, color=sub, weight=BOLD)
    line3 = safe_text("status: online", font="Consolas", font_size=14, color=sub, weight=BOLD)

    pad_x = 0.24
    body = VGroup(line1, line2, line3).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
    body.move_to(plate.get_center() + DOWN * 0.08)
    body.align_to(plate.get_left() + RIGHT * pad_x, LEFT)

    scan = Rectangle(width=w - 0.18, height=0.05).set_fill(accent, 0.10).set_stroke(width=0)
    scan.move_to(plate.get_bottom() + UP * 0.25)

    t = ValueTracker(0.0)

    def scan_updater(mob, dt):
        t.increment_value(dt)
        v = float(t.get_value())
        y0 = plate.get_bottom()[1] + 0.25
        y1 = plate.get_top()[1] - 0.40
        yy = y0 + (0.5 + 0.5 * math.sin(v * 2.2)) * (y1 - y0)
        mob.move_to([plate.get_center()[0], yy, 0])
        mob.set_fill(opacity=0.06 + 0.06 * (0.5 + 0.5 * math.sin(v * 3.1)))

    scan.add_updater(scan_updater)

    grp = VGroup(glow, plate, head, dot, head_txt, body, scan)
    grp.set_z_index(332)

    return {
        "group": grp,
        "plate": plate,
        "glow": glow,
        "head": head,
        "head_txt": head_txt,
        "dot": dot,
        "line1": line1,
        "line2": line2,
        "line3": line3,
        "body": body,
        "scan": scan,
        "pad_x": pad_x,
    }


def build_scoreboard(center: np.ndarray, w: float, c_left: str, c_right: str, p1_name: str, p2_name: str) -> Dict[str, Mobject]:
    bar = RoundedRectangle(width=w, height=0.84, corner_radius=0.30)
    bar.set_fill("#070A0C", 0.94)
    bar.set_stroke(color=[c_left, c_right], width=3.0, opacity=0.92)
    bar.move_to(center)

    glow = bar.copy().set_fill(opacity=0).set_stroke(color=[c_left, c_right], width=26, opacity=0.20)

    label = safe_text("SCOREBOARD", font="Consolas", font_size=12, color=GREY_B, weight=BOLD)
    label.move_to(bar.get_top() + DOWN * 0.20)

    left_name = safe_text(p1_name.upper(), font_size=20, color=c_left, weight=BOLD)
    right_name = safe_text(p2_name.upper(), font_size=20, color=c_right, weight=BOLD)
    score_txt = safe_text("0  —  0", font="Consolas", font_size=26, color=WHITE, weight=BOLD)

    sep1 = Line(UP * 0.22, DOWN * 0.22).set_stroke(WHITE, 2, 0.18)
    sep2 = sep1.copy()
    row = VGroup(left_name, sep1, score_txt, sep2, right_name).arrange(RIGHT, buff=0.22)
    row.move_to(bar.get_center() + DOWN * 0.07)

    grp = VGroup(glow, bar, label, row)
    grp.set_z_index(300)

    return {"group": grp, "bar": bar, "glow": glow, "left": left_name, "right": right_name, "score": score_txt, "row": row, "label": label}


# ============================================================
# PATCH #2: LIVE COMMENTARY -> SINGLE LINE SYSTEM STATUS TICKER
# ============================================================
def build_notes_console(center: np.ndarray, w: float, c_accent: str, c_sub: str, c_high: str) -> Dict[str, Mobject]:
    """
    PATCH #2:
    - LIVE COMMENTARY -> SINGLE LINE SYSTEM STATUS ticker
    - no decision duplication (decision already inside terminal)
    - blinking caret terminal feel
    """
    chip = RoundedRectangle(width=w, height=0.62, corner_radius=0.18)
    chip.set_fill("#0B0B0B", 0.94)
    chip.set_stroke(c_accent, 2.4, 0.60)
    chip.move_to(center)

    glow = chip.copy().set_fill(opacity=0).set_stroke(c_accent, 18, 0.14)

    head = safe_text("SYSTEM STATUS", font="Consolas", font_size=12, color=c_sub, weight=BOLD)
    head.move_to(chip.get_top() + DOWN * 0.20)
    head.align_to(chip.get_left() + RIGHT * 0.20, LEFT)

    line = safe_text("• system: initializing | backend: online", font="Consolas", font_size=16, color=WHITE, weight=BOLD)
    if line.width > (chip.width - 0.65):
        line.scale_to_fit_width(chip.width - 0.65)
    line.move_to(chip.get_center() + DOWN * 0.08)
    line.align_to(chip.get_left() + RIGHT * 0.20, LEFT)

    caret = safe_text("▍", font="Consolas", font_size=18, color=c_accent, weight=BOLD)
    caret.next_to(line, RIGHT, buff=0.10)

    t = ValueTracker(0.0)

    def caret_blink(mob, dt):
        t.increment_value(dt)
        v = float(t.get_value())
        mob.set_opacity(0.25 + 0.75 * (0.5 + 0.5 * math.sin(v * 6.0)))

    caret.add_updater(caret_blink)

    grp = VGroup(glow, chip, head, line, caret)
    grp.set_z_index(305)
    return {"group": grp, "chip": chip, "glow": glow, "head": head, "line": line, "caret": caret}


def build_title_scanner_line(center_y: float, width: float, c_left: str, c_right: str) -> VGroup:
    base = Line(LEFT * width / 2, RIGHT * width / 2).set_stroke(WHITE, 2, 0.18)
    base.move_to([0.0, center_y, 0.0])

    glow = base.copy().set_stroke(color=[c_left, c_right], width=12, opacity=0.10)

    seg = Line(LEFT * 0.55, RIGHT * 0.55).set_stroke(color=[c_left, c_right], width=3.2, opacity=0.85)
    seg.move_to(base.get_left())

    dot = Dot(radius=0.04, color=c_left).set_opacity(0.85)
    dot.move_to(seg.get_right())

    t = ValueTracker(0.0)

    def mover(_m, dt):
        t.increment_value(dt)
        v = float(t.get_value())
        u = 0.5 + 0.5 * math.sin(v * 1.4)
        x = base.get_left()[0] + u * (base.get_right()[0] - base.get_left()[0])
        seg.move_to([x, base.get_center()[1], 0.0])
        dot.move_to(seg.get_right())
        dot.set_color(c_right if u > 0.5 else c_left)

    seg.add_updater(mover)

    grp = VGroup(glow, base, seg, dot)
    grp.set_z_index(339)
    return grp


# ============================================================
# 5) MAIN SCENE
# ============================================================
# --- Premium visual layer (Visual & Aesthetic Pass) ---
try:
    from src.utils import add_cinematic_background
except Exception:
    def add_cinematic_background(*_a, **_k):
        return None
try:
    from src.config import FONT_DISPLAY
except Exception:
    FONT_DISPLAY = "Montserrat"


class VsCardFinal(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        add_cinematic_background(self, accent=Theme.NEON_BLUE)

        # ✅ Phase 2 Sync Standard: The 0.0s Intro Rule
        global_start_t0 = float(self.time)
        # Spine (central VS divider) built later; accent uses focus as fallback
        register_template_accent(
            self,
            lambda s, f, t: retain_accent_vs_card(s, f, t),
        )

        try:
            IntroManager.play_intro(
                self,
                brand_title="VS TRIBUNAL",
                brand_sub="HEAD-TO-HEAD PROTOCOL",
                feed_text="FEED_VS // TRIBUNAL",
                footer_text="CONFIDENTIAL // VERIFIED",
            )
        except Exception:
            pass

        W = float(config.frame_width)
        H = float(config.frame_height)
        sf = get_safe_frame(W, H, m_top=0.90, m_bottom=0.82, m_side=0.62)

        # Colors
        C_P1 = getattr(Theme, "NEON_BLUE", "#00F0FF")
        C_P2 = getattr(Theme, "NEON_PINK", "#FF0055")
        C_PURP = getattr(Theme, "NEON_PURPLE", "#BD00FF")
        C_WIN = getattr(Theme, "NEON_GREEN", "#00FF66")
        C_MAIN = getattr(Theme, "TEXT_MAIN", "#FFFFFF")
        C_SUB = getattr(Theme, "TEXT_SUB", "#B8B8B8")
        C_GOLD = "#FFD700"
        C_HI = "#7CFFB8"

        # ============================================================
        # JOB DATA & TIMELINE INJECTION (Audio Sync Pattern A)
        # ============================================================
        from pathlib import Path

        JOB_DIR = os.environ.get("JOB_DIR")
        JOB_JSON_PATH = os.environ.get("JOB_JSON_PATH", "")

        job_dir_path = Path(JOB_DIR) if JOB_DIR else None
        if not job_dir_path and JOB_JSON_PATH:
            job_dir_path = Path(JOB_JSON_PATH).parent

        sfx = SFXEngine(self, str(job_dir_path) if job_dir_path else str(Path.cwd()))

        job_data = {}
        if job_dir_path and job_dir_path.exists():
            try:
                job_data = load_job(job_dir_path)
            except Exception:
                pass

        audio_timings = job_data.get("timeline", {})

        csv_path = os.path.join(DATA_DIR, "vs_data.csv")
        meta, df = load_vs_csv(csv_path)

        # Dynamic template segment discovery based on input rows.
        n_rounds = max(1, len(df))
        round_segments = [f"round_{i+1}" for i in range(n_rounds)]
        audio_order = ["hook", "setup"] + round_segments + ["winner", "outro"]

        # Default durations if json lacks entries
        defaults = {
            "hook": 3.8,
            "setup": 3.2,
            "winner": 3.8,
            "outro": 2.2,
        }
        for seg in round_segments:
            defaults[seg] = 4.2

        TL = Timeline.from_dict(audio_timings, defaults=defaults)

        hook_seg = audio_order[0]
        setup_seg = audio_order[1]
        winner_seg = "winner"
        outro_seg = "outro"

        title_raw = (meta.get("TITLE", "ABHISHEK vs PANDEY") or "").strip()
        sub_raw = (meta.get("SUB", "AI ARENA // VS CARD") or "").strip()

        p1_name = (meta.get("P1_NAME", "ABHISHEK") or "ABHISHEK").strip()
        p2_name = (meta.get("P2_NAME", "PANDEY") or "PANDEY").strip()
        p1_img = (meta.get("P1_IMG", "player1.png") or "player1.png").strip()
        p2_img = (meta.get("P2_IMG", "player2.png") or "player2.png").strip()

        # Layers
        bg_layer = Group()
        fx_layer = Group()
        ui_layer = Group()
        self.add(bg_layer, fx_layer, ui_layer)

        bg_layer.add(build_background(W, H, C_P1, C_P2, C_PURP))

        # ----------------------------------------------------------------
        # SAFE LAYOUT (PATCH #1 + #4)
        # PATCH #1: hud_y will be computed dynamically AFTER subtitle exists
        # ----------------------------------------------------------------
        # top_y = sf["top"] - 0.35  ## OLD ONE
        TITLE_DROP = 0.05  # 5%
        top_y = sf["top"] - (0.35 + sf["height"] * TITLE_DROP)
        cards_y = 0.10
        values_y = -2.05
        score_y = sf["bottom"] + 0.48
        notes_y = score_y + 0.92
        decision_y = notes_y + 1.30

        # Cards
        X_OFF = 2.15
        card_w, card_h = 2.70, 3.70

        # ----------------------------------------------------------------
        # HEADER (VS always visible + moving line under title)
        # ----------------------------------------------------------------
        parts = re.split(r"\s+vs\s+", title_raw, flags=re.IGNORECASE)
        left_title = parts[0].strip() if len(parts) == 2 else p1_name
        right_title = parts[1].strip() if len(parts) == 2 else p2_name

        tL = safe_text(left_title.upper(), font=FONT_DISPLAY, font_size=38, color=C_P1, weight=BOLD)
        tR = safe_text(right_title.upper(), font=FONT_DISPLAY, font_size=38, color=C_P2, weight=BOLD)

        vs_box = Square(side_length=0.74, color=C_GOLD, stroke_width=3).rotate(45 * DEGREES)
        vs_txt = safe_text("VS", font="Montserrat", font_size=22, color=C_GOLD, weight=BOLD)
        vs_grp = VGroup(vs_box, vs_txt)
        vs_grp.set_z_index(341)

        # header = VGroup(tL, vs_grp, tR).arrange(RIGHT, buff=0.33).move_to([0, top_y, 0])  ## OLD ONE
        TITLE_GAP = 0.18  # smaller = closer
        header = VGroup(tL, vs_grp, tR).arrange(RIGHT, buff=TITLE_GAP).move_to([0, top_y, 0])
        header.set_z_index(340)

        pulse = ValueTracker(0.0)

        def vs_pulse(_m, dt):
            pulse.increment_value(dt)
            v = float(pulse.get_value())
            vs_box.set_stroke(width=3.1 + 0.9 * (0.5 + 0.5 * math.sin(v * 5.0)), opacity=0.94)
            vs_box.rotate(0.18 * dt)

        vs_box.add_updater(vs_pulse)

        # sub = safe_text(sub_raw, font="Consolas", font_size=14, color=C_SUB, weight=BOLD)   ## OLD ONE
        # sub.next_to(header, DOWN, buff=0.08).set_opacity(0.90)
        # sub.set_z_index(340)
        #
        # scan_line = build_title_scanner_line(
        #     center_y=sub.get_bottom()[1] - 0.18,
        #     width=min(sf["width"] * 0.70, 6.4),
        #     c_left=C_P1,
        #     c_right=C_P2,
        # )
        #
        # ui_layer.add(header, sub, scan_line)

        # Subtitle banate hain but position baad me set karenge
        sub = safe_text(sub_raw, font="Consolas", font_size=14, color=C_SUB, weight=BOLD)
        sub.set_opacity(0.90)
        sub.set_z_index(340)

        # LINE: title ke niche (subtitle abhi line ke baad)
        scan_line_y = header.get_bottom()[1] - 0.22
        scan_line = build_title_scanner_line(
            center_y=scan_line_y,
            width=min(sf["width"] * 0.70, 6.4),
            c_left=C_P1,
            c_right=C_P2,
        )

        # Subtitle line ke niche
        SUB_GAP = 0.10
        sub.next_to(scan_line, DOWN, buff=SUB_GAP)

        ui_layer.add(header, scan_line, sub)

        # ----------------------------------------------------------------
        # PATCH #1: Metrics box position dynamic (subtitle ke niche)
        # ----------------------------------------------------------------
        # hud_y = sub.get_bottom()[1] - 0.62  ## OLD ONE

        # PATCH: Metrics box subtitle ke niche controlled distance pe
        METRICS_GAP = 0.05  # 5%
        hud_y = sub.get_bottom()[1] - (sf["height"] * METRICS_GAP) - 0.30

        # ----------------------------------------------------------------
        # METRICS / ANNOUNCEMENT
        # ----------------------------------------------------------------
        ann_w = clamp(min(sf["width"] * 0.92, 6.6), 5.0, 6.6)
        ann = build_announcement_box(center=np.array([0.0, hud_y, 0]), width=ann_w, c_left=C_P1, c_right=C_P2)
        ui_layer.add(ann["group"])

        # ----------------------------------------------------------------
        # DECISION TERMINAL
        # ----------------------------------------------------------------
        term_w, term_h = clamp(min(sf["width"] * 0.92, 6.2), 5.2, 6.2), 1.30
        terminal = build_decision_terminal(np.array([0.0, decision_y, 0]), term_w, term_h, C_GOLD, C_SUB)
        terminal["group"].set_opacity(1.0)
        ui_layer.add(terminal["group"])

        # ----------------------------------------------------------------
        # SPINE + CARDS + VALUES
        # ----------------------------------------------------------------
        spine_center = np.array([0.0, cards_y + 0.18, 0])
        spine = build_energy_spine(spine_center, W, C_P1, C_P2)
        fx_layer.add(spine)

        p1 = create_player_card(p1_name, C_P1, p1_img, np.array([-X_OFF, cards_y, 0]), card_w, card_h, fallback_index=0)
        p2 = create_player_card(p2_name, C_P2, p2_img, np.array([+X_OFF, cards_y, 0]), card_w, card_h, fallback_index=1)
        ui_layer.add(p1["group"], p2["group"])

        v1 = build_value_box(np.array([-X_OFF, values_y, 0]), C_P1)
        v2 = build_value_box(np.array([+X_OFF, values_y, 0]), C_P2)
        ui_layer.add(v1["group"], v2["group"])

        scoreboard = build_scoreboard(
            np.array([0.0, score_y, 0]),
            w=min(sf["width"], 6.6),
            c_left=C_P1,
            c_right=C_P2,
            p1_name=p1_name,
            p2_name=p2_name,
        )
        ui_layer.add(scoreboard["group"])

        notes = build_notes_console(
            np.array([0.0, notes_y, 0]),
            w=min(sf["width"], 6.2),
            c_accent=C_GOLD,
            c_sub=C_SUB,
            c_high=C_HI,
        )
        ui_layer.add(notes["group"])

        # ----------------------------------------------------------------
        # CONNECTORS (straight/clean)
        # ----------------------------------------------------------------
        conn_alpha = ValueTracker(1.0)

        def a_val() -> float:
            return float(conn_alpha.get_value())

        conn_ann_spine = always_redraw(
            lambda: build_elbow_connector(
                ann["outer"].get_bottom() + DOWN * 0.05,
                spine_center + UP * 1.05,
                WHITE,
                opacity=0.16 * a_val(),
                lock_x=0.0,
            )
        )
        conn_spine_p1 = always_redraw(
            lambda: build_elbow_connector(
                spine_center,
                p1["bg"].get_right() + LEFT * 0.05,
                C_P1,
                opacity=0.18 * a_val(),
                lock_x=0.0,
            )
        )
        conn_spine_p2 = always_redraw(
            lambda: build_elbow_connector(
                spine_center,
                p2["bg"].get_left() + RIGHT * 0.05,
                C_P2,
                opacity=0.18 * a_val(),
                lock_x=0.0,
            )
        )
        conn_p1_val = always_redraw(
            lambda: build_elbow_connector(
                p1["bg"].get_bottom() + DOWN * 0.10,
                v1["box"].get_top() + UP * 0.05,
                C_P1,
                opacity=0.16 * a_val(),
                lock_x=p1["bg"].get_center()[0],
            )
        )
        conn_p2_val = always_redraw(
            lambda: build_elbow_connector(
                p2["bg"].get_bottom() + DOWN * 0.10,
                v2["box"].get_top() + UP * 0.05,
                C_P2,
                opacity=0.16 * a_val(),
                lock_x=p2["bg"].get_center()[0],
            )
        )
        conn_term_notes = always_redraw(
            lambda: build_elbow_connector(
                terminal["plate"].get_bottom() + DOWN * 0.05,
                notes["chip"].get_top() + UP * 0.05,
                C_GOLD,
                opacity=0.12 * a_val(),
                lock_x=0.0,
            )
        )

        fx_layer.add(conn_ann_spine, conn_spine_p1, conn_spine_p2, conn_p1_val, conn_p2_val, conn_term_notes)

        # ================================================================
        # ENTRANCE (PATCH: no flash + everything enters on-screen)
        # ================================================================
        hook_t0 = global_start_t0

        # 1) HARD FIX: intro खत्म होते ही UI "already visible" नहीं होना चाहिए
        for mob in [
            sub, scan_line,
            ann["group"],
            p1["group"], p2["group"],
            v1["group"], v2["group"],
            terminal["group"],
            notes["group"],
            scoreboard["group"],
        ]:
            mob.set_opacity(0.0)

        tL.set_opacity(0.0)
        tR.set_opacity(0.0)
        vs_grp.set_opacity(0.0)
        header.set_opacity(1.0)

        spine.set_opacity(0.0)
        conn_alpha.set_value(0.0)

        # 2) Prep: slide offsets
        try:
            tL.shift(LEFT * 0.55)
            tR.shift(RIGHT * 0.55)
        except Exception:
            pass

        try:
            vs_grp.shift(UP * 0.28)
        except Exception:
            pass

        scan_line.shift(DOWN * 0.10)
        sub.shift(DOWN * 0.12)

        ann["group"].shift(UP * 0.22)
        p1["group"].shift(LEFT * 0.55)
        p2["group"].shift(RIGHT * 0.55)

        v1["group"].shift(DOWN * 0.18)
        v2["group"].shift(DOWN * 0.18)
        terminal["group"].shift(DOWN * 0.14)
        notes["group"].shift(DOWN * 0.14)
        scoreboard["group"].shift(DOWN * 0.14)

        # ----------------------------------------------------------------
        # [HOOK SEGMENT] -> 3) TITLE entrance
        # ----------------------------------------------------------------
        hook_total = TL.seg_total(hook_seg, 3.8)
        hook_act = clamp(hook_total * 0.85, 0.60, 2.5)

        anims = []
        try:
            anims += [
                tL.animate.shift(RIGHT * 0.55).set_opacity(1.0),
                tR.animate.shift(LEFT * 0.55).set_opacity(1.0),
                vs_grp.animate.shift(DOWN * 0.28).set_opacity(1.0),
            ]
        except Exception:
            anims += [header.animate.set_opacity(1.0)]

        sfx.mark("ui_pop", gain_db=-10, meta={"segment": hook_seg, "at": "title_in"})
        self.play(
            *anims,
            run_time=hook_act * 0.5,
            rate_func=rf.ease_out_cubic,
        )
        self.play(
            scan_line.animate.shift(UP * 0.10).set_opacity(1.0),
            run_time=hook_act * 0.3,
            rate_func=rf.ease_out_cubic,
        )
        self.play(
            sub.animate.shift(UP * 0.12).set_opacity(0.90),
            run_time=hook_act * 0.2,
            rate_func=rf.ease_out_cubic,
        )
        
        TL.consume(hook_seg, float(self.time) - hook_t0)
        hold_breathing(self, TL.remaining(hook_seg), focus=header, text="INITIALIZING BOOT SEQUENCE")

        # ----------------------------------------------------------------
        # [SETUP SEGMENT] -> 5-8) Metrics / Cards / Terminals
        # ----------------------------------------------------------------
        setup_t0 = float(self.time)
        setup_total = TL.seg_total(setup_seg, 3.8)
        setup_act = clamp(setup_total * 0.85, 0.80, 2.8)

        sfx.mark("scan_tick", gain_db=-14, meta={"segment": setup_seg, "at": "metrics_down"})
        self.play(
            ann["group"].animate.shift(DOWN * 0.22).set_opacity(1.0),
            run_time=setup_act * 0.20,
            rate_func=rf.ease_out_cubic,
        )
        self.play(
            spine.animate.set_opacity(1.0),
            conn_alpha.animate.set_value(1.0),
            run_time=setup_act * 0.15,
            rate_func=rf.ease_out_cubic,
        )

        sfx.mark("impact_soft", gain_db=-12, meta={"segment": setup_seg, "at": "cards_in"})
        self.play(
            p1["group"].animate.shift(RIGHT * 0.55).set_opacity(1.0),
            p2["group"].animate.shift(LEFT * 0.55).set_opacity(1.0),
            run_time=setup_act * 0.35,
            rate_func=rf.ease_out_cubic,
        )

        sfx.mark("ui_tick", gain_db=-15, meta={"segment": setup_seg, "at": "bottom_stack"})
        self.play(
            LaggedStart(
                v1["group"].animate.shift(UP * 0.18).set_opacity(1.0),
                v2["group"].animate.shift(UP * 0.18).set_opacity(1.0),
                terminal["group"].animate.shift(UP * 0.14).set_opacity(1.0),
                notes["group"].animate.shift(UP * 0.14).set_opacity(1.0),
                scoreboard["group"].animate.shift(UP * 0.14).set_opacity(1.0),
                lag_ratio=0.10,
            ),
            run_time=setup_act * 0.30,
            rate_func=rf.ease_out_cubic,
        )

        # PATCH #2: SYSTEM STATUS TICKER (1-line)
        def set_status(msg: str, *, color=WHITE):
            msg = (msg or "").strip()
            if not msg:
                msg = "system: ok | backend: online"

            new_line = safe_text(f"• {msg}", font="Consolas", font_size=16, color=color, weight=BOLD)
            if new_line.width > (notes["chip"].width - 0.65):
                new_line.scale_to_fit_width(notes["chip"].width - 0.65)

            new_line.move_to(notes["line"].get_center())
            new_line.align_to(notes["chip"].get_left() + RIGHT * 0.20, LEFT)

            self.play(Transform(notes["line"], new_line), run_time=0.20, rate_func=rf.ease_out_cubic)

        set_status("system boot: ready | backend: online | awaiting round 1", color=C_SUB)
        
        TL.consume(setup_seg, float(self.time) - setup_t0)
        hold_breathing(self, TL.remaining(setup_seg), focus=header, text="SYSTEM STATUS: ONLINE")

        # ----------------------------------------------------------------
        # ROUND LOOP
        # ----------------------------------------------------------------
        n_rounds = max(1, len(df))
        p1_pts = 0.0
        p2_pts = 0.0

        def set_text(mobj: Mobject, txt: str, *, font="Consolas", font_size=14, color=C_SUB, weight=BOLD):
            new = safe_text(txt, font=font, font_size=font_size, color=color, weight=weight).move_to(mobj.get_center())
            mobj.become(new)

        def update_score_text():
            set_text(scoreboard["score"], f"{fmt_pts(p1_pts)}  —  {fmt_pts(p2_pts)}", font="Consolas", font_size=26, color=WHITE, weight=BOLD)
            set_text(p1["score"], fmt_pts(p1_pts), font="Consolas", font_size=22, color=WHITE, weight=BOLD)
            set_text(p2["score"], fmt_pts(p2_pts), font="Consolas", font_size=22, color=WHITE, weight=BOLD)

        update_score_text()

        def set_terminal_lines(l1: str, l2: str, l3: str, color: str):
            pad_x = float(terminal["pad_x"])
            new1 = safe_text(l1, font="Consolas", font_size=18, color=WHITE, weight=BOLD)
            if new1.width > (terminal["plate"].width - 0.55):
                new1.scale_to_fit_width(terminal["plate"].width - 0.55)
            new2 = safe_text(l2, font="Consolas", font_size=14, color=C_SUB, weight=BOLD)
            new3 = safe_text(l3, font="Consolas", font_size=14, color=C_SUB, weight=BOLD)

            new1.move_to(terminal["line1"].get_center()).align_to(terminal["plate"].get_left() + RIGHT * pad_x, LEFT)
            new2.move_to(terminal["line2"].get_center()).align_to(terminal["plate"].get_left() + RIGHT * pad_x, LEFT)
            new3.move_to(terminal["line3"].get_center()).align_to(terminal["plate"].get_left() + RIGHT * pad_x, LEFT)

            terminal["plate"].set_stroke(color, 3.0, 0.96)
            terminal["glow"].set_stroke(color, 26, 0.22)
            terminal["dot"].set_color(color)

            self.play(
                Transform(terminal["line1"], new1),
                Transform(terminal["line2"], new2),
                Transform(terminal["line3"], new3),
                run_time=0.20,
                rate_func=rf.ease_out_cubic,
            )
            self.play(Flash(terminal["plate"], color=color, line_length=0.35, num_lines=8), run_time=0.18)

        def terminal_scanning():
            set_terminal_lines(
                "AI TRIBUNAL SCANNING",
                "log: processing next metric...",
                "status: online",
                C_GOLD,
            )

        ROUND_HOLD = 0.45
        terminal_scanning()

        for i, row in df.iterrows():
            seg_name = round_segments[i] if i < len(round_segments) else f"round_{i+1}"
            r_total = TL.seg_total(seg_name, 4.2)
            metric_t0 = float(self.time)

            metric = str(row.get("Metric", "")).strip().upper()
            p1_val = str(row.get("P1_Value", "")).strip()
            p2_val = str(row.get("P2_Value", "")).strip()
            winner = int(row.get("Winner", 0))
            emoji = str(row.get("Emoji", "")).strip()
            category = str(row.get("Category", "")).strip().upper()
            weight = float(row.get("Weight", 1.0))

            top_line = f"ROUND {i+1}/{n_rounds}   |   CATEGORY: {category or '—'}"
            main_line = f"{(emoji + ' ') if emoji else ''}{ellipsize(metric, 24)}"
            sub_line = f"Weight: {weight:.1f}"

            new_top = safe_text(top_line, font="Consolas", font_size=14, color=C_SUB, weight=BOLD).move_to(ann["top"].get_center())
            new_main = safe_text(main_line, font="Montserrat", font_size=36, color=WHITE, weight=BOLD).move_to(ann["main"].get_center())
            if new_main.width > (ann["outer"].width - 0.55):
                new_main.scale_to_fit_width(ann["outer"].width - 0.55)
            new_sub = safe_text(sub_line, font="Consolas", font_size=14, color=C_SUB, weight=BOLD).move_to(ann["sub"].get_center())

            new_v1 = safe_text(p1_val, font_size=30, color=C_MAIN, weight=BOLD).move_to(v1["txt"].get_center())
            if new_v1.width > (v1["box"].width - 0.35):
                new_v1.scale_to_fit_width(v1["box"].width - 0.35)

            new_v2 = safe_text(p2_val, font_size=30, color=C_MAIN, weight=BOLD).move_to(v2["txt"].get_center())
            if new_v2.width > (v2["box"].width - 0.35):
                new_v2.scale_to_fit_width(v2["box"].width - 0.35)

            sfx.mark("ui_tick", gain_db=-14, meta={"segment": seg_name, "action": "metric_reveal"})
            act_reveal = clamp(r_total * 0.15, 0.25, 0.45)
            self.play(
                Transform(ann["top"], new_top),
                Transform(ann["main"], new_main),
                Transform(ann["sub"], new_sub),
                Transform(v1["txt"], new_v1),
                Transform(v2["txt"], new_v2),
                ann["glow"].animate.set_stroke(opacity=0.26),
                run_time=act_reveal * 0.65,
                rate_func=rf.ease_out_cubic,
            )
            self.play(ann["glow"].animate.set_stroke(opacity=0.22), run_time=act_reveal * 0.35, rate_func=rf.ease_in_out_sine)

            # PATCH #2: status (backend/system feel)
            set_status(f"scanning: r{i+1}/{n_rounds} | stream: stable | parsing metric…", color=C_SUB)

            # decision
            if winner in (1, 2):
                add_pts = max(0.0, float(weight))
                if add_pts < 0.5:
                    add_pts = 1.0

                if winner == 1:
                    p1_pts += add_pts
                    win_obj, lose_obj = p1, p2
                    win_name = p1_name
                else:
                    p2_pts += add_pts
                    win_obj, lose_obj = p2, p1
                    win_name = p2_name

                set_terminal_lines(
                    "RESULT: POINT AWARDED",
                    f"+{fmt_pts(add_pts)}  ->  {win_name.upper()}",
                    f"metric: {ellipsize(metric, 22)}",
                    C_WIN,
                )

                # PATCH #4: round-winner highlight (premium but minimal)
                WIN_SCALE = 1.08
                LOSE_SCALE = 0.96

                act_win = clamp(r_total * 0.25, 0.30, 0.60)
                sfx.mark("impact_soft", gain_db=-8, meta={"segment": seg_name, "action": "winner_scale"})

                self.play(
                    win_obj["group"].animate.scale(WIN_SCALE),
                    win_obj["glow"].animate.set_stroke(C_WIN, 26, 0.28),
                    win_obj["frame"].animate.set_stroke(C_WIN, 3.6, 0.98),
                    win_obj["corners"].animate.set_stroke(C_WIN, 5.8, 0.98),
                    lose_obj["group"].animate.scale(LOSE_SCALE).set_opacity(0.72),
                    lose_obj["glow"].animate.set_stroke(lose_obj["accent"], 20, 0.14),
                    lose_obj["frame"].animate.set_stroke(lose_obj["accent"], 2.8, 0.75),
                    run_time=act_win * 0.65,
                    rate_func=rf.ease_out_cubic,
                )
                self.play(
                    Flash(win_obj["frame"], color=C_WIN, line_length=0.35, num_lines=10),
                    run_time=act_win * 0.35,
                    rate_func=rf.ease_out_cubic,
                )

                update_score_text()
                act_score = clamp(r_total * 0.15, 0.20, 0.40)
                sfx.mark("ui_pop", gain_db=-10, meta={"segment": seg_name, "action": "score_update"})
                self.play(
                    scoreboard["glow"].animate.set_stroke(opacity=0.26),
                    Flash(scoreboard["score"], color=C_WIN, line_length=0.40, num_lines=8),
                    run_time=act_score * 0.65,
                    rate_func=rf.ease_out_cubic,
                )
                self.play(scoreboard["glow"].animate.set_stroke(opacity=0.20), run_time=act_score * 0.35, rate_func=rf.ease_in_out_sine)

                # PATCH #2: status after decision
                set_status("decision committed | backend: ok | preparing next round…", color=C_SUB)

                # Consume time used by main animations
                TL.consume(seg_name, float(self.time) - metric_t0)
                
                # Reserve time for reset animation, pad remaining
                reset_rt = 0.26
                pad_time = max(0.0, TL.remaining(seg_name) - reset_rt)
                
                hold_breathing(self, pad_time, focus=win_obj["group"])

                # PATCH #4: reset to neutral (still alive, not dull)
                reset_t0 = float(self.time)
                self.play(
                    win_obj["group"].animate.scale(1 / WIN_SCALE),
                    win_obj["glow"].animate.set_stroke(win_obj["accent"], 20, 0.20),
                    win_obj["frame"].animate.set_stroke(win_obj["accent"], 2.8, 0.90),
                    win_obj["corners"].animate.set_stroke(win_obj["accent"], 5.2, 0.95),
                    lose_obj["group"].animate.scale(1 / LOSE_SCALE).set_opacity(1.0),
                    lose_obj["glow"].animate.set_stroke(lose_obj["accent"], 20, 0.20),
                    lose_obj["frame"].animate.set_stroke(lose_obj["accent"], 2.8, 0.90),
                    run_time=reset_rt,
                    rate_func=rf.ease_in_out_sine,
                )
                TL.consume(seg_name, float(self.time) - reset_t0)

                terminal_scanning()

            else:
                set_terminal_lines(
                    "RESULT: DRAW",
                    "no points awarded",
                    f"metric: {ellipsize(metric, 22)}",
                    C_GOLD,
                )

                act_draw = clamp(r_total * 0.15, 0.20, 0.35)
                sfx.mark("impact_soft", gain_db=-14, meta={"segment": seg_name, "action": "draw_result"})
                self.play(
                    p1["glow"].animate.set_stroke(C_P1, 22, 0.24),
                    p2["glow"].animate.set_stroke(C_P2, 22, 0.24),
                    run_time=act_draw,
                    rate_func=rf.ease_out_cubic,
                )
                
                TL.consume(seg_name, float(self.time) - metric_t0)
                
                reset_rt = 0.18
                pad_time = max(0.0, TL.remaining(seg_name) - reset_rt)
                
                hold_breathing(self, pad_time, focus=ann["group"])
                
                reset_t0 = float(self.time)
                self.play(
                    p1["glow"].animate.set_stroke(C_P1, 22, 0.22),
                    p2["glow"].animate.set_stroke(C_P2, 22, 0.22),
                    run_time=reset_rt,
                    rate_func=rf.ease_in_out_sine,
                )
                TL.consume(seg_name, float(self.time) - reset_t0)

                # PATCH #2: status after draw
                set_status("draw confirmed | backend: ok | preparing next round…", color=C_SUB)

                terminal_scanning()
        
        # Ghost Padding Loop 
        for ghost_i in range(len(df), len(round_segments)):
            seg_key = round_segments[ghost_i]
            g_t0 = float(self.time)
            TL.consume(seg_key, float(self.time) - g_t0)
            hold_breathing(self, TL.remaining(seg_key))

        # ----------------------------------------------------------------
        # OUTRO (PATCH #5: loser truly gone + winner scale + no floating VS)
        # ----------------------------------------------------------------
        winner_t0 = float(self.time)
        final = 0
        if p1_pts > p2_pts:
            final = 1
        elif p2_pts > p1_pts:
            final = 2

        # stop VS updater so diamond never floats/rotates later
        try:
            vs_box.clear_updaters()
        except Exception:
            pass
        try:
            vs_grp.clear_updaters()
        except Exception:
            pass

        if final == 0:
            act_fade = clamp(TL.seg_total(winner_seg, 3.8) * 0.30, 0.35, 0.75)
            sfx.mark("outro_swipe", gain_db=-10, meta={"segment": winner_seg})
            self.play(
                header.animate.set_opacity(0.0),
                sub.animate.set_opacity(0.0),
                scan_line.animate.set_opacity(0.0),
                ann["group"].animate.set_opacity(0.0),
                v1["group"].animate.set_opacity(0.0),
                v2["group"].animate.set_opacity(0.0),
                terminal["group"].animate.set_opacity(0.0),
                notes["group"].animate.set_opacity(0.0),
                scoreboard["group"].animate.set_opacity(0.0),
                p1["group"].animate.set_opacity(0.0),
                p2["group"].animate.set_opacity(0.0),
                run_time=act_fade,
                rate_func=rf.ease_in_out_sine,
            )
            conn_alpha.set_value(0.0)
            spine.set_opacity(0.0)

            draw_txt = safe_text("IT'S A DRAW!", font="Montserrat", font_size=58, color=WHITE, weight=BOLD)
            draw_txt.set_z_index(380)
            act_draw = clamp(TL.seg_total(winner_seg) * 0.40, 0.45, 0.85)
            sfx.mark("ui_pop", gain_db=-8, meta={"segment": winner_seg})
            self.play(FadeIn(draw_txt, shift=UP * 0.10), run_time=act_draw, rate_func=rf.ease_out_cubic)
            self.play(Flash(draw_txt, color=C_GOLD, line_length=0.7, num_lines=12), run_time=0.35)
            
            TL.consume(winner_seg, float(self.time) - winner_t0)
            hold_breathing(self, TL.remaining(winner_seg), focus=draw_txt, text="COMPILING DIAGNOSTICS")
            
            outro_t0 = float(self.time)
            TL.consume(outro_seg, float(self.time) - outro_t0)
            hold_breathing(self, TL.remaining(outro_seg), focus=draw_txt, text="SYSTEM SHUTDOWN")
            
            sfx.flush()
            return

        win = p1 if final == 1 else p2
        lose = p2 if final == 1 else p1
        win_color = win["accent"]
        loser_slot = lose["bg"].get_center()

        w_total = TL.seg_total(winner_seg, 3.8)
        act_fade = clamp(w_total * 0.20, 0.25, 0.60)
        
        # fade UI fast
        sfx.mark("outro_swipe", gain_db=-14, meta={"segment": winner_seg})
        self.play(
            header.animate.set_opacity(0.0),
            sub.animate.set_opacity(0.0),
            scan_line.animate.set_opacity(0.0),
            ann["group"].animate.set_opacity(0.0),
            v1["group"].animate.set_opacity(0.0),
            v2["group"].animate.set_opacity(0.0),
            terminal["group"].animate.set_opacity(0.0),
            notes["group"].animate.set_opacity(0.0),
            scoreboard["group"].animate.set_opacity(0.0),
            run_time=act_fade,
            rate_func=rf.ease_in_out_sine,
        )

        # connectors/spine: fade + HARD remove (always_redraw safety)
        self.play(conn_alpha.animate.set_value(0.0), spine.animate.set_opacity(0.0), run_time=act_fade * 0.5, rate_func=rf.ease_in_out_sine)
        self.remove(conn_ann_spine, conn_spine_p1, conn_spine_p2, conn_p1_val, conn_p2_val, conn_term_notes, spine)

        # PATCH #3/#5: loser MUST disappear (FadeOut + remove)
        act_lose = clamp(w_total * 0.15, 0.25, 0.55)
        self.play(
            FadeOut(lose["group"], scale=0.92),
            run_time=act_lose,
            rate_func=rf.ease_in_out_sine,
        )
        self.remove(lose["group"])

        # winner scale only (no move)
        act_win = clamp(w_total * 0.25, 0.40, 0.80)
        sfx.mark("winner_rise", gain_db=-8, meta={"segment": winner_seg})
        self.play(
            win["group"].animate.scale(1.16),
            win["frame"].animate.set_stroke(C_WIN, 3.8, 0.98),
            win["glow"].animate.set_stroke(C_WIN, 26, 0.26),
            run_time=act_win,
            rate_func=rf.ease_out_cubic,
        )

        power1 = safe_text("WINNER CONFIRMED", font="Consolas", font_size=18, color=C_SUB, weight=BOLD)
        power2 = safe_text("YOUR WINNER", font="Montserrat", font_size=30, color=WHITE, weight=BOLD)
        power3 = safe_text(win["name"].upper(), font="Montserrat", font_size=56, color=win_color, weight=BOLD)

        power = VGroup(power1, power2, power3).arrange(DOWN, buff=0.10)
        power.move_to(loser_slot)
        power.set_z_index(390)

        act_pow = clamp(w_total * 0.35, 0.55, 1.25)
        sfx.mark("impact_soft", gain_db=-10, meta={"segment": winner_seg, "at": "winner_announcement"})
        self.play(FadeIn(power1, shift=UP * 0.08), run_time=act_pow * 0.20, rate_func=rf.ease_out_cubic)
        self.play(Write(power2), run_time=act_pow * 0.35, rate_func=rf.ease_out_cubic)
        self.play(Write(power3), run_time=act_pow * 0.45, rate_func=rf.ease_out_cubic)
        self.play(Flash(power3, color=win_color, line_length=0.70, num_lines=14), run_time=0.35)
        
        TL.consume(winner_seg, float(self.time) - winner_t0)
        hold_breathing(self, TL.remaining(winner_seg), focus=win["group"], text="LOCKING WINNER DATA")
        
        # FINAL OUTRO PAD
        outro_t0 = float(self.time)
        TL.consume(outro_seg, float(self.time) - outro_t0)
        hold_breathing(self, TL.remaining(outro_seg), focus=win["group"], text="SYSTEM SHUTDOWN")

        for seg in round_segments:
            _ = TL.remaining(seg) 
            
        try:
            sfx.flush()
        except Exception:
            pass
