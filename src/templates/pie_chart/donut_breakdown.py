import os
import sys
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from manim import *
from manim import rate_functions as rf

# ==========================
# Optional project imports
# ==========================
HAS_PROJECT = True
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    sys.path.append(project_root)

    from src.config import DATA_DIR, BACKGROUND_COLOR, Theme, FONT_DISPLAY  # type: ignore
    from src.utils import IntroManager, get_safe_frame, add_cinematic_background  # type: ignore
except Exception:
    HAS_PROJECT = False
    DATA_DIR = "."
    BACKGROUND_COLOR = "#0A0A0A"
    FONT_DISPLAY = "Montserrat"

    class Theme:
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#CCCCCC"
        TEXT_DIM = "#9AA3AD"
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_ORANGE = "#FF9900"
        NEON_GREEN = "#00FF66"
        NEON_YELLOW = "#FFE14D"

    def get_safe_frame(margin: float = 0.70) -> Dict[str, float]:
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

    def add_cinematic_background(*args, **kwargs):
        return None

import json
from pathlib import Path

# --- SYNC HELPERS (direct imports, NO try/except) ---
from src.sync.job import load_job
from src.sync.timeline import Timeline, clamp as _tl_clamp
from src.sync.retention import hold_breathing, banner_scan_hold
from src.sfx.engine import SFXEngine

# ============================================================
# SFX MARKS WRITER  (matches bar_chart.py exactly)
# - writes: jobs/<job>/output/sfx_marks.json
# - main.py will pick this up and mix SFX
# ============================================================
class SFXMarksWriter:
    def __init__(self, scene: Scene, job_dir, template_id="donut_breakdown", out_rel="output/sfx_marks.json"):
        self.scene = scene
        self.template_id = template_id
        self.out_path = Path(str(job_dir)) / out_rel if job_dir else None
        self.marks = []

    def mark(self, key: str, gain_db: float = 0.0, offset: float = 0.0, meta: dict | None = None):
        t = float(self.scene.time) + float(offset)
        ev = {"t": t, "key": str(key), "gain_db": float(gain_db)}
        if meta:
            ev["meta"] = meta
        self.marks.append(ev)

    def flush(self):
        if self.out_path is None:
            return
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "template_id": self.template_id,
            "marks": self.marks,
        }
        with self.out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[OK] Wrote sfx_marks.json: {self.out_path} ({len(self.marks)} marks)")


# ==========================
# Helpers / constants
# ==========================
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")

# Fallback (last resort)
FALLBACK_COLORS = [
    "#2DD4FF",  # cyan
    "#A78BFA",  # purple
    "#FB7185",  # rose
    "#FBBF24",  # amber
    "#34D399",  # emerald
    "#FDE047",  # yellow
    "#60A5FA",  # blue
    "#F472B6",  # pink
    "#4ADE80",  # green
    "#FDBA74",  # orange
]

# Premium preset palette (theme-friendly, softer, "premium" feel)
# Priority: PRESET -> FALLBACK (CSV only if USE_CSV_COLORS=1)
PRESET_BY_GROUP = {
    "PREMIUM": ["#53D9FF", "#8E84FF", "#6FB2FF", "#42C8FF"],
    "VALUE": ["#FF6FA1", "#FF9B7A", "#FFC36A", "#FFE08A"],
    "OTHER": ["#4CE6B4", "#7DE3FF", "#A7F0D7", "#B7C8FF"],
    "DEFAULT": ["#53D9FF", "#8E84FF", "#FF6FA1", "#FFC36A", "#4CE6B4", "#FFE08A"],
}


def is_hex(s: Optional[str]) -> bool:
    return isinstance(s, str) and bool(_HEX_RE.match(s.strip()))


def clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def _hex_to_rgb01(h: str) -> Optional[np.ndarray]:
    try:
        s = h.strip()
        if not is_hex(s):
            return None
        if len(s) == 4:  # #RGB
            r = int(s[1] * 2, 16)
            g = int(s[2] * 2, 16)
            b = int(s[3] * 2, 16)
        else:
            r = int(s[1:3], 16)
            g = int(s[3:5], 16)
            b = int(s[5:7], 16)
        return np.array([r, g, b], dtype=float) / 255.0
    except Exception:
        return None


def _rgb01_to_hex(rgb: np.ndarray) -> str:
    rgb = np.clip(rgb, 0.0, 1.0)
    r, g, b = (rgb * 255.0 + 0.5).astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def lighten_hex(hex_color: str, amount: float = 0.35) -> str:
    """
    amount: 0..1 (0 = no change, 1 = white)
    """
    rgb = _hex_to_rgb01(hex_color)
    if rgb is None:
        return hex_color
    w = np.array([1.0, 1.0, 1.0], dtype=float)
    out = rgb * (1.0 - amount) + w * amount
    return _rgb01_to_hex(out)


def darken_hex(hex_color: str, amount: float = 0.20) -> str:
    """
    amount: 0..1 (0 = no change, 1 = black)
    """
    rgb = _hex_to_rgb01(hex_color)
    if rgb is None:
        return hex_color
    k = np.array([0.0, 0.0, 0.0], dtype=float)
    out = rgb * (1.0 - amount) + k * amount
    return _rgb01_to_hex(out)


def blend_hex(a: str, b: str, t: float = 0.18) -> str:
    """
    Blend color a towards b by t (0..1).
    Used to keep slice palette cohesive with Theme NEON_BLUE.
    """
    ra = _hex_to_rgb01(a)
    rb = _hex_to_rgb01(b)
    if ra is None or rb is None:
        return a
    t = clamp(t, 0.0, 1.0)
    out = ra * (1.0 - t) + rb * t
    return _rgb01_to_hex(out)


def parse_meta_first_line(path: str) -> Dict[str, str]:
    meta = {
        "TITLE": "MARKET SHARE 2025",
        "SUB": "Global smartphone shipments",
        "UNIT": "%",
        "TOP": "10",
        "MODE": "DONUT",
        "OTHERS_MIN_PCT": "0",  # if >0, auto-merge tiny segments into Others
        "USE_CSV_COLORS": "0",  # 0 = ignore CSV colors (recommended), 1 = allow CSV override
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("#"):
            first = first[1:]
            parts = [p.strip() for p in first.split(",") if p.strip()]
            for p in parts:
                if "=" in p:
                    k, v = p.split("=", 1)
                    meta[k.strip().upper()] = v.strip()
    except Exception:
        pass
    return meta


def normalize_to_pct(values: List[float]) -> List[float]:
    vals = [float(v) if np.isfinite(v) else 0.0 for v in values]
    s = float(np.sum(vals)) if vals else 0.0
    if s <= 0:
        return [0.0 for _ in vals]
    # If already ~100
    if 90.0 <= s <= 110.0:
        return [float(v) for v in vals]
    return [float(v) / s * 100.0 for v in vals]


def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, str) and x.strip() == "":
            return None
        if pd.isna(x):
            return None
        v = float(str(x).replace("%", "").replace(",", "").strip())
        if not np.isfinite(v):
            return None
        return v
    except Exception:
        return None


def read_market_csv(
    csv_path: str,
) -> Tuple[Dict[str, str], List[str], List[float], List[str], List[str]]:
    """
    Returns: meta, names, values, colors, groups
    """
    meta = parse_meta_first_line(csv_path)

    # Default dataset if missing file
    if not os.path.exists(csv_path):
        names = ["Apple", "Samsung", "Xiaomi", "Oppo", "Vivo", "Others"]
        vals = [35, 25, 15, 10, 8, 7]
        groups = ["Premium", "Premium", "Value", "Value", "Value", "Other"]
        cols = ["" for _ in names]  # empty = trigger presets
        return meta, names, vals, cols, groups

    df = pd.read_csv(csv_path, comment="#")
    df.columns = [str(c).strip() for c in df.columns]
    cols_map = {c.lower().strip(): c for c in df.columns}

    cat_col = cols_map.get("category") or cols_map.get("name") or cols_map.get("label") or df.columns[0]
    val_col = cols_map.get("value") or cols_map.get("val") or cols_map.get("percent") or cols_map.get("pct") or (
        df.columns[1] if len(df.columns) > 1 else df.columns[0]
    )
    col_col = cols_map.get("color") or cols_map.get("hex") or cols_map.get("colour")
    grp_col = cols_map.get("group")
    ord_col = cols_map.get("order")

    d = df.copy()
    d[cat_col] = d[cat_col].astype(str).str.strip()

    d[val_col] = d[val_col].apply(_safe_float)
    d = d.dropna(subset=[val_col]).copy()
    d[val_col] = d[val_col].astype(float)
    d = d[d[val_col] > 0].copy()

    if grp_col is None:
        d["_Group"] = "Default"
        grp_col = "_Group"
    else:
        # avoid "nan" strings
        d[grp_col] = d[grp_col].where(~pd.isna(d[grp_col]), "Default")
        d[grp_col] = d[grp_col].astype(str).str.strip()
        d[grp_col] = d[grp_col].replace({"": "Default", "nan": "Default", "NaN": "Default", "None": "Default"})
        d[grp_col] = d[grp_col].fillna("Default")

    if ord_col is not None:
        d[ord_col] = pd.to_numeric(d[ord_col], errors="coerce").fillna(10_000)
        d = d.sort_values(by=[ord_col, val_col], ascending=[True, False], kind="mergesort")
    else:
        d = d.sort_values(by=[val_col], ascending=False, kind="mergesort")

    try:
        top = int(float(meta.get("TOP", "10")))
    except Exception:
        top = 10
    top = int(np.clip(top, 2, 10))

    names = d[cat_col].astype(str).tolist()
    vals = d[val_col].astype(float).tolist()
    groups = d[grp_col].astype(str).tolist()

    if col_col is not None and col_col in d.columns:
        rawc = d[col_col].astype(str).tolist()
        colors = [(s.strip() if is_hex(s.strip()) else "") for s in rawc]
    else:
        colors = ["" for _ in names]

    # Merge into Others if needed
    if len(names) > top:
        keep_n = names[: top - 1]
        keep_v = vals[: top - 1]
        keep_c = colors[: top - 1]
        keep_g = groups[: top - 1]

        rest_sum = float(np.sum(vals[top - 1 :]))
        keep_n.append("Others")
        keep_v.append(rest_sum)
        keep_c.append("")  # keep empty -> preset or fallback
        keep_g.append("Other")

        names, vals, colors, groups = keep_n, keep_v, keep_c, keep_g

    return meta, names, vals, colors, groups


def _merge_tiny_into_others(
    names: List[str],
    vals: List[float],
    colors: List[str],
    groups: List[str],
    min_pct: float,
) -> Tuple[List[str], List[float], List[str], List[str]]:
    if min_pct <= 0 or not names or not vals:
        return names, vals, colors, groups

    total = float(np.sum(vals)) if vals else 0.0
    if total <= 0:
        return names, vals, colors, groups

    keep_n, keep_v, keep_c, keep_g = [], [], [], []
    other_sum = 0.0
    for n, v, c, g in zip(names, vals, colors, groups):
        pct = (float(v) / total) * 100.0
        if pct < min_pct and str(n).strip().lower() != "others":
            other_sum += float(v)
        else:
            keep_n.append(n)
            keep_v.append(float(v))
            keep_c.append(c)
            keep_g.append(g)

    if other_sum > 0:
        keep_n.append("Others")
        keep_v.append(other_sum)
        keep_c.append("")  # let presets/fallback handle
        keep_g.append("Other")

    return keep_n, keep_v, keep_c, keep_g


def pick_premium_color(
    name: str,
    group: str,
    csv_color: str,
    i: int,
    used_by_group: Dict[str, int],
    allow_csv: bool,
    theme_blue: str,
) -> Tuple[str, str]:
    """
    Returns (color_hex, source_str)
    Default priority: PRESET -> FALLBACK
    Optional override: CSV (only if allow_csv=True and csv has valid hex)
    Always: lightly tint towards theme_blue to keep harmony.
    """
    gkey = (group or "Default").strip().upper()
    if gkey not in PRESET_BY_GROUP:
        gkey = "DEFAULT"

    # Optional CSV override (ONLY if allowed)
    if allow_csv and is_hex(csv_color):
        col = csv_color.strip()
        return blend_hex(col, theme_blue, 0.14), "CSV"

    # PRESET
    try:
        palette = PRESET_BY_GROUP.get(gkey, PRESET_BY_GROUP["DEFAULT"])
        k = used_by_group.get(gkey, 0)
        used_by_group[gkey] = k + 1
        col = palette[k % len(palette)]
        if is_hex(col):
            return blend_hex(col, theme_blue, 0.14), f"PRESET({gkey})"
    except Exception:
        pass

    # FALLBACK
    col = FALLBACK_COLORS[i % len(FALLBACK_COLORS)]
    return blend_hex(col, theme_blue, 0.14), "FALLBACK"


# ==========================
# Text-fit helpers (safe)
# ==========================
def _safe_text(
    txt: str,
    font: str,
    font_size: int,
    color: str,
    weight=None,
) -> Text:
    """
    IMPORTANT: never pass weight=None into Text (prevents PANGO NoneType concat issue).
    """
    if weight is None:
        return Text(txt, font=font, font_size=font_size, color=color)
    return Text(txt, font=font, font_size=font_size, color=color, weight=weight)


def text_ellipsize_to_width(
    s: str,
    font: str,
    font_size: int,
    max_width: float,
    color: str,
    weight=None,
    min_keep: int = 4,
) -> Text:
    base = str(s) if s is not None else ""
    t = _safe_text(base, font=font, font_size=font_size, color=color, weight=weight)
    if t.width <= max_width:
        return t

    raw = base
    for _ in range(60):
        if len(raw) <= min_keep:
            break
        raw = raw[:-1].rstrip()
        cand = raw + "…"
        t2 = _safe_text(cand, font=font, font_size=font_size, color=color, weight=weight)
        if t2.width <= max_width:
            return t2

    # last resort: scale down
    if t.width > max_width and t.width > 1e-6:
        t.scale_to_fit_width(max_width)
    return t


# ==========================
# Visual builders
# ==========================
def build_background(sf: Dict[str, float], center: np.ndarray, outer_r: float) -> VGroup:
    """
    Premium HUD background (full-screen grid):
    - 2-layer grid (major + minor) across FULL frame
    - ambient donut plate + controlled glow
    - vignette + edge-dark
    - subtle HUD frame stroke + corner ticks
    - light particles
    """
    g = VGroup().set_z_index(1)

    fw = float(config.frame_width)
    fh = float(config.frame_height)
    fb = {
        "left": -fw / 2,
        "right": fw / 2,
        "bottom": -fh / 2,
        "top": fh / 2,
        "cx": 0.0,
        "cy": 0.0,
        "w": fw,
        "h": fh,
    }

    base_blue = getattr(Theme, "NEON_BLUE", "#2DD4FF")

    tint = Rectangle(width=fw + 0.1, height=fh + 0.1).set_z_index(0)
    tint.set_fill(color=darken_hex(base_blue, 0.62), opacity=0.07)  # 0.05–0.09 sweet spot
    tint.set_stroke(width=0)
    tint.move_to([0, 0, 0])

    plate = Circle(radius=outer_r * 2.10).set_z_index(0)
    plate.set_fill(color=darken_hex(base_blue, 0.62), opacity=0.16)  # was 0.12
    plate.set_stroke(width=0)
    plate.move_to(center)

    glow = Circle(radius=outer_r * 1.88).set_z_index(0)
    glow.set_fill(color=base_blue, opacity=0.035)  # was 0.045 (dial/bkg too bright feel reduce)
    glow.set_stroke(width=0)
    glow.move_to(center)

    # Keep vignette strong (depth), but slightly less crushing
    vignette = Circle(radius=max(fw, fh) * 0.78).set_z_index(0)
    vignette.set_fill(color=BLACK, opacity=0.30)  # was 0.34
    vignette.set_stroke(width=0)
    vignette.move_to([0, 0, 0])

    haze = Circle(radius=max(fw, fh) * 0.62).set_z_index(0)
    haze.set_fill(color=darken_hex(base_blue, 0.22), opacity=0.04)  # was 0.03
    haze.set_stroke(width=0)
    haze.move_to(center + UP * 0.25)

    grid = VGroup().set_z_index(1)

    minor_step = 0.65
    x = fb["left"]
    while x <= fb["right"] + 1e-6:
        ln = Line([x, fb["bottom"], 0], [x, fb["top"], 0])
        ln.set_stroke(base_blue, width=1, opacity=0.020)  # was 0.016
        grid.add(ln)
        x += minor_step

    y = fb["bottom"]
    while y <= fb["top"] + 1e-6:
        ln = Line([fb["left"], y, 0], [fb["right"], y, 0])
        ln.set_stroke(base_blue, width=1, opacity=0.017)  # was 0.013
        grid.add(ln)
        y += minor_step

    major = VGroup().set_z_index(1)
    major_step = 1.30
    x = fb["left"]
    while x <= fb["right"] + 1e-6:
        ln = Line([x, fb["bottom"], 0], [x, fb["top"], 0])
        ln.set_stroke(base_blue, width=1.2, opacity=0.048)  # was 0.040
        major.add(ln)
        x += major_step

    y = fb["bottom"]
    while y <= fb["top"] + 1e-6:
        ln = Line([fb["left"], y, 0], [fb["right"], y, 0])
        ln.set_stroke(base_blue, width=1.2, opacity=0.040)  # was 0.034
        major.add(ln)
        y += major_step

    edge = VGroup(
        Rectangle(width=fw + 2, height=1.75)
        .set_fill(BLACK, 0.22)
        .set_stroke(width=0)
        .move_to([0, fb["top"] + 0.55, 0]),
        Rectangle(width=fw + 2, height=1.75)
        .set_fill(BLACK, 0.22)
        .set_stroke(width=0)
        .move_to([0, fb["bottom"] - 0.55, 0]),
        Rectangle(width=2.25, height=fh + 2)
        .set_fill(BLACK, 0.20)
        .set_stroke(width=0)
        .move_to([fb["left"] - 0.60, 0, 0]),
        Rectangle(width=2.25, height=fh + 2)
        .set_fill(BLACK, 0.20)
        .set_stroke(width=0)
        .move_to([fb["right"] + 0.60, 0, 0]),
    ).set_z_index(2)

    hud = RoundedRectangle(
        width=sf["w"] + 0.70,
        height=sf["h"] + 0.70,
        corner_radius=0.30,
    ).set_z_index(3)
    hud.set_fill(opacity=0)
    hud.set_stroke(color=base_blue, width=2.0, opacity=0.07)
    hud.move_to([sf["cx"], sf["cy"], 0])

    ticks = VGroup().set_z_index(3)
    tick_len = 0.40
    tick_w = 2.0
    tick_op = 0.14
    corners = [hud.get_corner(UL), hud.get_corner(UR), hud.get_corner(DL), hud.get_corner(DR)]
    dirs = [(RIGHT, DOWN), (LEFT, DOWN), (RIGHT, UP), (LEFT, UP)]
    for c, (dx, dy) in zip(corners, dirs):
        t1 = Line(c, c + dx * tick_len)
        t2 = Line(c, c + dy * tick_len)
        for t in (t1, t2):
            t.set_stroke(base_blue, width=tick_w, opacity=tick_op)
        ticks.add(t1, t2)

    particles = VGroup().set_z_index(2)
    rng = np.random.default_rng(7)
    for _ in range(18):
        r = float(rng.uniform(0.02, 0.05))
        p = Dot(
            point=np.array([rng.uniform(fb["left"], fb["right"]), rng.uniform(fb["bottom"], fb["top"]), 0]),
            radius=r,
            color=base_blue,
        )
        p.set_opacity(float(rng.uniform(0.05, 0.12)))
        drift = np.array([rng.uniform(-0.028, 0.028), rng.uniform(-0.018, 0.018), 0])

        def _make_updater(v):
            def _up(m, dt):
                m.shift(v * dt)
                x0, y0, _ = m.get_center()
                if x0 < fb["left"]:
                    m.move_to([fb["right"], y0, 0])
                elif x0 > fb["right"]:
                    m.move_to([fb["left"], y0, 0])
                if y0 < fb["bottom"]:
                    m.move_to([x0, fb["top"], 0])
                elif y0 > fb["top"]:
                    m.move_to([x0, fb["bottom"], 0])

            return _up

        p.add_updater(_make_updater(drift))
        particles.add(p)

    g.add(tint, plate, glow, haze, vignette, grid, major, edge, hud, ticks, particles)
    return g


def build_header(sf: Dict[str, float], title_text: str, sub_text: str) -> Tuple[Mobject, Mobject, Mobject, Mobject]:
    title = _safe_text(
        title_text,
        font=FONT_DISPLAY,
        font_size=44,
        color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"),
        weight=BOLD,
    ).set_z_index(200)
    title.move_to([sf["cx"], sf["top"] - 0.95, 0])

    underline = Line(LEFT, RIGHT).set_z_index(200)
    underline.set_stroke(
        width=4,
        color=[getattr(Theme, "NEON_PINK", "#FB7185"), getattr(Theme, "NEON_BLUE", "#2DD4FF")],
        opacity=0.90,
    )
    underline.scale_to_fit_width(min(sf["w"] * 0.72, 6.8))
    underline.next_to(title, DOWN, buff=0.18)

    sub = _safe_text(
        sub_text,
        font="Montserrat",
        font_size=18,
        color=getattr(Theme, "TEXT_SUB", "#CCCCCC"),
    ).set_z_index(200)
    sub.next_to(underline, DOWN, buff=0.18)

    t = ValueTracker(0.0)

    def dot_mob():
        u = float(t.get_value()) % 1.0
        p = underline.point_from_proportion(u)
        d = Dot(point=p, radius=0.045, color=getattr(Theme, "NEON_BLUE", "#2DD4FF"))
        d.set_z_index(205)
        d.set_opacity(0.95)
        return d

    dot = always_redraw(dot_mob)

    def _tick(_m, dt):
        t.increment_value(dt * 0.18)

    dot.add_updater(_tick)

    return title, underline, sub, dot


def build_dial(center: np.ndarray, outer_r: float) -> VGroup:
    g = VGroup().set_z_index(10)
    neon = getattr(Theme, "NEON_BLUE", "#2DD4FF")

    halo = Circle(radius=outer_r * 1.18).set_z_index(8)
    halo.set_fill(neon, 0.022)  # was 0.035
    halo.set_stroke(width=0)
    halo.move_to(center)

    backplate = Circle(radius=outer_r * 1.28).set_z_index(8)
    backplate.set_fill("#05080B", 0.24)  # was 0.22 (slightly more depth)
    backplate.set_stroke(neon, width=2, opacity=0.045)  # was 0.06
    backplate.move_to(center)

    plate = Circle(radius=outer_r * 1.06).set_z_index(9)
    plate.set_fill("#05080B", 0.26)
    plate.set_stroke(width=0)
    plate.move_to(center)

    rings = VGroup(
        Circle(radius=outer_r * 1.08),
        Circle(radius=outer_r * 1.20),
        Circle(radius=outer_r * 1.32),
    ).set_z_index(10)
    for r in rings:
        r.set_fill(opacity=0)
        r.set_stroke(color=getattr(Theme, "TEXT_SUB", "#CCCCCC"), width=2, opacity=0.075)  # was 0.10
        r.move_to(center)

    ticks = VGroup().set_z_index(11)
    tick_r = outer_r * 1.36
    for ang in np.linspace(0, TAU, 48, endpoint=False):
        p1 = center + np.array([np.cos(ang) * (tick_r - 0.10), np.sin(ang) * (tick_r - 0.10), 0])
        p2 = center + np.array([np.cos(ang) * tick_r, np.sin(ang) * tick_r, 0])
        ln = Line(p1, p2)
        ln.set_stroke(color=getattr(Theme, "TEXT_SUB", "#CCCCCC"), width=2, opacity=0.075)
        ticks.add(ln)

    glass = Circle(radius=outer_r * 1.06).set_z_index(90)
    glass.set_fill(WHITE, 0.007)  # was 0.010
    glass.set_stroke(WHITE, width=2, opacity=0.05)  # was 0.07
    glass.move_to(center)

    g.add(halo, backplate, plate, rings, ticks, glass)
    return g


# ==========================
# Slot system (fixed layout + push-out)
# ==========================
def fixed_slots(sf: Dict[str, float], center: np.ndarray, lane_top: float) -> List[np.ndarray]:
    rel = [
        (-2.60, 2.10),
        (0.00, 2.35),
        (2.60, 2.05),
        (-3.05, 1.05),
        (3.05, 1.05),
        (-3.05, -0.15),
        (3.05, -0.15),
        (-2.55, -1.40),
        (0.00, -1.85),
        (2.55, -1.40),
    ]

    out: List[np.ndarray] = []
    max_y = lane_top - 0.30
    min_y = sf["bottom"] + 0.60

    for dx, dy in rel:
        x = clamp(center[0] + dx, sf["left"] + 0.70, sf["right"] - 0.70)
        y = clamp(center[1] + dy, min_y, max_y)
        out.append(np.array([x, y, 0]))
    return out


def push_out_slots(slots: List[np.ndarray], center: np.ndarray, amount: float) -> List[np.ndarray]:
    pushed: List[np.ndarray] = []
    for p in slots:
        v = p - center
        n = float(np.linalg.norm(v))
        if n < 1e-6:
            pushed.append(p.copy())
            continue
        pushed.append(p + (v / n) * amount)
    return pushed


def assign_slots_nearest_side_biased(
    slice_points: List[np.ndarray],
    slots: List[np.ndarray],
    center: np.ndarray,
) -> List[int]:
    remaining = set(range(len(slots)))
    out = [-1] * len(slice_points)

    order = sorted(range(len(slice_points)), key=lambda i: -np.linalg.norm(slice_points[i] - center))
    for i in order:
        p = slice_points[i]
        side = -1 if p[0] < center[0] else 1

        best = None
        best_score = 1e18
        for s in remaining:
            q = slots[s]
            dist = float(np.linalg.norm(p - q))
            slot_side = -1 if q[0] < center[0] else 1
            penalty = 1.25 if slot_side != side else 0.0
            score = dist + penalty
            if score < best_score:
                best_score = score
                best = s

        if best is None:
            best = next(iter(remaining)) if remaining else 0

        out[i] = int(best)
        if best in remaining:
            remaining.remove(best)

    return out


# ==========================
# Commentary (center text, safe fit)
# ==========================
def make_commentary(center: np.ndarray, inner_r: float, label: str, name: str, pct_text: str, col: str) -> VGroup:
    g = VGroup(
        _safe_text(label, font="Consolas", font_size=14, color=getattr(Theme, "TEXT_SUB", "#CCCCCC")),
        _safe_text(name, font="Montserrat", font_size=26, color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"), weight=BOLD),
        _safe_text(pct_text, font="Montserrat", font_size=30, color=col, weight=BOLD),
        _safe_text("computing…", font="Consolas", font_size=12, color=getattr(Theme, "TEXT_SUB", "#CCCCCC")),
    ).arrange(DOWN, buff=0.06)
    g.set_z_index(210)
    g.scale_to_fit_width(inner_r * 1.62)
    g.move_to(center)
    return g


# ==========================
# Callouts (chip + elbow lines) - geo_universal style (core + glow)
# ==========================
def make_callout_chip(name: str, value: float, unit: str, rank: int, col: str, frac: float) -> VGroup:
    rank_txt = _safe_text(
        f"{rank:02d}",
        font="Consolas",
        font_size=12,
        color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"),
        weight=BOLD,
    )
    badge = Circle(radius=0.15)
    badge.set_fill("#05080B", 0.85)
    badge.set_stroke(lighten_hex(col, 0.18), 1.8, 0.95)
    rank_txt.move_to(badge)

    nm = text_ellipsize_to_width(
        str(name),
        font="Montserrat",
        font_size=13,
        max_width=2.25,
        color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"),
    )

    v_str = f"{int(round(value))}{unit}" if unit else f"{int(round(value))}"
    vv = _safe_text(v_str, font="Montserrat", font_size=13, color=lighten_hex(col, 0.08), weight=BOLD)

    row = VGroup(badge, rank_txt, nm, vv).arrange(RIGHT, buff=0.14, aligned_edge=DOWN)

    bar_w = max(1.35, float(row.width * 0.52))
    bar_h = 0.06
    bar_bg = RoundedRectangle(width=bar_w, height=bar_h, corner_radius=0.03)
    bar_bg.set_fill("#0B0F12", 0.85)
    bar_bg.set_stroke(width=0)

    bar_fill = RoundedRectangle(width=max(0.01, bar_w * clamp(frac, 0.05, 1.0)), height=bar_h, corner_radius=0.03)
    bar_fill.set_fill(lighten_hex(col, 0.05), 0.72)
    bar_fill.set_stroke(width=0)
    bar_fill.align_to(bar_bg, LEFT)

    bar = VGroup(bar_bg, bar_fill)
    content = VGroup(row, bar).arrange(DOWN, buff=0.10, aligned_edge=LEFT)

    pad_x, pad_y = 0.22, 0.16
    bg = RoundedRectangle(width=content.width + 2 * pad_x, height=content.height + 2 * pad_y, corner_radius=0.16)
    bg.set_fill("#05080B", 0.72)
    bg.set_stroke(lighten_hex(col, 0.12), 1.7, 0.92)

    glow = bg.copy()
    glow.set_fill(opacity=0)
    glow.set_stroke(col, width=11, opacity=0.10)

    content.move_to(bg.get_center())
    return VGroup(glow, bg, content).set_z_index(170)


def make_callout(center: np.ndarray, outer_r: float, slice_mid: float, pop_vec: np.ndarray, chip: VGroup, col: str) -> VGroup:
    base_edge = center + np.array([np.cos(slice_mid) * outer_r, np.sin(slice_mid) * outer_r, 0])
    p0 = base_edge + pop_vec * 0.55

    if chip.get_center()[0] >= center[0]:
        dot_pos = chip.get_left() + LEFT * 0.12
    else:
        dot_pos = chip.get_right() + RIGHT * 0.12

    dot = Dot(dot_pos, radius=0.05, color=lighten_hex(col, 0.08)).set_z_index(166)
    dot.set_opacity(0.95)

    dirx = 1 if dot_pos[0] >= center[0] else -1
    elbow_x = center[0] + dirx * (outer_r + 0.60)
    p1 = np.array([elbow_x, dot_pos[1], 0])
    p2 = dot_pos

    core1 = Line(p0, p1)
    core2 = Line(p1, p2)

    dot0 = Dot(p0, radius=0.035, color=col).set_z_index(166)

    for ln in (core1, core2):
        ln.set_fill(opacity=0)
        ln.set_z_index(165)
        ln.set_stroke(color=col, width=3.0, opacity=0.72)
        try:
            ln.set_stroke(line_cap=ROUND)
        except Exception:
            pass

    glow1 = core1.copy()
    glow2 = core2.copy()
    for gl in (glow1, glow2):
        gl.set_fill(opacity=0)
        gl.set_z_index(164)
        gl.set_stroke(color=col, width=10.0, opacity=0.12)
        try:
            gl.set_stroke(line_cap=ROUND)
        except Exception:
            pass

    return VGroup(glow1, glow2, core1, core2, dot, chip, dot0).set_z_index(165)


def _make_callout_lines_only(
    center_for_slice: np.ndarray,
    outer_r: float,
    slice_mid: float,
    pop_vec: np.ndarray,
    dot_pos: np.ndarray,
    col: str,
) -> Tuple[Line, Line, Line, Line]:
    """
    Returns: (glow1, glow2, core1, core2)
    Uses dot_pos (chip-side) + slice-side computed from center_for_slice.
    This fixes "winner callout missing" / disconnect when slice is shifted (popped).
    """
    base_edge = center_for_slice + np.array([np.cos(slice_mid) * outer_r, np.sin(slice_mid) * outer_r, 0])
    p0 = base_edge + pop_vec * 0.55

    dirx = 1 if dot_pos[0] >= center_for_slice[0] else -1
    elbow_x = center_for_slice[0] + dirx * (outer_r + 0.60)
    p1 = np.array([elbow_x, dot_pos[1], 0])
    p2 = dot_pos

    core1 = Line(p0, p1)
    core2 = Line(p1, p2)
    dot0 = Dot(p0, radius=0.035, color=col).set_z_index(166)

    for ln in (core1, core2):
        ln.set_fill(opacity=0)
        ln.set_z_index(165)
        ln.set_stroke(color=col, width=3.0, opacity=0.72)
        try:
            ln.set_stroke(line_cap=ROUND)
        except Exception:
            pass

    glow1 = core1.copy()
    glow2 = core2.copy()
    for gl in (glow1, glow2):
        gl.set_fill(opacity=0)
        gl.set_z_index(164)
        gl.set_stroke(color=col, width=10.0, opacity=0.12)
        try:
            gl.set_stroke(line_cap=ROUND)
        except Exception:
            pass

    return glow1, glow2, core1, core2, dot0


# ==========================
# Chip overlap resolver (SAFE: no .bounding_box attribute usage)
# ==========================
def resolve_chip_overlaps(
    chips: List[VGroup],
    sf: Dict[str, float],
    lane_top: float,
    max_iters: int = 28,
    pad: float = 0.06,
    extra_push: float = 0.06,
) -> None:
    if len(chips) <= 1:
        return

    min_y = sf["bottom"] + 0.20
    max_y = lane_top - 0.20

    def _chip_h(c: VGroup) -> float:
        return float(c.get_top()[1] - c.get_bottom()[1])

    def _clamp_chip(c: VGroup) -> None:
        cx, cy, _ = c.get_center()
        h = _chip_h(c)
        lo = min_y + h / 2.0
        hi = max_y - h / 2.0
        cy2 = clamp(cy, lo, hi)
        c.move_to([cx, cy2, 0])

    def _aabb(c: VGroup) -> Tuple[float, float, float, float]:
        x0 = float(c.get_left()[0]) - pad
        x1 = float(c.get_right()[0]) + pad
        y0 = float(c.get_bottom()[1]) - pad
        y1 = float(c.get_top()[1]) + pad
        return x0, x1, y0, y1

    for c in chips:
        _clamp_chip(c)

    for _ in range(max_iters):
        moved = False

        for i in range(len(chips)):
            for j in range(i + 1, len(chips)):
                a, b = chips[i], chips[j]
                ax0, ax1, ay0, ay1 = _aabb(a)
                bx0, bx1, by0, by1 = _aabb(b)

                x_overlap = min(ax1, bx1) - max(ax0, bx0)
                y_overlap = min(ay1, by1) - max(ay0, by0)

                if x_overlap > 0 and y_overlap > 0:
                    push = (y_overlap / 2.0) + extra_push
                    if a.get_center()[1] <= b.get_center()[1]:
                        a.shift(DOWN * push)
                        b.shift(UP * push)
                    else:
                        a.shift(UP * push)
                        b.shift(DOWN * push)

                    _clamp_chip(a)
                    _clamp_chip(b)
                    moved = True

        if not moved:
            break


# ==========================
# ==========================
# Data loader (current branch — job-aware; preserved verbatim)
# ==========================
SLICE_PALETTE = [
    "#00F0FF", "#FF0055", "#BD00FF", "#FFE14D",
    "#00FF66", "#FF9900", "#3388FF", "#FF6EC7",
]


def _parse_meta(path: str) -> dict:
    meta = {"TITLE": "MARKET BREAKDOWN", "SUB": "Share Distribution", "TOTAL_LABEL": "TOTAL"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("#"):
            for part in first[1:].split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    meta[k.strip().upper()] = v.strip()
    except Exception:
        pass
    return meta


def load_donut_csv(csv_path: str):
    meta = _parse_meta(csv_path)
    if not os.path.exists(csv_path):
        categories = ["Nvidia", "Microsoft", "Google", "Apple", "Others"]
        values     = [35.0, 22.0, 18.0, 15.0, 10.0]
        colors     = SLICE_PALETTE[:5]
        return meta, categories, values, colors

    df = pd.read_csv(csv_path, comment="#")
    df.columns = [c.strip().title() for c in df.columns]
    for required in ("Category", "Value"):
        if required not in df.columns:
            raise ValueError(f"donut_breakdown CSV missing column: {required}")

    df["Category"] = df["Category"].astype(str).str.strip()
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0.0)
    df = df[df["Value"] > 0].head(8).reset_index(drop=True)

    if "Color" in df.columns:
        raw_colors = df["Color"].astype(str).str.strip().tolist()
        colors = [c if c.startswith("#") else SLICE_PALETTE[i % len(SLICE_PALETTE)]
                  for i, c in enumerate(raw_colors)]
    else:
        colors = [SLICE_PALETTE[i % len(SLICE_PALETTE)] for i in range(len(df))]

    return meta, df["Category"].tolist(), df["Value"].tolist(), colors


# ==========================
# Scene (FINAL)
# ==========================
class DonutBreakdownFinal(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        add_cinematic_background(self, accent=getattr(Theme, "NEON_BLUE", "#00F0FF"))
        sf = get_safe_frame(margin=0.70)

        # Timeline Initialization (current job-aware plumbing)
        job_dir_env = os.environ.get("JOB_DIR", "")
        job_json_path = os.environ.get("JOB_JSON_PATH", "")
        job_dir = job_dir_env or (os.path.dirname(job_json_path) if job_json_path else project_root)
            
        sys_job = load_job(default={"template_id": "donut_breakdown", "timeline": {}})
        sfx = SFXEngine(self, job_dir)
        
        timeline_dict = sys_job.get("timeline", {}) if isinstance(sys_job.get("timeline", {}), dict) else {}

        # Anchor global start time before intro plays
        global_start_t0 = float(self.time)

        # Intro (LOCKED utils.py)
        if HAS_PROJECT:
            try:
                IntroManager.play_intro(
                    self,
                    brand_title="BIGDATA LEAK",
                    brand_sub="SYSTEM BREACH DETECTED",
                    feed_text="FEED_DONUT // BREAKDOWN",
                    footer_text="CONFIDENTIAL // VERIFIED",
                )
            except Exception:
                pass

        # Data — current job-aware loader (reads THIS job's CSV, not a fixed path)
        csv_path = sys_job.get("data_csv") or "data/donut_data.csv"
        if not os.path.isabs(csv_path):
            csv_path = os.path.join(job_dir, csv_path)
        meta, names, raw_vals, _csv_cols = load_donut_csv(csv_path)
        # Slice colors come from main's premium-palette resolver (matches the reference
        # video); feed neutral groups + empty CSV colors so the presets are used.
        groups = ["Default"] * len(names)
        csv_colors = ["" for _ in names]

        title_text = (meta.get("TITLE", "MARKET SHARE 2025") or "MARKET SHARE 2025").strip()
        sub_text = (meta.get("SUB", "Global smartphone shipments") or "").strip()
        unit = (meta.get("UNIT", "%") or "").strip()

        # Layout anchors
        center = np.array([0.0, -0.52, 0.0])
        outer_r = 1.92
        inner_r = 1.05

        # Background + Dial
        bg = build_background(sf, center, outer_r)
        dial = build_dial(center, outer_r)
        self.add(bg, dial)

        # Header
        title, underline, sub, underline_dot = build_header(sf, title_text, sub_text)
        lane_top = sub.get_bottom()[1] - 0.55 if sub_text else underline.get_bottom()[1] - 0.55

        # Donut base
        shadow_ring = Annulus(inner_radius=inner_r, outer_radius=outer_r).set_z_index(25)
        shadow_ring.set_fill(BLACK, 0.22).set_stroke(width=0)
        shadow_ring.move_to(center + DOWN * 0.10)

        track = Annulus(inner_radius=inner_r, outer_radius=outer_r).set_z_index(30)
        track.set_fill("#060A0D", 0.72).set_stroke("#0D141A", 3, 1.0)
        track.move_to(center)

        outer_rim = Circle(radius=outer_r).set_z_index(55).set_fill(opacity=0)
        outer_rim.set_stroke(WHITE, 3, 0.10).move_to(center)

        inner_rim = Circle(radius=inner_r).set_z_index(56).set_fill(opacity=0)
        inner_rim.set_stroke(WHITE, 2, 0.10).move_to(center)

        core = Circle(radius=inner_r * 0.96).set_z_index(80)
        core.set_fill("#05080B", 0.90).set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), 2, 0.18)
        core.move_to(center)

        self.add(shadow_ring, track, outer_rim, inner_rim, core)

        # Commentary (boot)
        commentary = make_commentary(center, inner_r, "SCAN", "MARKET", "…", getattr(Theme, "NEON_BLUE", "#2DD4FF"))
        self.add(commentary)

        # Segment plumbing — current audio-sync logic: derive slice_* from audio.order
        # so the ghost-padding loop below covers EVERY audio slot (not a hardcoded range).
        n = len(names)
        slice_segs = [f"slice_{i + 1}" for i in range(n)]
        _audio_cfg = sys_job.get("audio") if isinstance(sys_job, dict) else {}
        _audio_order = _audio_cfg.get("order", []) if isinstance(_audio_cfg, dict) else []
        _all_slice_segs = [s for s in _audio_order if isinstance(s, str) and s.startswith("slice_")]
        if not _all_slice_segs:
            _all_slice_segs = slice_segs  # fallback: audio.order absent → no ghost padding

        defaults = {"hook": 2.5, "setup": 2.0, "winner": 3.0, "outro": 1.5}
        for seg in _all_slice_segs:
            defaults[seg] = 2.2
        
        TL = Timeline.from_dict(timeline_dict, defaults=defaults)
        
        # Audio starts for hook
        hook_t0 = global_start_t0

        # Edge case: no geo_data
        if not names or not raw_vals:
            t_h = TL.seg_total("hook", 2.0)
            self.play(Write(title), run_time=clamp(t_h * 0.45, 0.25, 0.70), rate_func=rf.ease_out_cubic)
            self.play(Create(underline), run_time=clamp(t_h * 0.30, 0.15, 0.40), rate_func=rf.ease_out_cubic)
            self.add(underline_dot)
            if sub_text:
                self.play(FadeIn(sub, shift=UP * 0.06), run_time=clamp(t_h * 0.25, 0.10, 0.35), rate_func=rf.ease_out_cubic)
            
            TL.consume("hook", float(self.time) - hook_t0)
            hold_breathing(self, TL.remaining("hook"), focus=title)
            return

        # Percent + ranks
        pct_vals = normalize_to_pct(raw_vals)
        total = float(np.sum(pct_vals)) if pct_vals else 100.0
        total = max(1e-9, total)

        vmax = float(np.max(raw_vals)) if raw_vals else 1.0
        vmax = max(1e-9, vmax)

        idx_desc = sorted(range(len(raw_vals)), key=lambda i: float(raw_vals[i]), reverse=True)
        winner_idx = idx_desc[0] if idx_desc else 0
        rank_map = {i: r + 1 for r, i in enumerate(idx_desc)}

        idx_asc = sorted(range(len(raw_vals)), key=lambda i: float(raw_vals[i]))
        if winner_idx in idx_asc:
            idx_asc.remove(winner_idx)
            idx_asc.append(winner_idx)

        # Color resolution (premium + theme-tint). CSV only if meta USE_CSV_COLORS=1.
        base_blue = getattr(Theme, "NEON_BLUE", "#2DD4FF")
        use_csv = False
        try:
            use_csv = bool(int(str(meta.get("USE_CSV_COLORS", "0")).strip() or "0"))
        except Exception:
            use_csv = False

        used_by_group: Dict[str, int] = {}
        colors: List[str] = []
        for i, nm in enumerate(names):
            grp = groups[i] if i < len(groups) else "Default"
            csv_c = csv_colors[i] if i < len(csv_colors) else ""
            col, src = pick_premium_color(
                nm,
                grp,
                csv_c,
                i,
                used_by_group,
                allow_csv=use_csv,
                theme_blue=base_blue,
            )
            colors.append(col)
            print(f"[DonutBreakdownFinal] COLOR_SOURCE={src} | name={nm} | group={grp} | color={col}")

        # Donut build (sweep + reveal slices)
        t_setup = TL.seg_total("setup", 2.6)
        setup_action = clamp(t_setup * 0.85, 1.8, 3.5)
        scale_setup = setup_action / 2.6
        
        # ✅ FIX 1.1: Anchor for delta time
        setup_t0 = float(self.time)
        
        # Audio starts for setup
        sfx.mark("ui_in", meta={"at": "setup_start"})
        
        master_ring = Annulus(inner_radius=inner_r, outer_radius=outer_r).set_z_index(70)
        master_ring.set_fill("#0A1118", 0.62)
        master_ring.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), 2.0, 0.16)
        master_ring.move_to(center)
        master_ring.set_opacity(0.0)
        
        inner_glow = Circle(radius=inner_r).set_z_index(72)
        inner_glow.set_stroke(color=getattr(Theme, "NEON_BLUE", "#2DD4FF"), width=6.0, opacity=0.3)
        inner_glow.move_to(center)
        inner_glow.set_opacity(0.0)

        inner_core = Circle(radius=inner_r).set_z_index(73)
        inner_core.set_stroke(color=WHITE, width=1.5, opacity=0.8)
        inner_core.move_to(center)
        inner_core.set_opacity(0.0)

        self.add(master_ring, inner_glow, inner_core)
        
        # NOTE: the hook budget is consumed AFTER the title/donut reveal (below), so the
        # buildup starts right after the intro instead of holding on a blank boot screen.
        
        setup_t0 = float(self.time)

        sweep_t = ValueTracker(0.0)
        sweep_span = TAU * 0.18

        def sweep_band():
            a0 = float(sweep_t.get_value())
            return AnnularSector(
                inner_radius=inner_r - 0.02,
                outer_radius=outer_r + 0.06,
                arc_center=center,
                start_angle=a0,
                angle=sweep_span,
                fill_color=getattr(Theme, "NEON_BLUE", "#2DD4FF"),
                fill_opacity=0.10,
                stroke_width=0,
            ).set_z_index(75)

        def sweep_arc():
            a0 = float(sweep_t.get_value()) + sweep_span * 0.65
            arc = Arc(radius=outer_r + 0.02, start_angle=a0, angle=TAU * 0.10, arc_center=center)
            arc.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), width=4, opacity=0.35)
            arc.set_z_index(76)
            return arc

        sweep_band_m = always_redraw(sweep_band)
        sweep_arc_m = always_redraw(sweep_arc)
        self.add(sweep_band_m, sweep_arc_m)

        # Build slices (hidden -> reveal)
        start_angle = 90 * DEGREES
        slice_groups: List[VGroup] = []
        slice_mids: List[float] = []
        slice_edge_points: List[np.ndarray] = []

        for i, pct in enumerate(pct_vals):
            ang = (float(pct) / total) * TAU
            col = colors[i] if is_hex(colors[i]) else FALLBACK_COLORS[i % len(FALLBACK_COLORS)]

            sh = AnnularSector(
                inner_radius=inner_r,
                outer_radius=outer_r,
                arc_center=center + DOWN * 0.10,
                start_angle=start_angle,
                angle=ang,
                fill_color=BLACK,
                fill_opacity=0.18,
                stroke_width=0,
            ).set_z_index(60)

            sec = AnnularSector(
                inner_radius=inner_r,
                outer_radius=outer_r,
                arc_center=center,
                start_angle=start_angle,
                angle=ang,
                fill_color=col,
                fill_opacity=0.90,
                stroke_color="#050505",
                stroke_width=4.0,
            ).set_z_index(70)

            hi = AnnularSector(
                inner_radius=inner_r + 0.06,
                outer_radius=outer_r - 0.10,
                arc_center=center,
                start_angle=start_angle,
                angle=ang,
                fill_color=WHITE,
                fill_opacity=0.06,
                stroke_color="#050505",
                stroke_width=4.0,
            ).set_z_index(71)

            rim = AnnularSector(
                inner_radius=outer_r - 0.12,
                outer_radius=outer_r,
                arc_center=center,
                start_angle=start_angle,
                angle=ang,
                fill_opacity=0.0,
                stroke_color=WHITE,
                stroke_width=2.0,
            ).set_z_index(72)
            rim.set_stroke(opacity=0.10)
            
            grp = VGroup(sh, sec, hi, rim).set_z_index(70)
            grp.save_state()
            grp.set_opacity(0.0)

            self.add(grp)
            slice_groups.append(grp)

            mid = float(start_angle + ang / 2.0)
            slice_mids.append(mid)
            slice_edge_points.append(center + np.array([np.cos(mid) * outer_r, np.sin(mid) * outer_r, 0]))
            start_angle += ang

        # Slots + push-out
        slots = fixed_slots(sf, center, lane_top)
        slots = push_out_slots(slots, center, amount=0.55)
        slot_ids = assign_slots_nearest_side_biased(slice_edge_points, slots, center)

        # Build chips FIRST, resolve overlaps, THEN build callouts
        chips: List[VGroup] = []
        for i in range(len(names)):
            col = colors[i] if is_hex(colors[i]) else FALLBACK_COLORS[i % len(FALLBACK_COLORS)]
            frac = float(raw_vals[i] / vmax) if vmax > 0 else 0.1

            chip = make_callout_chip(
                name=names[i],
                value=float(raw_vals[i]),
                unit=unit,
                rank=int(rank_map.get(i, i + 1)),
                col=col,
                frac=frac,
            )

            slot_pos = slots[slot_ids[i]] if 0 <= slot_ids[i] < len(slots) else slots[0]
            chip.move_to(slot_pos)

            # Final clamp
            cx = clamp(
                chip.get_center()[0],
                sf["left"] + chip.width / 2 + 0.05,
                sf["right"] - chip.width / 2 - 0.05,
            )
            cy = clamp(
                chip.get_center()[1],
                sf["bottom"] + chip.height / 2 + 0.05,
                lane_top - chip.height / 2 - 0.10,
            )
            chip.move_to([cx, cy, 0])
            chips.append(chip)

        resolve_chip_overlaps(chips, sf, lane_top)

        callouts = VGroup().set_z_index(165)
        self.add(callouts)
        callout_by_idx: Dict[int, VGroup] = {}

        for i in range(len(names)):
            col = colors[i] if is_hex(colors[i]) else FALLBACK_COLORS[i % len(FALLBACK_COLORS)]
            chip = chips[i]
            pop_vec = np.array([np.cos(slice_mids[i]), np.sin(slice_mids[i]), 0]) * 0.22
            callout = make_callout(
                center=center,
                outer_r=outer_r,
                slice_mid=slice_mids[i],
                pop_vec=pop_vec,
                chip=chip,
                col=col,
            )
            callout.set_opacity(0.0)
            callouts.add(callout)
            callout_by_idx[i] = callout

        # Header + Donut creation (parallel feel)
        self.play(Write(title), run_time=0.45, rate_func=rf.ease_out_cubic)
        self.play(
            AnimationGroup(
                Create(underline, rate_func=rf.ease_out_cubic),
                FadeIn(shadow_ring, shift=DOWN * 0.03, rate_func=rf.ease_out_cubic),
                lag_ratio=0.0,
            ),
            run_time=0.30,
        )
        self.add(underline_dot)
        if sub_text:
            self.play(FadeIn(sub, shift=UP * 0.06), run_time=0.25, rate_func=rf.ease_out_cubic)

        master_ring.set_opacity(1.0)
        inner_glow.set_opacity(1.0)
        inner_core.set_opacity(1.0)
        self.play(
            DrawBorderThenFill(master_ring),
            DrawBorderThenFill(inner_glow),
            DrawBorderThenFill(inner_core),
            run_time=0.40,
            rate_func=rf.ease_out_cubic
        )
        self.play(sweep_t.animate.set_value(TAU), run_time=0.55, rate_func=rf.linear)
        self.play(
            LaggedStart(*[Restore(g) for g in slice_groups], lag_ratio=0.08),
            run_time=1.05,
            rate_func=rf.linear,
        )
        self.play(
            master_ring.animate.set_opacity(0.16),
            inner_glow.animate.set_stroke(opacity=0.10),
            inner_core.animate.set_stroke(opacity=0.30),
            run_time=0.18,
            rate_func=rf.ease_out_cubic
        )
        self.play(FadeOut(sweep_band_m), FadeOut(sweep_arc_m), run_time=0.18, rate_func=rf.ease_out_cubic)

        # ── HOOK budget: the intro + the title/donut reveal above just played. Consume
        # the elapsed hook time and hold the REMAINING hook on the FULL donut (no more
        # ~8s blank boot screen). Per-segment durations are unchanged → sync stays exact.
        TL.consume("hook", float(self.time) - hook_t0)
        hold_breathing(self, TL.remaining("hook"), focus=master_ring, text="ANALYZING BREAKDOWN")

        # ── SETUP budget: hold on the fully-revealed donut before the slice story begins.
        setup_anchor = float(self.time)
        TL.consume("setup", float(self.time) - setup_anchor)
        hold_breathing(self, TL.remaining("setup"), focus=master_ring, text="CALIBRATING SLICES")

        # Story loop
        scan_t = ValueTracker(0.0)

        def scan_arc():
            a = float(scan_t.get_value())
            arc = Arc(
                radius=outer_r + 0.03,
                start_angle=a,
                angle=TAU * 0.10,
                arc_center=center,
            )
            arc.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), width=3, opacity=0.12)
            arc.set_z_index(77)
            return arc

        scan_arc_m = always_redraw(scan_arc)
        self.add(scan_arc_m)

        for i_idx, idx in enumerate(idx_asc):
            # ✅ FIX: Anchor time for this specific slice
            slice_t0 = float(self.time)
            
            grp = slice_groups[idx]
            sec = grp[1]

            col = colors[idx] if is_hex(colors[idx]) else FALLBACK_COLORS[idx % len(FALLBACK_COLORS)]
            pct_int = int(round(float(pct_vals[idx])))
            is_winner = (idx == winner_idx)

            pop = np.array([np.cos(slice_mids[idx]), np.sin(slice_mids[idx]), 0]) * 0.24
            pop_vec = np.array([np.cos(slice_mids[idx]), np.sin(slice_mids[idx]), 0]) * 0.22  # must match callout math

            seg_key = f"slice_{i_idx + 1}"
            t_item = TL.seg_total(seg_key, 2.0)
            
            # Action pacing rules
            act_in = clamp(t_item * 0.35, 0.40, 1.25)
            act_pop = clamp(t_item * 0.15, 0.15, 0.45)
            act_out = clamp(t_item * 0.25, 0.30, 0.85)
            
            # ✅ FIX: Scope leak resolved (idx+1 instead of undefined i+1)
            sfx.mark("whoosh_short", offset=0.0, meta={"at": "slice_reveal", "i": int(idx + 1)})

            new_comm = make_commentary(center, inner_r, "SEGMENT", str(names[idx]).upper(), f"{pct_int}%", col)
            self.play(
                Transform(commentary, new_comm),
                grp.animate.shift(pop).scale(1.03),
                scan_t.animate.increment_value(TAU * 0.35),
                run_time=act_in,
                rate_func=rf.ease_out_cubic,
            )

            c = callout_by_idx[idx]
            glow1, glow2, core1, core2, dot, chip, dot0 = c  # stable order

            # --- RETARGET lines to current slice position ---
            dot_pos = dot.get_center()
            center_for_slice = center + pop  # slice is currently shifted by pop
            new_glow1, new_glow2, new_core1, new_core2, new_dot0 = _make_callout_lines_only(
                center_for_slice=center_for_slice,
                outer_r=outer_r,
                slice_mid=slice_mids[idx],
                pop_vec=pop_vec,
                dot_pos=dot_pos,
                col=col,
            )
            glow1.become(new_glow1)
            glow2.become(new_glow2)
            core1.become(new_core1)
            core2.become(new_core2)
            dot0.become(new_dot0)

            c.set_opacity(1.0)
            self.play(
                AnimationGroup(
                    FadeIn(glow1, rate_func=rf.ease_out_cubic),
                    FadeIn(glow2, rate_func=rf.ease_out_cubic),
                    GrowFromPoint(core1, core1.get_start(), rate_func=rf.ease_out_cubic),
                    GrowFromPoint(core2, core2.get_start(), rate_func=rf.ease_out_cubic),
                    FadeIn(dot, shift=0.04 * UP, rate_func=rf.ease_out_cubic),
                    FadeIn(dot0, shift=0.04 * DOWN, rate_func=rf.ease_out_cubic),
                    FadeIn(chip, shift=0.06 * UP, rate_func=rf.ease_out_cubic),
                    lag_ratio=0.06,
                ),
                run_time=act_in,
                rate_func=rf.linear,
            )
            
            # ✅ FIX: Scope leak resolved
            sfx.mark("ui_pop", offset=0.0, meta={"at": "chip_pop", "i": int(idx + 1)})

            self.play(
                Indicate(dot, scale_factor=1.18, color=lighten_hex(col, 0.15)),
                run_time=act_pop,
                rate_func=rf.ease_out_cubic,
            )

            # ✅ FIX: Delta time implementation replaces additive math
            TL.consume(seg_key, float(self.time) - slice_t0)
            hold_breathing(self, TL.remaining(seg_key), focus=chip)

            # Anchor for exit animations
            exit_t0 = float(self.time)

            if not is_winner:
                # ✅ FIX: Scope leak resolved
                sfx.mark("whoosh_soft", offset=0.0, meta={"at": "winner_pop", "i": int(idx + 1)})
                self.play(
                    grp.animate.shift(-pop).scale(1 / 1.03),
                    scan_t.animate.increment_value(TAU * 0.20),
                    run_time=act_out,
                    rate_func=rf.ease_in_out_sine,
                )
                
                # ✅ FIX: Delta time
                TL.consume(seg_key, float(self.time) - exit_t0)

                # retarget lines back to base center after slice returns
                dot_pos = dot.get_center()
                back_glow1, back_glow2, back_core1, back_core2, back_dot0 = _make_callout_lines_only(
                    center_for_slice=center,
                    outer_r=outer_r,
                    slice_mid=slice_mids[idx],
                    pop_vec=pop_vec,
                    dot_pos=dot_pos,
                    col=col,
                )
                glow1.become(back_glow1)
                glow2.become(back_glow2)
                core1.become(back_core1)
                core2.become(back_core2)
                dot0.become(back_dot0)

            else:
                glow = sec.copy()
                glow.set_fill(opacity=0)
                glow.set_stroke(color=lighten_hex(col, 0.10), width=18, opacity=0.10)
                glow.set_z_index(73)
                self.add(glow)
                
                # ✅ FIX: Scope leak resolved
                sfx.mark("success", offset=0.0, meta={"at": "winner_glow", "i": int(idx + 1)})
                self.play(
                    Indicate(sec, color=lighten_hex(col, 0.05), scale_factor=1.02),
                    FadeIn(glow),
                    run_time=act_out,
                    rate_func=rf.ease_out_cubic,
                )
                # ✅ FIX: Delta time
                TL.consume(seg_key, float(self.time) - exit_t0)

        # Ghost Padding Loop — current audio-sync logic: absorb EVERY audio.order
        # slice_* segment beyond the actual data count (not a hardcoded range(.., 16)).
        for ghost_i in range(n, len(_all_slice_segs)):
            g_t0 = float(self.time)
            TL.consume(_all_slice_segs[ghost_i], float(self.time) - g_t0)
            hold_breathing(self, TL.remaining(_all_slice_segs[ghost_i]))

        # Final leader
        win_t0 = float(self.time)
        t_win = TL.seg_total("winner", 3.0)
        winner_col = colors[winner_idx] if colors else getattr(Theme, "NEON_BLUE", "#2DD4FF")
        leader = make_commentary(
            center,
            inner_r,
            "LEADER",
            str(names[winner_idx]).upper(),
            f"{int(round(float(pct_vals[winner_idx])))}%",
            winner_col,
        )
        sfx.mark("winner_sting", offset=0.0, meta={"at": "winner_announce"})
        self.play(Transform(commentary, leader), run_time=clamp(t_win * 0.25, 0.40, 0.90), rate_func=rf.ease_out_cubic)

        TL.consume("winner", float(self.time) - win_t0)
        hold_breathing(self, TL.remaining("winner"), focus=commentary)
        
        # Outro padding
        outro_t0 = float(self.time)
        TL.consume("outro", float(self.time) - outro_t0)
        hold_breathing(self, TL.remaining("outro"))
        
        # Write marks to disk
        sfx.flush()
