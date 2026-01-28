# panel_preview.py
import os
import sys
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
from manim import *

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

from src.config import BACKGROUND_COLOR, Theme  # noqa: E402
from src.utils import get_safe_frame, clamp_x, clamp_y  # noqa: E402

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def _is_hex_color(s: Optional[str]) -> bool:
    return isinstance(s, str) and bool(_HEX_RE.match(s.strip()))


def _ellipsize(s: str, max_chars: int) -> str:
    s = str(s)
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return "…"
    return s[: max_chars - 1] + "…"


def _assign_color_fallback(i: int) -> str:
    palette = [
        getattr(Theme, "NEON_BLUE", "#00F0FF"),
        getattr(Theme, "NEON_PURPLE", "#BD00FF"),
        getattr(Theme, "NEON_PINK", "#FF0055"),
        getattr(Theme, "NEON_ORANGE", "#FF9900"),
        getattr(Theme, "NEON_GREEN", "#00FF66"),
        getattr(Theme, "NEON_YELLOW", "#FFFF00"),
    ]
    return palette[i % len(palette)]


def _normalize_items(items: List[Tuple[str, float, Optional[str]]]) -> List[Tuple[str, float, str]]:
    out = []
    for i, (name, pct, col) in enumerate(items):
        pct = float(pct) if pct is not None else 0.0
        pct = float(np.clip(pct, 0.0, 100.0))
        if _is_hex_color(col):
            color = col.strip()
        else:
            color = _assign_color_fallback(i)
        out.append((str(name).strip(), pct, color))
    return out


def _top4_plus_others(items: List[Tuple[str, float, str]]) -> List[Tuple[str, float, str]]:
    if not items:
        return []
    items_sorted = sorted(items, key=lambda x: float(x[1]), reverse=True)
    top4 = items_sorted[: min(4, len(items_sorted))]
    rest = items_sorted[min(4, len(items_sorted)) :]

    if rest:
        others_pct = float(np.sum([p for _, p, _ in rest]))
        top4.append(("OTHERS", others_pct, getattr(Theme, "NEON_YELLOW", "#FFFF00")))
    return top4


def build_quick_scan_panel(
    sf: dict,
    *,
    unit: str = "%",
    items: List[Tuple[str, float, Optional[str]]] = None,
    winner_name: str = "APPLE",
) -> Tuple[VGroup, Dict[str, VGroup]]:
    """
    QUICK SCAN panel: Top 4 + Others.
    Premium spacing, taller frame, slimmer glow bars, clean header.
    """
    if items is None:
        items = []

    items_norm = _normalize_items(items)
    items_final = _top4_plus_others(items_norm)

    # ---- frame sizing (taller + less cramped)
    panel_w = sf["w"] * 0.46
    panel_h = 3.35
    corner = 0.24

    frame = RoundedRectangle(width=panel_w, height=panel_h, corner_radius=corner).set_z_index(50)
    frame.set_fill(color="#05080B", opacity=0.72)
    frame.set_stroke(color=getattr(Theme, "NEON_BLUE", "#00F0FF"), width=2.2, opacity=0.92)

    # inner soft frame (aesthetic)
    inner = RoundedRectangle(width=panel_w * 0.94, height=panel_h * 0.92, corner_radius=0.22).set_z_index(50)
    inner.set_fill(opacity=0)
    inner.set_stroke(color=WHITE, width=1.2, opacity=0.06)
    inner.move_to(frame)

    # top accent (thin, premium)
    accent = Line(LEFT, RIGHT).set_z_index(51)
    accent.set_stroke(
        color=[getattr(Theme, "NEON_PINK", "#FF0055"), getattr(Theme, "NEON_BLUE", "#00F0FF")],
        width=2.6,
        opacity=0.88,
    )
    accent.scale_to_fit_width(panel_w * 0.90)

    # header: ONLY QUICK SCAN
    header = Text("QUICK SCAN", font="Montserrat", font_size=16, color=Theme.TEXT_MAIN, weight=BOLD).set_z_index(52)

    maxp = max([p for _, p, _ in items_final], default=1.0)
    maxp = max(1e-6, float(maxp))

    row_map: Dict[str, VGroup] = {}

    def make_row(name: str, pct: float, col: str) -> VGroup:
        is_win = str(name).strip().lower() == str(winner_name).strip().lower()

        # left marker (small, clean)
        marker = RoundedRectangle(width=0.16, height=0.16, corner_radius=0.05).set_z_index(52)
        marker.set_fill(color=col, opacity=1.0)
        marker.set_stroke(width=0)

        # text: cleaner + "catchy" via weight + spacing
        name_txt = Text(
            _ellipsize(str(name).upper(), 14),
            font="Montserrat",
            font_size=13,
            color=Theme.TEXT_MAIN,
            weight=BOLD if is_win else SEMIBOLD,
        ).set_z_index(52)

        pct_txt = Text(
            f"{int(round(pct))}{unit}",
            font="Consolas",
            font_size=13,
            color=col,
            weight=BOLD,
        ).set_z_index(52)

        head_left = VGroup(marker, name_txt).arrange(RIGHT, buff=0.12)
        head = VGroup(head_left, pct_txt).arrange(RIGHT, buff=0.22)

        # slim bar + subtle glow
        bar_w = panel_w * 0.56
        bar_h = 0.072

        bar_bg = RoundedRectangle(width=bar_w, height=bar_h, corner_radius=bar_h / 2).set_z_index(51)
        bar_bg.set_fill(color=WHITE, opacity=0.06).set_stroke(width=0)

        fill_w = bar_w * float(np.clip(float(pct) / maxp, 0.10, 1.0))
        bar_fill = RoundedRectangle(width=fill_w, height=bar_h, corner_radius=bar_h / 2).set_z_index(52)
        bar_fill.set_fill(color=col, opacity=0.88).set_stroke(width=0)
        bar_fill.align_to(bar_bg, LEFT)

        bar_glow = bar_fill.copy().set_z_index(51)
        bar_glow.set_fill(opacity=0)
        bar_glow.set_stroke(color=col, width=8, opacity=0.12)

        bar = VGroup(bar_bg, bar_glow, bar_fill)

        # row container (less heavy, less crowded)
        row_w = panel_w * 0.92
        row_h = head.height + bar.height + 0.22

        row_bg = RoundedRectangle(width=row_w, height=row_h, corner_radius=0.16).set_z_index(51)
        row_bg.set_fill(color="#070A0C", opacity=0.26)
        row_bg.set_stroke(color=col, width=1.5 if is_win else 1.0, opacity=0.55 if is_win else 0.18)

        content = VGroup(head, bar).arrange(DOWN, buff=0.10, aligned_edge=LEFT).set_z_index(52)
        content.move_to(row_bg.get_center()).align_to(row_bg, LEFT).shift(RIGHT * 0.18)

        return VGroup(row_bg, content).set_z_index(52)

    rows = VGroup().set_z_index(52)
    for nm, pct, col in items_final:
        r = make_row(nm, pct, col)
        rows.add(r)
        row_map[str(nm).strip().lower()] = r

    # luxury spacing
    rows.arrange(DOWN, buff=0.16, aligned_edge=LEFT)

    panel = VGroup(frame, inner, accent, header, rows).set_z_index(50)

    # ---- position: top-right but pushed DOWN (no subtitle collision)
    anchor_y = sf["top"] - 2.70
    panel.move_to([sf["right"] - panel_w / 2, anchor_y, 0])
    panel.move_to(
        [
            clamp_x(panel.get_center()[0], panel.width, margin=0.70),
            clamp_y(panel.get_center()[1], panel.height, margin=0.70),
            0,
        ]
    )

    # internal anchors
    left_x = frame.get_left()[0] + 0.22
    top_y = frame.get_top()[1]

    accent.move_to(frame.get_top() + DOWN * 0.24)
    header.move_to([left_x + header.width / 2, top_y - 0.44, 0])

    rows.align_to(header, LEFT)
    rows.move_to([left_x + rows.width / 2, top_y - 0.92 - rows.height / 2, 0])

    # ensure frame fits content (taller frame kept; this prevents crowd)
    content = VGroup(header, rows)
    target_h = (frame.get_top()[1] - content.get_bottom()[1]) + 0.32
    target_h = float(np.clip(target_h, 3.10, 3.80))
    frame.stretch_to_fit_height(target_h)
    frame.move_to(panel.get_center())

    inner.stretch_to_fit_height(frame.height * 0.92)
    inner.stretch_to_fit_width(frame.width * 0.94)
    inner.move_to(frame)

    # re-anchor after stretch
    top_y = frame.get_top()[1]
    accent.move_to(frame.get_top() + DOWN * 0.24)
    header.move_to([left_x + header.width / 2, top_y - 0.44, 0])
    rows.move_to([left_x + rows.width / 2, top_y - 0.92 - rows.height / 2, 0])

    return panel, row_map


class PanelOnlyPreview(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        sf = get_safe_frame(margin=0.70)

        # Dummy data (panel shows TOP4 + OTHERS automatically)
        items = [
            ("Apple", 35, "#00F0FF"),
            ("Samsung", 25, "#BD00FF"),
            ("Xiaomi", 15, "#FF0055"),
            ("Oppo", 10, "#FF9900"),
            ("Vivo", 8, "#00FF66"),
            ("Others", 7, "#FFFF00"),
        ]

        panel, _ = build_quick_scan_panel(
            sf,
            unit="%",
            items=items,
            winner_name="Apple",
        )

        self.add(panel)
        self.wait(3)
