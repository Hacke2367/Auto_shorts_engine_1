# # src/templates/donut_breakdown.py
# # FINAL GOD-TIER Donut Breakdown Template (Intro + Build + Story Loop)
# # Manim Community v0.19.2 compatible
# #
# # Run:
# #   manim -pqh donut_breakdown.py DonutBreakdownFinal
#
# import os
# import sys
# import re
# import colorsys
# from typing import Dict, List, Optional, Tuple
#
# import numpy as np
# import pandas as pd
# from manim import *
# from manim import rate_functions as rf
#
# # ==========================
# # Optional project imports
# # ==========================
# HAS_PROJECT = True
# try:
#     current_dir = os.path.dirname(os.path.abspath(__file__))
#     project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
#     sys.path.append(project_root)
#
#     from src.config import DATA_DIR, BACKGROUND_COLOR, Theme  # type: ignore
#     from src.utils import IntroManager, get_safe_frame  # type: ignore
# except Exception:
#     HAS_PROJECT = False
#     DATA_DIR = "."
#     BACKGROUND_COLOR = "#0A0A0A"
#
#     class Theme:
#         TEXT_MAIN = "#FFFFFF"
#         TEXT_SUB = "#CCCCCC"
#         TEXT_DIM = "#9AA3AD"
#         NEON_BLUE = "#00F0FF"
#         NEON_PINK = "#FF0055"
#         NEON_PURPLE = "#BD00FF"
#         NEON_ORANGE = "#FF9900"
#         NEON_GREEN = "#00FF66"
#         NEON_YELLOW = "#FFE14D"
#
#     def get_safe_frame(margin: float = 0.70) -> Dict[str, float]:
#         half_w = config.frame_width / 2
#         half_h = config.frame_height / 2
#         return {
#             "left": -half_w + margin,
#             "right": half_w - margin,
#             "top": half_h - margin,
#             "bottom": -half_h + margin,
#             "w": config.frame_width - (2 * margin),
#             "h": config.frame_height - (2 * margin),
#             "cx": 0.0,
#             "cy": 0.0,
#         }
#
#
# # ==========================
# # Helpers / constants
# # ==========================
# _HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
#
# # Last-resort fallback (kept, but we try not to use it)
# FALLBACK_COLORS = [
#     "#2DD4FF",
#     "#A78BFA",
#     "#FB7185",
#     "#FBBF24",
#     "#34D399",
#     "#FDE047",
#     "#60A5FA",
#     "#F472B6",
#     "#4ADE80",
#     "#FDBA74",
# ]
#
#
# def is_hex(s: Optional[str]) -> bool:
#     return isinstance(s, str) and bool(_HEX_RE.match(s.strip()))
#
#
# def clamp(v: float, lo: float, hi: float) -> float:
#     return float(max(lo, min(hi, v)))
#
#
# def _hex_to_rgb01(h: str) -> Optional[np.ndarray]:
#     try:
#         s = h.strip()
#         if not is_hex(s):
#             return None
#         if len(s) == 4:  # #RGB
#             r = int(s[1] * 2, 16)
#             g = int(s[2] * 2, 16)
#             b = int(s[3] * 2, 16)
#         else:
#             r = int(s[1:3], 16)
#             g = int(s[3:5], 16)
#             b = int(s[5:7], 16)
#         return np.array([r, g, b], dtype=float) / 255.0
#     except Exception:
#         return None
#
#
# def _rgb01_to_hex(rgb: np.ndarray) -> str:
#     rgb = np.clip(rgb, 0.0, 1.0)
#     r, g, b = (rgb * 255.0 + 0.5).astype(int)
#     return f"#{r:02X}{g:02X}{b:02X}"
#
#
# def mix_hex(a: str, b: str, t: float) -> str:
#     """
#     t: 0..1  (0 = a, 1 = b)
#     """
#     ra = _hex_to_rgb01(a)
#     rb = _hex_to_rgb01(b)
#     if ra is None or rb is None:
#         return a
#     t = clamp(t, 0.0, 1.0)
#     out = ra * (1.0 - t) + rb * t
#     return _rgb01_to_hex(out)
#
#
# def lighten_hex(hex_color: str, amount: float = 0.35) -> str:
#     """
#     amount: 0..1 (0 = no change, 1 = white)
#     """
#     rgb = _hex_to_rgb01(hex_color)
#     if rgb is None:
#         return hex_color
#     w = np.array([1.0, 1.0, 1.0], dtype=float)
#     out = rgb * (1.0 - amount) + w * amount
#     return _rgb01_to_hex(out)
#
#
# def darken_hex(hex_color: str, amount: float = 0.20) -> str:
#     """
#     amount: 0..1 (0 = no change, 1 = black)
#     """
#     rgb = _hex_to_rgb01(hex_color)
#     if rgb is None:
#         return hex_color
#     k = np.array([0.0, 0.0, 0.0], dtype=float)
#     out = rgb * (1.0 - amount) + k * amount
#     return _rgb01_to_hex(out)
#
#
# # ==========================
# # PREMIUM PALETTE (theme-based, soothing)
# # ==========================
# def _hsv_to_hex(h: float, s: float, v: float) -> str:
#     r, g, b = colorsys.hsv_to_rgb(h % 1.0, clamp(s, 0, 1), clamp(v, 0, 1))
#     return _rgb01_to_hex(np.array([r, g, b], dtype=float))
#
#
# def build_theme_palette(base_hex: str, n: int) -> List[str]:
#     """
#     Goal: premium + soothing on dark background, consistent with Theme.NEON_BLUE.
#     - We keep saturation moderate and value high (but not neon).
#     - A small warm accent is allowed (still softened) so the chart doesn't feel "all same".
#     """
#     base_rgb = _hex_to_rgb01(base_hex)
#     if base_rgb is None:
#         base_rgb = np.array([0.18, 0.82, 1.0], dtype=float)
#
#     h0, s0, v0 = colorsys.rgb_to_hsv(float(base_rgb[0]), float(base_rgb[1]), float(base_rgb[2]))
#
#     # Controlled hue offsets (mostly cool + one warm accent)
#     offsets = [0, -0.06, +0.06, -0.12, +0.12, +0.30, +0.18, -0.18, +0.42, -0.30]
#
#     # Softening target (reduces harshness without killing contrast)
#     SOFT_TARGET = "#CFE8F4"  # cool off-white
#     OUT: List[str] = []
#     for i in range(max(1, n)):
#         off = offsets[i % len(offsets)]
#         # moderate saturation & value; adapt slightly from base
#         s = clamp(0.52 + (s0 - 0.52) * 0.35, 0.42, 0.62)
#         v = clamp(0.92 + (v0 - 0.92) * 0.25, 0.86, 0.95)
#         col = _hsv_to_hex(h0 + off, s, v)
#
#         # soften a bit to avoid "direct neon"
#         col = mix_hex(col, SOFT_TARGET, 0.18)
#
#         # ensure not too bright (avoid looking like pure highlight)
#         col = mix_hex(col, "#0A1118", 0.06)
#
#         OUT.append(col)
#
#     # Make sure colors are valid hex and stable
#     OUT = [c if is_hex(c) else FALLBACK_COLORS[i % len(FALLBACK_COLORS)] for i, c in enumerate(OUT)]
#     return OUT
#
#
# # ==========================
# # CSV meta + reading
# # ==========================
# def parse_meta_first_line(path: str) -> Dict[str, str]:
#     meta = {
#         "TITLE": "MARKET SHARE 2025",
#         "SUB": "Global smartphone shipments",
#         "UNIT": "%",
#         "TOP": "10",
#         "MODE": "DONUT",
#         "OTHERS_MIN_PCT": "0",
#         # Optional knobs (safe defaults)
#         "USE_CSV_COLORS": "0",  # 1 => respect CSV hex colors
#     }
#     try:
#         with open(path, "r", encoding="utf-8") as f:
#             first = f.readline().strip()
#         if first.startswith("#"):
#             first = first[1:]
#             parts = [p.strip() for p in first.split(",") if p.strip()]
#             for p in parts:
#                 if "=" in p:
#                     k, v = p.split("=", 1)
#                     meta[k.strip().upper()] = v.strip()
#     except Exception:
#         pass
#     return meta
#
#
# def normalize_to_pct(values: List[float]) -> List[float]:
#     vals = [float(v) if np.isfinite(v) else 0.0 for v in values]
#     s = float(np.sum(vals)) if vals else 0.0
#     if s <= 0:
#         return [0.0 for _ in vals]
#     if 90.0 <= s <= 110.0:
#         return [float(v) for v in vals]
#     return [float(v) / s * 100.0 for v in vals]
#
#
# def _safe_float(x) -> Optional[float]:
#     try:
#         if x is None:
#             return None
#         if isinstance(x, str) and x.strip() == "":
#             return None
#         if pd.isna(x):
#             return None
#         v = float(str(x).replace("%", "").replace(",", "").strip())
#         if not np.isfinite(v):
#             return None
#         return v
#     except Exception:
#         return None
#
#
# def read_market_csv(
#     csv_path: str,
# ) -> Tuple[Dict[str, str], List[str], List[float], List[str], List[str]]:
#     """
#     Returns: meta, names, values, colors, groups
#     """
#     meta = parse_meta_first_line(csv_path)
#
#     if not os.path.exists(csv_path):
#         names = ["Apple", "Samsung", "Xiaomi", "Oppo", "Vivo", "Others"]
#         vals = [35, 25, 15, 10, 8, 7]
#         groups = ["Premium", "Premium", "Value", "Value", "Value", "Other"]
#         cols = ["" for _ in names]
#         return meta, names, vals, cols, groups
#
#     df = pd.read_csv(csv_path, comment="#")
#     df.columns = [str(c).strip() for c in df.columns]
#     cols_map = {c.lower().strip(): c for c in df.columns}
#
#     cat_col = cols_map.get("category") or cols_map.get("name") or cols_map.get("label") or df.columns[0]
#     val_col = cols_map.get("value") or cols_map.get("val") or cols_map.get("percent") or cols_map.get("pct") or (
#         df.columns[1] if len(df.columns) > 1 else df.columns[0]
#     )
#     col_col = cols_map.get("color") or cols_map.get("hex") or cols_map.get("colour")
#     grp_col = cols_map.get("group")
#     ord_col = cols_map.get("order")
#
#     d = df.copy()
#     d[cat_col] = d[cat_col].astype(str).str.strip()
#
#     d[val_col] = d[val_col].apply(_safe_float)
#     d = d.dropna(subset=[val_col]).copy()
#     d[val_col] = d[val_col].astype(float)
#     d = d[d[val_col] > 0].copy()
#
#     if grp_col is None:
#         d["_Group"] = "Default"
#         grp_col = "_Group"
#     else:
#         d[grp_col] = d[grp_col].where(~pd.isna(d[grp_col]), "Default")
#         d[grp_col] = d[grp_col].astype(str).str.strip()
#         d[grp_col] = d[grp_col].replace({"": "Default", "nan": "Default", "NaN": "Default", "None": "Default"})
#         d[grp_col] = d[grp_col].fillna("Default")
#
#     if ord_col is not None:
#         d[ord_col] = pd.to_numeric(d[ord_col], errors="coerce").fillna(10_000)
#         d = d.sort_values(by=[ord_col, val_col], ascending=[True, False], kind="mergesort")
#     else:
#         d = d.sort_values(by=[val_col], ascending=False, kind="mergesort")
#
#     try:
#         top = int(float(meta.get("TOP", "10")))
#     except Exception:
#         top = 10
#     top = int(np.clip(top, 2, 10))
#
#     names = d[cat_col].astype(str).tolist()
#     vals = d[val_col].astype(float).tolist()
#     groups = d[grp_col].astype(str).tolist()
#
#     if col_col is not None and col_col in d.columns:
#         rawc = d[col_col].astype(str).tolist()
#         colors = [(s.strip() if is_hex(s.strip()) else "") for s in rawc]
#     else:
#         colors = ["" for _ in names]
#
#     if len(names) > top:
#         keep_n = names[: top - 1]
#         keep_v = vals[: top - 1]
#         keep_c = colors[: top - 1]
#         keep_g = groups[: top - 1]
#
#         rest_sum = float(np.sum(vals[top - 1 :]))
#         keep_n.append("Others")
#         keep_v.append(rest_sum)
#         keep_c.append("")
#         keep_g.append("Other")
#
#         names, vals, colors, groups = keep_n, keep_v, keep_c, keep_g
#
#     return meta, names, vals, colors, groups
#
#
# def _merge_tiny_into_others(
#     names: List[str],
#     vals: List[float],
#     colors: List[str],
#     groups: List[str],
#     min_pct: float,
# ) -> Tuple[List[str], List[float], List[str], List[str]]:
#     if min_pct <= 0 or not names or not vals:
#         return names, vals, colors, groups
#
#     total = float(np.sum(vals)) if vals else 0.0
#     if total <= 0:
#         return names, vals, colors, groups
#
#     keep_n, keep_v, keep_c, keep_g = [], [], [], []
#     other_sum = 0.0
#     for n, v, c, g in zip(names, vals, colors, groups):
#         pct = (float(v) / total) * 100.0
#         if pct < min_pct and str(n).strip().lower() != "others":
#             other_sum += float(v)
#         else:
#             keep_n.append(n)
#             keep_v.append(float(v))
#             keep_c.append(c)
#             keep_g.append(g)
#
#     if other_sum > 0:
#         keep_n.append("Others")
#         keep_v.append(other_sum)
#         keep_c.append("")
#         keep_g.append("Other")
#
#     return keep_n, keep_v, keep_c, keep_g
#
#
# def pick_premium_color(
#     name: str,
#     group: str,
#     csv_color: str,
#     i: int,
#     theme_palette: List[str],
#     use_csv_colors: bool,
# ) -> Tuple[str, str]:
#     """
#     Priority:
#       1) Theme palette (premium, soothing)
#       2) CSV color (ONLY if meta USE_CSV_COLORS=1)
#       3) fallback
#     """
#     # Theme palette first (always stable)
#     if theme_palette and i < len(theme_palette) and is_hex(theme_palette[i]):
#         return theme_palette[i], "THEME"
#
#     if use_csv_colors and is_hex(csv_color):
#         return csv_color.strip(), "CSV"
#
#     return FALLBACK_COLORS[i % len(FALLBACK_COLORS)], "FALLBACK"
#
#
# # ==========================
# # Text-fit helpers (safe)
# # ==========================
# def _safe_text(txt: str, font: str, font_size: int, color: str, weight=None) -> Text:
#     if weight is None:
#         return Text(txt, font=font, font_size=font_size, color=color)
#     return Text(txt, font=font, font_size=font_size, color=color, weight=weight)
#
#
# def text_ellipsize_to_width(
#     s: str,
#     font: str,
#     font_size: int,
#     max_width: float,
#     color: str,
#     weight=None,
#     min_keep: int = 4,
# ) -> Text:
#     base = str(s) if s is not None else ""
#     t = _safe_text(base, font=font, font_size=font_size, color=color, weight=weight)
#     if t.width <= max_width:
#         return t
#
#     raw = base
#     for _ in range(60):
#         if len(raw) <= min_keep:
#             break
#         raw = raw[:-1].rstrip()
#         cand = raw + "…"
#         t2 = _safe_text(cand, font=font, font_size=font_size, color=color, weight=weight)
#         if t2.width <= max_width:
#             return t2
#
#     if t.width > max_width and t.width > 1e-6:
#         t.scale_to_fit_width(max_width)
#     return t
#
#
# # ==========================
# # Visual builders
# # ==========================
# def build_background(sf: Dict[str, float], center: np.ndarray, outer_r: float) -> VGroup:
#     """
#     Premium HUD background (FULL-SCREEN grid, actually visible)
#     """
#     g = VGroup().set_z_index(1)
#
#     fw = float(config.frame_width)
#     fh = float(config.frame_height)
#     fb = {
#         "left": -fw / 2,
#         "right": fw / 2,
#         "bottom": -fh / 2,
#         "top": fh / 2,
#         "cx": 0.0,
#         "cy": 0.0,
#         "w": fw,
#         "h": fh,
#     }
#
#     base_blue = getattr(Theme, "NEON_BLUE", "#2DD4FF")
#     # Tint layer (makes grid readable without increasing opacity too much)
#     tint = Rectangle(width=fw + 0.1, height=fh + 0.1).set_z_index(0)
#     tint.set_fill(color=darken_hex(base_blue, 0.60), opacity=0.06)
#     tint.set_stroke(width=0)
#     tint.move_to([0, 0, 0])
#
#     plate = Circle(radius=outer_r * 2.15).set_z_index(0)
#     plate.set_fill(color=darken_hex(base_blue, 0.58), opacity=0.14)
#     plate.set_stroke(width=0)
#     plate.move_to(center)
#
#     glow = Circle(radius=outer_r * 1.90).set_z_index(0)
#     glow.set_fill(color=base_blue, opacity=0.050)
#     glow.set_stroke(width=0)
#     glow.move_to(center)
#
#     vignette = Circle(radius=max(fw, fh) * 0.78).set_z_index(0)
#     vignette.set_fill(color=BLACK, opacity=0.32)
#     vignette.set_stroke(width=0)
#     vignette.move_to([0, 0, 0])
#
#     haze = Circle(radius=max(fw, fh) * 0.62).set_z_index(0)
#     haze.set_fill(color=darken_hex(base_blue, 0.22), opacity=0.035)
#     haze.set_stroke(width=0)
#     haze.move_to(center + UP * 0.25)
#
#     grid = VGroup().set_z_index(1)
#
#     # Minor grid (slightly stronger than before)
#     minor_step = 0.65
#     x = fb["left"]
#     while x <= fb["right"] + 1e-6:
#         ln = Line([x, fb["bottom"], 0], [x, fb["top"], 0])
#         ln.set_stroke(base_blue, width=1, opacity=0.014)
#         grid.add(ln)
#         x += minor_step
#
#     y = fb["bottom"]
#     while y <= fb["top"] + 1e-6:
#         ln = Line([fb["left"], y, 0], [fb["right"], y, 0])
#         ln.set_stroke(base_blue, width=1, opacity=0.011)
#         grid.add(ln)
#         y += minor_step
#
#     # Major grid (punch)
#     major = VGroup().set_z_index(1)
#     major_step = 1.30
#     x = fb["left"]
#     while x <= fb["right"] + 1e-6:
#         ln = Line([x, fb["bottom"], 0], [x, fb["top"], 0])
#         ln.set_stroke(base_blue, width=1.2, opacity=0.038)
#         major.add(ln)
#         x += major_step
#
#     y = fb["bottom"]
#     while y <= fb["top"] + 1e-6:
#         ln = Line([fb["left"], y, 0], [fb["right"], y, 0])
#         ln.set_stroke(base_blue, width=1.2, opacity=0.030)
#         major.add(ln)
#         y += major_step
#
#     edge = VGroup(
#         Rectangle(width=fw + 2, height=1.75)
#         .set_fill(BLACK, 0.24)
#         .set_stroke(width=0)
#         .move_to([0, fb["top"] + 0.55, 0]),
#         Rectangle(width=fw + 2, height=1.75)
#         .set_fill(BLACK, 0.24)
#         .set_stroke(width=0)
#         .move_to([0, fb["bottom"] - 0.55, 0]),
#         Rectangle(width=2.25, height=fh + 2)
#         .set_fill(BLACK, 0.22)
#         .set_stroke(width=0)
#         .move_to([fb["left"] - 0.60, 0, 0]),
#         Rectangle(width=2.25, height=fh + 2)
#         .set_fill(BLACK, 0.22)
#         .set_stroke(width=0)
#         .move_to([fb["right"] + 0.60, 0, 0]),
#     ).set_z_index(2)
#
#     hud = RoundedRectangle(
#         width=sf["w"] + 0.70,
#         height=sf["h"] + 0.70,
#         corner_radius=0.30,
#     ).set_z_index(3)
#     hud.set_fill(opacity=0)
#     hud.set_stroke(color=base_blue, width=2.0, opacity=0.075)
#     hud.move_to([sf["cx"], sf["cy"], 0])
#
#     ticks = VGroup().set_z_index(3)
#     tick_len = 0.40
#     tick_w = 2.0
#     tick_op = 0.14
#     corners = [hud.get_corner(UL), hud.get_corner(UR), hud.get_corner(DL), hud.get_corner(DR)]
#     dirs = [(RIGHT, DOWN), (LEFT, DOWN), (RIGHT, UP), (LEFT, UP)]
#     for c, (dx, dy) in zip(corners, dirs):
#         t1 = Line(c, c + dx * tick_len)
#         t2 = Line(c, c + dy * tick_len)
#         for t in (t1, t2):
#             t.set_stroke(base_blue, width=tick_w, opacity=tick_op)
#         ticks.add(t1, t2)
#
#     particles = VGroup().set_z_index(2)
#     rng = np.random.default_rng(7)
#     for _ in range(18):
#         r = float(rng.uniform(0.02, 0.05))
#         p = Dot(
#             point=np.array([rng.uniform(fb["left"], fb["right"]), rng.uniform(fb["bottom"], fb["top"]), 0]),
#             radius=r,
#             color=base_blue,
#         )
#         p.set_opacity(float(rng.uniform(0.05, 0.12)))
#         drift = np.array([rng.uniform(-0.028, 0.028), rng.uniform(-0.018, 0.018), 0])
#
#         def _make_updater(v):
#             def _up(m, dt):
#                 m.shift(v * dt)
#                 x0, y0, _ = m.get_center()
#                 if x0 < fb["left"]:
#                     m.move_to([fb["right"], y0, 0])
#                 elif x0 > fb["right"]:
#                     m.move_to([fb["left"], y0, 0])
#                 if y0 < fb["bottom"]:
#                     m.move_to([x0, fb["top"], 0])
#                 elif y0 > fb["top"]:
#                     m.move_to([x0, fb["bottom"], 0])
#
#             return _up
#
#         p.add_updater(_make_updater(drift))
#         particles.add(p)
#
#     g.add(tint, plate, glow, haze, vignette, grid, major, edge, hud, ticks, particles)
#     return g
#
#
# def build_header(sf: Dict[str, float], title_text: str, sub_text: str) -> Tuple[Mobject, Mobject, Mobject, Mobject]:
#     title = _safe_text(
#         title_text,
#         font="Montserrat",
#         font_size=44,
#         color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"),
#         weight=BOLD,
#     ).set_z_index(200)
#     title.move_to([sf["cx"], sf["top"] - 0.95, 0])
#
#     underline = Line(LEFT, RIGHT).set_z_index(200)
#     underline.set_stroke(
#         width=4,
#         color=[getattr(Theme, "NEON_PINK", "#FB7185"), getattr(Theme, "NEON_BLUE", "#2DD4FF")],
#         opacity=0.90,
#     )
#     underline.scale_to_fit_width(min(sf["w"] * 0.72, 6.8))
#     underline.next_to(title, DOWN, buff=0.18)
#
#     sub = _safe_text(
#         sub_text,
#         font="Montserrat",
#         font_size=18,
#         color=getattr(Theme, "TEXT_SUB", "#CCCCCC"),
#     ).set_z_index(200)
#     sub.next_to(underline, DOWN, buff=0.18)
#
#     t = ValueTracker(0.0)
#
#     def dot_mob():
#         u = float(t.get_value()) % 1.0
#         p = underline.point_from_proportion(u)
#         d = Dot(point=p, radius=0.045, color=getattr(Theme, "NEON_BLUE", "#2DD4FF"))
#         d.set_z_index(205)
#         d.set_opacity(0.95)
#         return d
#
#     dot = always_redraw(dot_mob)
#
#     def _tick(_m, dt):
#         t.increment_value(dt * 0.18)
#
#     dot.add_updater(_tick)
#
#     return title, underline, sub, dot
#
#
# def build_dial(center: np.ndarray, outer_r: float) -> VGroup:
#     g = VGroup().set_z_index(10)
#
#     halo = Circle(radius=outer_r * 1.18).set_z_index(8)
#     halo.set_fill(getattr(Theme, "NEON_BLUE", "#2DD4FF"), 0.035)
#     halo.set_stroke(width=0)
#     halo.move_to(center)
#
#     backplate = Circle(radius=outer_r * 1.28).set_z_index(8)
#     backplate.set_fill("#05080B", 0.22)
#     backplate.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), width=2, opacity=0.06)
#     backplate.move_to(center)
#
#     plate = Circle(radius=outer_r * 1.06).set_z_index(9)
#     plate.set_fill("#05080B", 0.26)
#     plate.set_stroke(width=0)
#     plate.move_to(center)
#
#     rings = VGroup(
#         Circle(radius=outer_r * 1.08),
#         Circle(radius=outer_r * 1.20),
#         Circle(radius=outer_r * 1.32),
#     ).set_z_index(10)
#     for r in rings:
#         r.set_fill(opacity=0)
#         r.set_stroke(color=getattr(Theme, "TEXT_SUB", "#CCCCCC"), width=2, opacity=0.10)
#         r.move_to(center)
#
#     ticks = VGroup().set_z_index(11)
#     tick_r = outer_r * 1.36
#     for ang in np.linspace(0, TAU, 48, endpoint=False):
#         p1 = center + np.array([np.cos(ang) * (tick_r - 0.10), np.sin(ang) * (tick_r - 0.10), 0])
#         p2 = center + np.array([np.cos(ang) * tick_r, np.sin(ang) * tick_r, 0])
#         ln = Line(p1, p2)
#         ln.set_stroke(color=getattr(Theme, "TEXT_SUB", "#CCCCCC"), width=2, opacity=0.075)
#         ticks.add(ln)
#
#     glass = Circle(radius=outer_r * 1.06).set_z_index(90)
#     glass.set_fill(WHITE, 0.010)
#     glass.set_stroke(WHITE, width=2, opacity=0.07)
#     glass.move_to(center)
#
#     g.add(halo, backplate, plate, rings, ticks, glass)
#     return g
#
#
# # ==========================
# # Slot system (fixed layout + push-out)
# # ==========================
# def fixed_slots(sf: Dict[str, float], center: np.ndarray, lane_top: float) -> List[np.ndarray]:
#     rel = [
#         (-2.60, 2.10),
#         (0.00, 2.35),
#         (2.60, 2.05),
#         (-3.05, 1.05),
#         (3.05, 1.05),
#         (-3.05, -0.15),
#         (3.05, -0.15),
#         (-2.55, -1.40),
#         (0.00, -1.85),
#         (2.55, -1.40),
#     ]
#
#     out: List[np.ndarray] = []
#     max_y = lane_top - 0.30
#     min_y = sf["bottom"] + 0.60
#
#     for dx, dy in rel:
#         x = clamp(center[0] + dx, sf["left"] + 0.70, sf["right"] - 0.70)
#         y = clamp(center[1] + dy, min_y, max_y)
#         out.append(np.array([x, y, 0]))
#     return out
#
#
# def push_out_slots(slots: List[np.ndarray], center: np.ndarray, amount: float) -> List[np.ndarray]:
#     pushed: List[np.ndarray] = []
#     for p in slots:
#         v = p - center
#         n = float(np.linalg.norm(v))
#         if n < 1e-6:
#             pushed.append(p.copy())
#             continue
#         pushed.append(p + (v / n) * amount)
#     return pushed
#
#
# def assign_slots_nearest_side_biased(
#     slice_points: List[np.ndarray],
#     slots: List[np.ndarray],
#     center: np.ndarray,
# ) -> List[int]:
#     remaining = set(range(len(slots)))
#     out = [-1] * len(slice_points)
#
#     order = sorted(range(len(slice_points)), key=lambda i: -np.linalg.norm(slice_points[i] - center))
#     for i in order:
#         p = slice_points[i]
#         side = -1 if p[0] < center[0] else 1
#
#         best = None
#         best_score = 1e18
#         for s in remaining:
#             q = slots[s]
#             dist = float(np.linalg.norm(p - q))
#             slot_side = -1 if q[0] < center[0] else 1
#             penalty = 1.25 if slot_side != side else 0.0
#             score = dist + penalty
#             if score < best_score:
#                 best_score = score
#                 best = s
#
#         if best is None:
#             best = next(iter(remaining)) if remaining else 0
#
#         out[i] = int(best)
#         if best in remaining:
#             remaining.remove(best)
#
#     return out
#
#
# # ==========================
# # Commentary (center text, safe fit)
# # ==========================
# def make_commentary(center: np.ndarray, inner_r: float, label: str, name: str, pct_text: str, col: str) -> VGroup:
#     g = VGroup(
#         _safe_text(label, font="Consolas", font_size=14, color=getattr(Theme, "TEXT_SUB", "#CCCCCC")),
#         _safe_text(name, font="Montserrat", font_size=26, color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"), weight=BOLD),
#         _safe_text(pct_text, font="Montserrat", font_size=30, color=col, weight=BOLD),
#         _safe_text("computing…", font="Consolas", font_size=12, color=getattr(Theme, "TEXT_SUB", "#CCCCCC")),
#     ).arrange(DOWN, buff=0.06)
#     g.set_z_index(210)
#     g.scale_to_fit_width(inner_r * 1.62)
#     g.move_to(center)
#     return g
#
#
# # ==========================
# # Callouts (chip + elbow lines) - premium + auto match
# # ==========================
# def make_callout_chip(name: str, value: float, unit: str, rank: int, col: str, frac: float) -> VGroup:
#     rank_txt = _safe_text(
#         f"{rank:02d}",
#         font="Consolas",
#         font_size=12,
#         color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"),
#         weight=BOLD,
#     )
#     badge = Circle(radius=0.15)
#     badge.set_fill("#05080B", 0.86)
#     badge.set_stroke(lighten_hex(col, 0.18), 1.8, 0.95)
#     rank_txt.move_to(badge)
#
#     nm = text_ellipsize_to_width(
#         str(name),
#         font="Montserrat",
#         font_size=13,
#         max_width=2.25,
#         color=getattr(Theme, "TEXT_MAIN", "#FFFFFF"),
#     )
#
#     v_str = f"{int(round(value))}{unit}" if unit else f"{int(round(value))}"
#     vv = _safe_text(v_str, font="Montserrat", font_size=13, color=lighten_hex(col, 0.10), weight=BOLD)
#
#     row = VGroup(badge, rank_txt, nm, vv).arrange(RIGHT, buff=0.14, aligned_edge=DOWN)
#
#     bar_w = max(1.35, float(row.width * 0.52))
#     bar_h = 0.06
#     bar_bg = RoundedRectangle(width=bar_w, height=bar_h, corner_radius=0.03)
#     bar_bg.set_fill("#0B0F12", 0.88)
#     bar_bg.set_stroke(width=0)
#
#     bar_fill = RoundedRectangle(width=max(0.01, bar_w * clamp(frac, 0.05, 1.0)), height=bar_h, corner_radius=0.03)
#     bar_fill.set_fill(lighten_hex(col, 0.08), 0.70)
#     bar_fill.set_stroke(width=0)
#     bar_fill.align_to(bar_bg, LEFT)
#
#     bar = VGroup(bar_bg, bar_fill)
#     content = VGroup(row, bar).arrange(DOWN, buff=0.10, aligned_edge=LEFT)
#
#     pad_x, pad_y = 0.22, 0.16
#     bg = RoundedRectangle(width=content.width + 2 * pad_x, height=content.height + 2 * pad_y, corner_radius=0.16)
#     bg.set_fill("#05080B", 0.72)
#     bg.set_stroke(lighten_hex(col, 0.12), 1.7, 0.92)
#
#     glow = bg.copy()
#     glow.set_fill(opacity=0)
#     glow.set_stroke(color=col, width=11, opacity=0.10)
#
#     content.move_to(bg.get_center())
#     return VGroup(glow, bg, content).set_z_index(170)
#
#
# def make_callout(center: np.ndarray, outer_r: float, slice_mid: float, pop_vec: np.ndarray, chip: VGroup, col: str) -> VGroup:
#     base_edge = center + np.array([np.cos(slice_mid) * outer_r, np.sin(slice_mid) * outer_r, 0])
#     p0 = base_edge + pop_vec * 0.55
#
#     if chip.get_center()[0] >= center[0]:
#         dot_pos = chip.get_left() + LEFT * 0.12
#     else:
#         dot_pos = chip.get_right() + RIGHT * 0.12
#
#     # Callout line color should "feel" like slice (slightly dark + clean)
#     core_col = mix_hex(col, "#0A1118", 0.18)
#     glow_col = mix_hex(col, "#FFFFFF", 0.06)
#
#     dot = Dot(dot_pos, radius=0.05, color=lighten_hex(col, 0.14)).set_z_index(166)
#     # dot.set_opacity(0.0)  # start hidden (we'll fade in)
#
#     dirx = 1 if dot_pos[0] >= center[0] else -1
#     elbow_x = center[0] + dirx * (outer_r + 0.60)
#     p1 = np.array([elbow_x, dot_pos[1], 0])
#     p2 = dot_pos
#
#     core1 = Line(p0, p1)
#     core2 = Line(p1, p2)
#
#     for ln in (core1, core2):
#         ln.set_fill(opacity=0)
#         ln.set_z_index(165)
#         ln.set_stroke(color=core_col, width=2.8, opacity=0.0)  # start hidden (IMPORTANT)
#         try:
#             ln.set_stroke(line_cap=ROUND)
#         except Exception:
#             pass
#
#     glow1 = core1.copy()
#     glow2 = core2.copy()
#     for gl in (glow1, glow2):
#         gl.set_fill(opacity=0)
#         gl.set_z_index(164)
#         gl.set_stroke(color=glow_col, width=10.0, opacity=0.0)  # start hidden
#         try:
#             gl.set_stroke(line_cap=ROUND)
#         except Exception:
#             pass
#
#     # Start chip hidden (IMPORTANT)
#     chip.set_opacity(0.0)
#
#     # IMPORTANT: chip ko callout group me mat rakho (render bug avoid)
#     return VGroup(glow1, glow2, core1, core2, dot).set_z_index(165)
#
#
# # ==========================
# # Chip overlap resolver (SAFE)
# # ==========================
# def resolve_chip_overlaps(
#     chips: List[VGroup],
#     sf: Dict[str, float],
#     lane_top: float,
#     max_iters: int = 28,
#     pad: float = 0.06,
#     extra_push: float = 0.06,
# ) -> None:
#     if len(chips) <= 1:
#         return
#
#     min_y = sf["bottom"] + 0.20
#     max_y = lane_top - 0.20
#
#     def _chip_h(c: VGroup) -> float:
#         return float(c.get_top()[1] - c.get_bottom()[1])
#
#     def _clamp_chip(c: VGroup) -> None:
#         cx, cy, _ = c.get_center()
#         h = _chip_h(c)
#         lo = min_y + h / 2.0
#         hi = max_y - h / 2.0
#         cy2 = clamp(cy, lo, hi)
#         c.move_to([cx, cy2, 0])
#
#     def _aabb(c: VGroup) -> Tuple[float, float, float, float]:
#         x0 = float(c.get_left()[0]) - pad
#         x1 = float(c.get_right()[0]) + pad
#         y0 = float(c.get_bottom()[1]) - pad
#         y1 = float(c.get_top()[1]) + pad
#         return x0, x1, y0, y1
#
#     for c in chips:
#         _clamp_chip(c)
#
#     for _ in range(max_iters):
#         moved = False
#         for i in range(len(chips)):
#             for j in range(i + 1, len(chips)):
#                 a, b = chips[i], chips[j]
#                 ax0, ax1, ay0, ay1 = _aabb(a)
#                 bx0, bx1, by0, by1 = _aabb(b)
#
#                 x_overlap = min(ax1, bx1) - max(ax0, bx0)
#                 y_overlap = min(ay1, by1) - max(ay0, by0)
#
#                 if x_overlap > 0 and y_overlap > 0:
#                     push = (y_overlap / 2.0) + extra_push
#                     if a.get_center()[1] <= b.get_center()[1]:
#                         a.shift(DOWN * push)
#                         b.shift(UP * push)
#                     else:
#                         a.shift(UP * push)
#                         b.shift(DOWN * push)
#
#                     _clamp_chip(a)
#                     _clamp_chip(b)
#                     moved = True
#
#         if not moved:
#             break
#
#
# # ==========================
# # Scene (FINAL)
# # ==========================
# class DonutBreakdownFinal(Scene):
#     def construct(self):
#         self.camera.background_color = BACKGROUND_COLOR
#         sf = get_safe_frame(margin=0.70)
#
#         # Intro (LOCKED utils.py)
#         if HAS_PROJECT:
#             try:
#                 IntroManager.play_intro(
#                     self,
#                     brand_title="BIGDATA LEAK",
#                     brand_sub="SYSTEM BREACH DETECTED",
#                     feed_text="FEED_DONUT // BREAKDOWN",
#                     footer_text="CONFIDENTIAL // VERIFIED",
#                 )
#             except Exception:
#                 pass
#
#         # Data
#         csv_path = os.path.join(DATA_DIR, "market_share.csv")
#         meta, names, raw_vals, csv_colors, groups = read_market_csv(csv_path)
#
#         # Optional: merge tiny segments into Others
#         try:
#             min_pct = float(meta.get("OTHERS_MIN_PCT", "0") or "0")
#         except Exception:
#             min_pct = 0.0
#         names, raw_vals, csv_colors, groups = _merge_tiny_into_others(names, raw_vals, csv_colors, groups, min_pct=min_pct)
#
#         title_text = (meta.get("TITLE", "MARKET SHARE 2025") or "MARKET SHARE 2025").strip()
#         sub_text = (meta.get("SUB", "Global smartphone shipments") or "").strip()
#         unit = (meta.get("UNIT", "%") or "").strip()
#
#         # Layout anchors
#         center = np.array([0.0, -0.52, 0.0])
#         outer_r = 1.92
#         inner_r = 1.05
#
#         # Background + Dial
#         bg = build_background(sf, center, outer_r)
#         dial = build_dial(center, outer_r)
#         self.add(bg, dial)
#
#         # Header
#         title, underline, sub, underline_dot = build_header(sf, title_text, sub_text)
#         lane_top = sub.get_bottom()[1] - 0.55 if sub_text else underline.get_bottom()[1] - 0.55
#
#         # Donut base
#         shadow_ring = Annulus(inner_radius=inner_r, outer_radius=outer_r).set_z_index(25)
#         shadow_ring.set_fill(BLACK, 0.22).set_stroke(width=0)
#         shadow_ring.move_to(center + DOWN * 0.10)
#
#         track = Annulus(inner_radius=inner_r, outer_radius=outer_r).set_z_index(30)
#         track.set_fill("#060A0D", 0.72).set_stroke("#0D141A", 3, 1.0)
#         track.move_to(center)
#
#         outer_rim = Circle(radius=outer_r).set_z_index(55).set_fill(opacity=0)
#         outer_rim.set_stroke(WHITE, 3, 0.10).move_to(center)
#
#         inner_rim = Circle(radius=inner_r).set_z_index(56).set_fill(opacity=0)
#         inner_rim.set_stroke(WHITE, 2, 0.10).move_to(center)
#
#         core = Circle(radius=inner_r * 0.96).set_z_index(80)
#         core.set_fill("#05080B", 0.90).set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), 2, 0.18)
#         core.move_to(center)
#
#         self.add(shadow_ring, track, outer_rim, inner_rim, core)
#
#         # Commentary (boot)
#         commentary = make_commentary(center, inner_r, "SCAN", "MARKET", "…", getattr(Theme, "NEON_BLUE", "#2DD4FF"))
#         self.add(commentary)
#
#         # Edge case: no data
#         if not names or not raw_vals:
#             self.play(Write(title), run_time=0.45, rate_func=rf.ease_out_cubic)
#             self.play(Create(underline), run_time=0.30, rate_func=rf.ease_out_cubic)
#             self.add(underline_dot)
#             if sub_text:
#                 self.play(FadeIn(sub, shift=UP * 0.06), run_time=0.25, rate_func=rf.ease_out_cubic)
#             self.wait(1.0)
#             return
#
#         # Percent + ranks
#         pct_vals = normalize_to_pct(raw_vals)
#         total = float(np.sum(pct_vals)) if pct_vals else 100.0
#         total = max(1e-9, total)
#
#         vmax = float(np.max(raw_vals)) if raw_vals else 1.0
#         vmax = max(1e-9, vmax)
#
#         idx_desc = sorted(range(len(raw_vals)), key=lambda i: float(raw_vals[i]), reverse=True)
#         winner_idx = idx_desc[0] if idx_desc else 0
#         rank_map = {i: r + 1 for r, i in enumerate(idx_desc)}
#
#         idx_asc = sorted(range(len(raw_vals)), key=lambda i: float(raw_vals[i]))
#         if winner_idx in idx_asc:
#             idx_asc.remove(winner_idx)
#             idx_asc.append(winner_idx)
#
#         # Premium theme palette (AUTO, soothing)
#         base_blue = getattr(Theme, "NEON_BLUE", "#2DD4FF")
#         theme_palette = build_theme_palette(base_blue, len(names))
#
#         use_csv_colors = str(meta.get("USE_CSV_COLORS", "0")).strip() in ("1", "true", "True", "YES", "yes")
#
#         colors: List[str] = []
#         for i, nm in enumerate(names):
#             grp = groups[i] if i < len(groups) else "Default"
#             csv_c = csv_colors[i] if i < len(csv_colors) else ""
#             col, src = pick_premium_color(nm, grp, csv_c, i, theme_palette, use_csv_colors)
#             colors.append(col)
#             print(f"[DonutBreakdownFinal] COLOR_SOURCE={src} | name={nm} | group={grp} | color={col}")
#
#         # Donut build (sweep + reveal slices)
#         master_ring = Annulus(inner_radius=inner_r, outer_radius=outer_r).set_z_index(70)
#         master_ring.set_fill("#0A1118", 0.62)
#         master_ring.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), 2.0, 0.16)
#         master_ring.move_to(center)
#         master_ring.set_opacity(0.0)
#         self.add(master_ring)
#
#         sweep_t = ValueTracker(0.0)
#         sweep_span = TAU * 0.18
#
#         def sweep_band():
#             a0 = float(sweep_t.get_value())
#             return AnnularSector(
#                 inner_radius=inner_r - 0.02,
#                 outer_radius=outer_r + 0.06,
#                 arc_center=center,
#                 start_angle=a0,
#                 angle=sweep_span,
#                 fill_color=getattr(Theme, "NEON_BLUE", "#2DD4FF"),
#                 fill_opacity=0.10,
#                 stroke_width=0,
#             ).set_z_index(75)
#
#         def sweep_arc():
#             a0 = float(sweep_t.get_value()) + sweep_span * 0.65
#             arc = Arc(radius=outer_r + 0.02, start_angle=a0, angle=TAU * 0.10, arc_center=center)
#             arc.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), width=4, opacity=0.35)
#             arc.set_z_index(76)
#             return arc
#
#         sweep_band_m = always_redraw(sweep_band)
#         sweep_arc_m = always_redraw(sweep_arc)
#         self.add(sweep_band_m, sweep_arc_m)
#
#         # Build slices (hidden -> reveal)
#         start_angle = 90 * DEGREES
#         slice_groups: List[VGroup] = []
#         slice_mids: List[float] = []
#         slice_edge_points: List[np.ndarray] = []
#
#         for i, pct in enumerate(pct_vals):
#             ang = (float(pct) / total) * TAU
#             col = colors[i] if is_hex(colors[i]) else FALLBACK_COLORS[i % len(FALLBACK_COLORS)]
#
#             sh = AnnularSector(
#                 inner_radius=inner_r,
#                 outer_radius=outer_r,
#                 arc_center=center + DOWN * 0.10,
#                 start_angle=start_angle,
#                 angle=ang,
#                 fill_color=BLACK,
#                 fill_opacity=0.18,
#                 stroke_width=0,
#             ).set_z_index(60)
#
#             sec = AnnularSector(
#                 inner_radius=inner_r,
#                 outer_radius=outer_r,
#                 arc_center=center,
#                 start_angle=start_angle,
#                 angle=ang,
#                 fill_color=col,
#                 fill_opacity=0.88,  # slightly softer
#                 stroke_color="#0B0F12",
#                 stroke_width=3.0,
#             ).set_z_index(70)
#
#             hi = AnnularSector(
#                 inner_radius=inner_r + 0.06,
#                 outer_radius=outer_r - 0.10,
#                 arc_center=center,
#                 start_angle=start_angle,
#                 angle=ang,
#                 fill_color=WHITE,
#                 fill_opacity=0.06,
#                 stroke_width=0,
#             ).set_z_index(71)
#
#             rim = AnnularSector(
#                 inner_radius=outer_r - 0.12,
#                 outer_radius=outer_r,
#                 arc_center=center,
#                 start_angle=start_angle,
#                 angle=ang,
#                 fill_opacity=0.0,
#                 stroke_color=WHITE,
#                 stroke_width=2.0,
#             ).set_z_index(72)
#             rim.set_fill(opacity=0)
#             rim.set_stroke(opacity=0.10)
#
#             grp = VGroup(sh, sec, hi, rim).set_z_index(70)
#             grp.save_state()
#             grp.set_opacity(0.0)
#
#             self.add(grp)
#             slice_groups.append(grp)
#
#             mid = float(start_angle + ang / 2.0)
#             slice_mids.append(mid)
#             slice_edge_points.append(center + np.array([np.cos(mid) * outer_r, np.sin(mid) * outer_r, 0]))
#             start_angle += ang
#
#         # Slots + push-out
#         slots = fixed_slots(sf, center, lane_top)
#         slots = push_out_slots(slots, center, amount=0.55)
#         slot_ids = assign_slots_nearest_side_biased(slice_edge_points, slots, center)
#
#         # Build chips FIRST, resolve overlaps, THEN build callouts
#         chips: List[VGroup] = []
#         for i in range(len(names)):
#             col = colors[i] if is_hex(colors[i]) else FALLBACK_COLORS[i % len(FALLBACK_COLORS)]
#             frac = float(raw_vals[i] / vmax) if vmax > 0 else 0.1
#
#             chip = make_callout_chip(
#                 name=names[i],
#                 value=float(raw_vals[i]),
#                 unit=unit,
#                 rank=int(rank_map.get(i, i + 1)),
#                 col=col,
#                 frac=frac,
#             )
#
#             slot_pos = slots[slot_ids[i]] if 0 <= slot_ids[i] < len(slots) else slots[0]
#             chip.move_to(slot_pos)
#
#             cx = clamp(
#                 chip.get_center()[0],
#                 sf["left"] + chip.width / 2 + 0.05,
#                 sf["right"] - chip.width / 2 - 0.05,
#             )
#             cy = clamp(
#                 chip.get_center()[1],
#                 sf["bottom"] + chip.height / 2 + 0.05,
#                 lane_top - chip.height / 2 - 0.10,
#             )
#             chip.move_to([cx, cy, 0])
#             chips.append(chip)
#
#         resolve_chip_overlaps(chips, sf, lane_top)
#         # IMPORTANT: chips ko scene me separately add karo (initially hidden)
#         for ch in chips:
#             ch.set_z_index(180)
#             ch.save_state()  # <-- important: final visible state saved
#             ch.shift(DOWN * 0.06)  # small pre-offset for a nice pop
#             ch.set_opacity(0.0)  # start hidden, but saved_state is visible
#             self.add(ch)
#
#         callouts = VGroup().set_z_index(165)
#         self.add(callouts)
#         callout_by_idx: Dict[int, VGroup] = {}
#
#         for i in range(len(names)):
#             col = colors[i] if is_hex(colors[i]) else FALLBACK_COLORS[i % len(FALLBACK_COLORS)]
#             chip = chips[i]
#
#             pop_vec = np.array([np.cos(slice_mids[i]), np.sin(slice_mids[i]), 0]) * 0.22
#             callout = make_callout(
#                 center=center,
#                 outer_r=outer_r,
#                 slice_mid=slice_mids[i],
#                 pop_vec=pop_vec,
#                 chip=chip,
#                 col=col,
#             )
#             callouts.add(callout)
#             callout_by_idx[i] = callout
#
#         # ==========================
#         # HEADER + Donut creation (parallel feel)
#         # ==========================
#         self.play(Write(title), run_time=0.45, rate_func=rf.ease_out_cubic)
#         self.play(
#             AnimationGroup(
#                 Create(underline, rate_func=rf.ease_out_cubic),
#                 FadeIn(shadow_ring, shift=DOWN * 0.03, rate_func=rf.ease_out_cubic),
#                 lag_ratio=0.0,
#             ),
#             run_time=0.30,
#         )
#         self.add(underline_dot)
#         if sub_text:
#             self.play(FadeIn(sub, shift=UP * 0.06), run_time=0.25, rate_func=rf.ease_out_cubic)
#
#         master_ring.set_opacity(1.0)
#         self.play(DrawBorderThenFill(master_ring), run_time=0.40, rate_func=rf.ease_out_cubic)
#         self.play(sweep_t.animate.set_value(TAU), run_time=0.55, rate_func=rf.linear)
#         self.play(
#             LaggedStart(*[Restore(g) for g in slice_groups], lag_ratio=0.08),
#             run_time=1.05,
#             rate_func=rf.linear,
#         )
#         self.play(master_ring.animate.set_opacity(0.16), run_time=0.18, rate_func=rf.ease_out_cubic)
#         self.play(FadeOut(sweep_band_m), FadeOut(sweep_arc_m), run_time=0.18, rate_func=rf.ease_out_cubic)
#
#         # ==========================
#         # STAGE: Main story loop (with subtle scan sweep)
#         # ==========================
#         scan_t = ValueTracker(0.0)
#
#         def scan_arc():
#             a = float(scan_t.get_value())
#             arc = Arc(
#                 radius=outer_r + 0.03,
#                 start_angle=a,
#                 angle=TAU * 0.10,
#                 arc_center=center,
#             )
#             arc.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), width=3, opacity=0.12)
#             arc.set_z_index(77)
#             return arc
#
#         scan_arc_m = always_redraw(scan_arc)
#         self.add(scan_arc_m)
#
#         # Visibility constants (callout)
#         CORE_OP = 0.68
#         GLOW_OP = 0.12
#
#         for idx in idx_asc:
#             grp = slice_groups[idx]
#             sec = grp[1]
#
#             col = colors[idx] if is_hex(colors[idx]) else FALLBACK_COLORS[idx % len(FALLBACK_COLORS)]
#             pct_int = int(round(float(pct_vals[idx])))
#             is_winner = (idx == winner_idx)
#
#             pop = np.array([np.cos(slice_mids[idx]), np.sin(slice_mids[idx]), 0]) * 0.24
#
#             new_comm = make_commentary(center, inner_r, "SEGMENT", str(names[idx]).upper(), f"{pct_int}%", col)
#             self.play(
#                 Transform(commentary, new_comm),
#                 grp.animate.shift(pop).scale(1.03),
#                 scan_t.animate.increment_value(TAU * 0.35),
#                 run_time=0.55,
#                 rate_func=rf.ease_out_cubic,
#             )
#
#             # --- callout (FIX: ensure strokes restored; winner never misses)
#             c = callout_by_idx[idx]
#             glow1, glow2, core1, core2, dot = c
#             chip = chips[idx]  # chip ab scene me separately hai
#             # stable order
#
#             # Force correct visible stroke (IMPORTANT: fixes "last callout missing")
#             glow1.set_stroke(opacity=GLOW_OP)
#             glow2.set_stroke(opacity=GLOW_OP)
#             core1.set_stroke(opacity=CORE_OP)
#             core2.set_stroke(opacity=CORE_OP)
#
#             self.bring_to_front(c)  # lines + dot front
#             self.bring_to_front(chip)  # chip MUST be front (value box)
#
#             self.play(
#                 AnimationGroup(
#
#                     FadeIn(glow1, rate_func=rf.ease_out_cubic),
#                     FadeIn(glow2, rate_func=rf.ease_out_cubic),
#                     GrowFromPoint(core1, core1.get_start(), rate_func=rf.ease_out_cubic),
#                     GrowFromPoint(core2, core2.get_start(), rate_func=rf.ease_out_cubic),
#                     FadeIn(dot, shift=0.04 * UP, rate_func=rf.ease_out_cubic),
#                     Restore(chip, rate_func=rf.ease_out_cubic),
#                     lag_ratio=0.06,
#                 ),
#                 run_time=0.55,
#                 rate_func=rf.linear,
#             )
#
#             self.play(
#                 Indicate(dot, scale_factor=1.18, color=lighten_hex(col, 0.15)),
#                 run_time=0.18,
#                 rate_func=rf.ease_out_cubic,
#             )
#
#             self.wait(0.10)
#
#             if not is_winner:
#                 self.play(
#                     grp.animate.shift(-pop).scale(1 / 1.03),
#                     scan_t.animate.increment_value(TAU * 0.20),
#                     run_time=0.40,
#                     rate_func=rf.ease_in_out_sine,
#                 )
#             else:
#                 glow = sec.copy()
#                 glow.set_fill(opacity=0)
#                 glow.set_stroke(color=lighten_hex(col, 0.10), width=18, opacity=0.10)
#                 glow.set_z_index(73)
#                 self.add(glow)
#                 self.play(
#                     Indicate(sec, color=lighten_hex(col, 0.05), scale_factor=1.02),
#                     FadeIn(glow),
#                     run_time=0.45,
#                     rate_func=rf.ease_out_cubic,
#                 )
#
#         # Final leader (and keep winner callout visible)
#         winner_col = colors[winner_idx] if colors else getattr(Theme, "NEON_BLUE", "#2DD4FF")
#
#         # Ensure winner callout stays visible in final frame
#         try:
#             cwin = callout_by_idx[winner_idx]
#             glow1, glow2, core1, core2, dot = cwin
#             chip = chips[winner_idx]
#
#             glow1.set_stroke(opacity=GLOW_OP)
#             glow2.set_stroke(opacity=GLOW_OP)
#             core1.set_stroke(opacity=CORE_OP)
#             core2.set_stroke(opacity=CORE_OP)
#             dot.set_opacity(0.95)
#             chip.set_opacity(1.0)
#
#             self.bring_to_front(cwin)
#             self.bring_to_front(chip)
#         except Exception:
#             pass
#
#         leader = make_commentary(
#             center,
#             inner_r,
#             "LEADER",
#             str(names[winner_idx]).upper(),
#             f"{int(round(float(pct_vals[winner_idx])))}%",
#             winner_col,
#         )
#         self.play(Transform(commentary, leader), run_time=0.45, rate_func=rf.ease_out_cubic)
#
#         self.wait(2.0)


# src/templates/donut_breakdown.py
# FINAL GOD-TIER Donut Breakdown Template (Intro + Build + Story Loop)
# Manim Community v0.19.2 compatible
#
# Run:
#   manim -pqh donut_breakdown.py DonutBreakdownFinal

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

    from src.config import DATA_DIR, BACKGROUND_COLOR, Theme  # type: ignore
    from src.utils import IntroManager, get_safe_frame  # type: ignore
except Exception:
    HAS_PROJECT = False
    DATA_DIR = "."
    BACKGROUND_COLOR = "#0A0A0A"

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
        font="Montserrat",
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

    return VGroup(glow1, glow2, core1, core2, dot, chip).set_z_index(165)


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

    return glow1, glow2, core1, core2


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
# Scene (FINAL)
# ==========================
class DonutBreakdownFinal(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        sf = get_safe_frame(margin=0.70)

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

        # Data
        csv_path = os.path.join(DATA_DIR, "market_share.csv")
        meta, names, raw_vals, csv_colors, groups = read_market_csv(csv_path)

        # Optional: merge tiny segments into Others (only if meta asks)
        try:
            min_pct = float(meta.get("OTHERS_MIN_PCT", "0") or "0")
        except Exception:
            min_pct = 0.0
        names, raw_vals, csv_colors, groups = _merge_tiny_into_others(
            names, raw_vals, csv_colors, groups, min_pct=min_pct
        )

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

        # Edge case: no data
        if not names or not raw_vals:
            self.play(Write(title), run_time=0.45, rate_func=rf.ease_out_cubic)
            self.play(Create(underline), run_time=0.30, rate_func=rf.ease_out_cubic)
            self.add(underline_dot)
            if sub_text:
                self.play(FadeIn(sub, shift=UP * 0.06), run_time=0.25, rate_func=rf.ease_out_cubic)
            self.wait(1.0)
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
        master_ring = Annulus(inner_radius=inner_r, outer_radius=outer_r).set_z_index(70)
        master_ring.set_fill("#0A1118", 0.62)
        master_ring.set_stroke(getattr(Theme, "NEON_BLUE", "#2DD4FF"), 2.0, 0.16)
        master_ring.move_to(center)
        master_ring.set_opacity(0.0)
        self.add(master_ring)

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
                stroke_color="#0B0F12",
                stroke_width=3.0,
            ).set_z_index(70)

            hi = AnnularSector(
                inner_radius=inner_r + 0.06,
                outer_radius=outer_r - 0.10,
                arc_center=center,
                start_angle=start_angle,
                angle=ang,
                fill_color=WHITE,
                fill_opacity=0.06,
                stroke_width=0,
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
            rim.set_fill(opacity=0)
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
        self.play(DrawBorderThenFill(master_ring), run_time=0.40, rate_func=rf.ease_out_cubic)
        self.play(sweep_t.animate.set_value(TAU), run_time=0.55, rate_func=rf.linear)
        self.play(
            LaggedStart(*[Restore(g) for g in slice_groups], lag_ratio=0.08),
            run_time=1.05,
            rate_func=rf.linear,
        )
        self.play(master_ring.animate.set_opacity(0.16), run_time=0.18, rate_func=rf.ease_out_cubic)
        self.play(FadeOut(sweep_band_m), FadeOut(sweep_arc_m), run_time=0.18, rate_func=rf.ease_out_cubic)

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

        for idx in idx_asc:
            grp = slice_groups[idx]
            sec = grp[1]

            col = colors[idx] if is_hex(colors[idx]) else FALLBACK_COLORS[idx % len(FALLBACK_COLORS)]
            pct_int = int(round(float(pct_vals[idx])))
            is_winner = (idx == winner_idx)

            pop = np.array([np.cos(slice_mids[idx]), np.sin(slice_mids[idx]), 0]) * 0.24
            pop_vec = np.array([np.cos(slice_mids[idx]), np.sin(slice_mids[idx]), 0]) * 0.22  # must match callout math

            new_comm = make_commentary(center, inner_r, "SEGMENT", str(names[idx]).upper(), f"{pct_int}%", col)
            self.play(
                Transform(commentary, new_comm),
                grp.animate.shift(pop).scale(1.03),
                scan_t.animate.increment_value(TAU * 0.35),
                run_time=0.55,
                rate_func=rf.ease_out_cubic,
            )

            c = callout_by_idx[idx]
            glow1, glow2, core1, core2, dot, chip = c  # stable order

            # --- RETARGET lines to current slice position (FIX: winner callout missing/disconnect) ---
            dot_pos = dot.get_center()
            center_for_slice = center + pop  # slice is currently shifted by pop
            new_glow1, new_glow2, new_core1, new_core2 = _make_callout_lines_only(
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

            c.set_opacity(1.0)
            self.play(
                AnimationGroup(
                    FadeIn(glow1, rate_func=rf.ease_out_cubic),
                    FadeIn(glow2, rate_func=rf.ease_out_cubic),
                    GrowFromPoint(core1, core1.get_start(), rate_func=rf.ease_out_cubic),
                    GrowFromPoint(core2, core2.get_start(), rate_func=rf.ease_out_cubic),
                    FadeIn(dot, shift=0.04 * UP, rate_func=rf.ease_out_cubic),
                    FadeIn(chip, shift=0.06 * UP, rate_func=rf.ease_out_cubic),
                    lag_ratio=0.06,
                ),
                run_time=0.55,
                rate_func=rf.linear,
            )

            self.play(
                Indicate(dot, scale_factor=1.18, color=lighten_hex(col, 0.15)),
                run_time=0.18,
                rate_func=rf.ease_out_cubic,
            )

            self.wait(0.10)

            if not is_winner:
                self.play(
                    grp.animate.shift(-pop).scale(1 / 1.03),
                    scan_t.animate.increment_value(TAU * 0.20),
                    run_time=0.40,
                    rate_func=rf.ease_in_out_sine,
                )

                # retarget lines back to base center after slice returns
                dot_pos = dot.get_center()
                back_glow1, back_glow2, back_core1, back_core2 = _make_callout_lines_only(
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

            else:
                glow = sec.copy()
                glow.set_fill(opacity=0)
                glow.set_stroke(color=lighten_hex(col, 0.10), width=18, opacity=0.10)
                glow.set_z_index(73)
                self.add(glow)
                self.play(
                    Indicate(sec, color=lighten_hex(col, 0.05), scale_factor=1.02),
                    FadeIn(glow),
                    run_time=0.45,
                    rate_func=rf.ease_out_cubic,
                )

        # Final leader
        winner_col = colors[winner_idx] if colors else getattr(Theme, "NEON_BLUE", "#2DD4FF")
        leader = make_commentary(
            center,
            inner_r,
            "LEADER",
            str(names[winner_idx]).upper(),
            f"{int(round(float(pct_vals[winner_idx])))}%",
            winner_col,
        )
        self.play(Transform(commentary, leader), run_time=0.45, rate_func=rf.ease_out_cubic)

        self.wait(2.0)
