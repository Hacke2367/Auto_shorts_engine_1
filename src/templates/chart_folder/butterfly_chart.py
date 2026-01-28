# src/templates/chart_folder/butterfly_chart.py
# Manim Community v0.19.1 (works fine on 0.19.2 too)

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Tuple, List, Literal

import numpy as np
import pandas as pd
from manim import *
from manim import rate_functions as rf

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

# --- IMPORTS (Robust) ---
try:
    from src.config import BACKGROUND_COLOR
    from src.utils import (
        IntroManager,
        Brand,
        get_safe_frame,
        make_floating_particles,
    )
except Exception:
    BACKGROUND_COLOR = "#050505"

    class Brand:
        CYAN = "#00F0FF"
        PINK = "#FF0055"
        GREEN = "#00FF66"
        WHITE = "#FFFFFF"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"

    config.frame_height = 16.0
    config.frame_width = 9.0

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

    def make_floating_particles(*args, **kwargs):
        return VGroup()

    class IntroManager:
        @staticmethod
        def play_intro(*args, **kwargs):
            return


# ==========================
# DESIGN (single vibe)
# ==========================
class Design:
    BG = BACKGROUND_COLOR if "BACKGROUND_COLOR" in globals() else "#050505"

    CYAN = getattr(Brand, "CYAN", "#00F0FF")
    PINK = getattr(Brand, "PINK", "#FF0055")
    GREEN = getattr(Brand, "GREEN", "#00FF66")
    WHITE = getattr(Brand, "WHITE", "#FFFFFF")

    TEXT_MAIN = getattr(Brand, "TEXT_MAIN", "#FFFFFF")
    TEXT_SUB = getattr(Brand, "TEXT_SUB", "#B8B8B8")

    GOLD = "#FFD700"

    GLASS_FILL = "#0B0F12"
    PANEL_STROKE = "#1B2A33"

    BAR_BG = "#070A0C"
    GRID_OP = 0.05

    P1_GRAD = [CYAN, "#0055FF"]
    P2_GRAD = [PINK, "#8800FF"]


EndBoxMode = Literal["AUTO", "OUTSIDE", "INSIDE"]


@dataclass(frozen=True)
class EndBoxPolicy:
    """
    AUTO: prefer OUTSIDE, fallback to INSIDE if it would clip the safe-frame.
    OUTSIDE: force outside, but still clamp to safe-frame (less clean).
    INSIDE: force inside track end.
    """
    mode: EndBoxMode = "AUTO"
    gap_outside: float = 0.18
    pad_inside: float = 0.14
    safe_pad: float = 0.06


@dataclass(frozen=True)
class LayoutCfg:
    safe_margin: float = 0.60

    header_top_pad: float = 0.85
    header_to_rows_pad: float = 1.00

    timeline_h: float = 1.30
    timeline_bottom_lift: float = 0.95
    rows_to_timeline_pad: float = 0.95

    rows_shift_down: float = 0.45

    node_radius: float = 0.40
    node_w: float = 0.82

    bar_h: float = 0.48
    bar_tip_len: float = 0.30
    bar_tip_gutter: float = 0.62

    endbox_h: float = 0.44
    endbox_text_pad: float = 0.16

    row_gap_min: float = 0.90
    row_gap_max: float = 1.35

    z_bg: int = 0
    z_atmo: int = 1
    z_fx: int = 2
    z_spine: int = 10
    z_track: int = 20
    z_bar: int = 28
    z_node: int = 35
    z_header: int = 60
    z_ui: int = 55
    z_value: int = 85
    z_winner_dim: int = 120
    z_winner: int = 140

    endbox_policy: EndBoxPolicy = EndBoxPolicy()


# ==========================
# CSV helpers (supports meta first line: "#P1=...,P2=...")
# ==========================
def _parse_players_from_first_line(path: str) -> Tuple[str, str]:
    p1 = "ITEM A"
    p2 = "ITEM B"
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("#") and ("P1=" in first) and ("P2=" in first):
            first = first[1:]
            parts = [x.strip() for x in first.split(",") if x.strip()]
            for part in parts:
                if part.upper().startswith("P1="):
                    p1 = part.split("=", 1)[1].strip() or p1
                if part.upper().startswith("P2="):
                    p2 = part.split("=", 1)[1].strip() or p2
    except Exception:
        pass
    return p1, p2


def _load_butterfly_df(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, comment="#")
    df.columns = [str(c).strip() for c in df.columns]

    if not {"Attribute", "P1_Value", "P2_Value"}.issubset(set(df.columns)):
        if len(df.columns) >= 3:
            attr_col, p1_col, p2_col = df.columns[0], df.columns[1], df.columns[2]
            df = df.rename(columns={attr_col: "Attribute", p1_col: "P1_Value", p2_col: "P2_Value"})
        else:
            raise ValueError(f"CSV columns mismatch. Found: {list(df.columns)}")

    df = df.copy()
    df["Attribute"] = df["Attribute"].astype(str).str.strip().str.upper()
    df["P1_Value"] = pd.to_numeric(df["P1_Value"], errors="coerce").fillna(0.0)
    df["P2_Value"] = pd.to_numeric(df["P2_Value"], errors="coerce").fillna(0.0)

    df = df[df["Attribute"].astype(str).str.len() > 0]
    df = df.reset_index(drop=True)
    return df


def _format_attr_label(label: str) -> str:
    s = (label or "").strip().upper()
    if len(s) <= 7:
        return s
    if " " in s:
        parts = s.split()
        if len(parts) >= 2:
            return f"{parts[0]}\n{parts[1]}"
    mid = max(3, len(s) // 2)
    return f"{s[:mid]}\n{s[mid:]}"


@dataclass(frozen=True)
class CompactSpec:
    divisor: float
    decimals: int
    suffix: str


def _compact_spec_for_target(target_value: float) -> CompactSpec:
    a = float(abs(target_value))
    if a < 1000:
        return CompactSpec(divisor=1.0, decimals=0, suffix="")
    if a < 1_000_000:
        return CompactSpec(divisor=1_000.0, decimals=1, suffix="K")
    if a < 1_000_000_000:
        return CompactSpec(divisor=1_000_000.0, decimals=1, suffix="M")
    return CompactSpec(divisor=1_000_000_000.0, decimals=1, suffix="B")


def _nice_endbox_width(spec: CompactSpec, negative_possible: bool) -> float:
    base = 1.18 if spec.suffix == "" else 1.42
    return base + (0.10 if negative_possible else 0.0)


def _high_contrast_text(mob: Mobject) -> Mobject:
    mob.set_opacity(1.0)
    try:
        mob.set_stroke(color=BLACK, width=1, opacity=0.35)
    except Exception:
        pass
    return mob


def _fits_safe_x(mob: Mobject, sf: dict, safe_pad: float) -> bool:
    return (mob.get_left()[0] >= sf["left"] + safe_pad) and (mob.get_right()[0] <= sf["right"] - safe_pad)


def _clamp_x_into_safe(mob: Mobject, sf: dict, safe_pad: float) -> None:
    left_min = sf["left"] + safe_pad + mob.width / 2
    right_max = sf["right"] - safe_pad - mob.width / 2
    x = float(np.clip(mob.get_center()[0], left_min, right_max))
    mob.move_to([x, mob.get_center()[1], 0])


def _place_end_box(
    side: Literal["L", "R"],
    end_box: VGroup,
    track_rect: Mobject,
    sf: dict,
    policy: EndBoxPolicy,
) -> Literal["OUTSIDE", "INSIDE"]:
    """
    Places end_box at same y as track_rect, preferring OUTSIDE.
    AUTO: outside if fits safe-frame, else inside.
    OUTSIDE: outside then clamp into safe-frame.
    INSIDE: inside.
    """
    y = track_rect.get_center()[1]
    outside_pos = (
        track_rect.get_left() + LEFT * (end_box[0].width / 2 + policy.gap_outside)
        if side == "L"
        else track_rect.get_right() + RIGHT * (end_box[0].width / 2 + policy.gap_outside)
    )
    inside_pos = (
        track_rect.get_left() + RIGHT * (end_box[0].width / 2 + policy.pad_inside)
        if side == "L"
        else track_rect.get_right() + LEFT * (end_box[0].width / 2 + policy.pad_inside)
    )

    if policy.mode == "INSIDE":
        end_box.move_to([inside_pos[0], y, 0])
        return "INSIDE"

    end_box.move_to([outside_pos[0], y, 0])
    if policy.mode == "OUTSIDE":
        _clamp_x_into_safe(end_box, sf, policy.safe_pad)
        return "OUTSIDE"

    # AUTO
    if _fits_safe_x(end_box, sf, policy.safe_pad):
        return "OUTSIDE"

    end_box.move_to([inside_pos[0], y, 0])
    return "INSIDE"


# ==========================
# ✅ NUMBER FIX (stable on Windows/Cairo): use Text + ValueTracker instead of Integer/DecimalNumber
# ==========================
def _fmt_compact_value(raw_value: float, spec: CompactSpec) -> str:
    """
    raw_value = original number (not divided)
    spec.divisor/spec.decimals/spec.suffix control formatting.
    """
    v = float(raw_value) / float(spec.divisor)
    # For plain numbers, keep it integer-looking (your decision: integer is best)
    if spec.suffix == "":
        return str(int(round(v)))
    # For K/M/B keep 1 decimal but trim trailing .0
    s = f"{v:.{spec.decimals}f}"
    s = s.rstrip("0").rstrip(".")
    return s


def _make_tracker_text(
    tracker: ValueTracker,
    font_size: int,
    z: int,
    font: str = "Montserrat",
    weight: str = BOLD,
    color=WHITE,
    stroke_color=BLACK,
    stroke_w: float = 1.0,
    stroke_op: float = 0.35,
) -> Text:
    """
    Creates a Text that updates from a ValueTracker (int rounded).
    This avoids the "numbers vanish" issue from Integer/DecimalNumber rebuilds.
    """
    t = Text("0", font=font, weight=weight, font_size=font_size, color=color).set_z_index(z)
    try:
        t.set_stroke(stroke_color, width=stroke_w, opacity=stroke_op)
    except Exception:
        pass

    def _upd(m: Mobject):
        v = int(round(tracker.get_value()))
        new = Text(str(v), font=font, weight=weight, font_size=font_size, color=color)
        try:
            new.set_stroke(stroke_color, width=stroke_w, opacity=stroke_op)
        except Exception:
            pass
        new.set_z_index(z)
        m.become(new)

    t.add_updater(_upd)
    return t


class ButterflyChart(Scene):
    def construct(self):
        cfg = LayoutCfg()
        self.camera.background_color = Design.BG
        sf = get_safe_frame(margin=cfg.safe_margin)

        # ==========================================
        # 1) INTRO (utils IntroManager only)
        # ==========================================
        try:
            IntroManager.play_intro(
                self,
                brand_title="BIGDATA LEAK",
                brand_sub="SYSTEM BREACH DETECTED",
                feed_text="FEED_BUTTERFLY // VS",
                footer_text="CONFIDENTIAL // VERIFIED",
            )
        except Exception:
            pass

        # ==========================================
        # 2) DATA
        # ==========================================
        csv_candidates = [
            os.path.join(project_root, "Data", "butterfly_data.csv"),
            os.path.join(current_dir, "Data", "butterfly_data.csv"),
            os.path.join(current_dir, "butterfly_data.csv"),
            os.path.join(project_root, "butterfly_data.csv"),
            "butterfly_data.csv",
        ]
        csv_path = next((p for p in csv_candidates if os.path.exists(p)), None)

        if csv_path:
            p1_name, p2_name = _parse_players_from_first_line(csv_path)
            df = _load_butterfly_df(csv_path)
        else:
            p1_name, p2_name = "ITEM A", "ITEM B"
            df = pd.DataFrame(
                [
                    {"Attribute": "SPEED", "P1_Value": 88, "P2_Value": 92},
                    {"Attribute": "HANDLING", "P1_Value": 95, "P2_Value": 80},
                    {"Attribute": "ACCEL", "P1_Value": 78, "P2_Value": 88},
                    {"Attribute": "LUXURY", "P1_Value": 90, "P2_Value": 65},
                    {"Attribute": "TECH", "P1_Value": 85, "P2_Value": 95},
                ]
            )

        attrs: List[str] = df["Attribute"].tolist()
        p1_vals_raw = df["P1_Value"].astype(float).tolist()
        p2_vals_raw = df["P2_Value"].astype(float).tolist()

        # Display as integer (simple), keep compare safe
        p1_vals = [float(int(round(v))) for v in p1_vals_raw]
        p2_vals = [float(int(round(v))) for v in p2_vals_raw]

        negative_possible = any(v < 0 for v in (p1_vals + p2_vals))
        max_val = float(max(100.0, np.max(np.abs(np.array(p1_vals + p2_vals + [0.0])))))

        # Auto thin bars when many attributes (keeps code small; prevents breakage)
        n_attr = max(1, len(attrs))
        bar_h = cfg.bar_h
        if n_attr >= 13:
            bar_h = 0.44
        if n_attr >= 17:
            bar_h = 0.40

        # ==========================================
        # 3) ATMOSPHERE
        # ==========================================
        grid = NumberPlane(
            x_range=[-10, 10, 2],
            y_range=[-16, 16, 2],
            background_line_style={"stroke_color": Design.CYAN, "stroke_width": 1, "stroke_opacity": Design.GRID_OP},
            axis_config={"stroke_width": 0},
        ).set_z_index(cfg.z_bg)
        self.add(grid)

        ring1 = DashedVMobject(Circle(radius=3.2), num_dashes=36).set_z_index(cfg.z_atmo)
        ring1.set_stroke(color=Design.CYAN, width=2.2, opacity=0.14)
        ring2 = DashedVMobject(Circle(radius=4.8), num_dashes=54).set_z_index(cfg.z_atmo)
        ring2.set_stroke(color=Design.PINK, width=1.8, opacity=0.10)
        ring3 = Circle(radius=6.4).set_z_index(cfg.z_atmo)
        ring3.set_stroke(color=WHITE, width=1.2, opacity=0.06)
        self.add(ring1, ring2, ring3)

        ring1.add_updater(lambda m, dt: m.rotate(0.10 * dt))
        ring2.add_updater(lambda m, dt: m.rotate(-0.07 * dt))
        ring3.add_updater(lambda m, dt: m.rotate(0.02 * dt))

        try:
            particles = make_floating_particles(
                n=26,
                color=Design.CYAN,
                radius_range=(0.02, 0.05),
                opacity_range=(0.06, 0.18),
                drift=0.05,
                margin=cfg.safe_margin,
            ).set_z_index(cfg.z_fx)
            self.add(particles)
        except Exception:
            pass

        # ==========================================
        # 4) HEADER (✅ score stable now)
        # ==========================================
        header_top_y = sf["top"] - cfg.header_top_pad
        title = Text("WHO WILL DOMINATE?", font="Montserrat", weight=BOLD, font_size=26, color=Design.TEXT_SUB).set_z_index(cfg.z_header)
        title.move_to([sf["cx"], header_top_y, 0])

        underline = Line(LEFT * 3.0, RIGHT * 3.0).set_z_index(cfg.z_header)
        underline.set_stroke(width=3, color=[Design.CYAN, Design.PINK], opacity=0.85)
        underline.next_to(title, DOWN, buff=0.22)

        scan_dot = Dot(radius=0.06, color=WHITE).set_z_index(cfg.z_header + 1)
        scan_dot.move_to(underline.get_left())

        def _scan(m, dt):
            if not hasattr(m, "_phase"):
                m._phase = 0.0
            m._phase += dt
            t = (np.sin(m._phase * 2.0) + 1) / 2
            m.move_to(underline.get_left() + (underline.get_right() - underline.get_left()) * t)

        scan_dot.add_updater(_scan)

        # ✅ CHANGED: returns (grp, ring, score_text, score_tracker)
        def player_card(name: str, accent: str, side: str) -> Tuple[VGroup, Circle, Text, ValueTracker]:
            plate_w = 3.10
            plate_h = 1.10

            plate = RoundedRectangle(width=plate_w, height=plate_h, corner_radius=0.22).set_z_index(cfg.z_header + 5)
            plate.set_fill(color=Design.GLASS_FILL, opacity=0.62)
            plate.set_stroke(color=Design.PANEL_STROKE, width=2, opacity=0.95)

            glow = plate.copy().set_z_index(cfg.z_header + 4)
            glow.set_fill(opacity=0)
            glow.set_stroke(color=accent, width=10, opacity=0.08)

            ring = Circle(radius=0.42).set_z_index(cfg.z_header + 7)
            ring.set_fill(color="#0A0A0A", opacity=1.0)
            ring.set_stroke(color=accent, width=3, opacity=0.95)

            # ✅ FIX: stable score (Text + tracker)
            score_t = ValueTracker(0.0)
            score = _make_tracker_text(score_t, font_size=34, z=cfg.z_header + 9)
            # keep it centered in ring
            score.add_updater(lambda m: m.move_to(ring.get_center()))

            name_txt = Text(name, font="Montserrat", weight=BOLD, font_size=22, color=WHITE).set_z_index(cfg.z_header + 9)
            _high_contrast_text(name_txt)
            sub = Text("SCORE", font="Montserrat", font_size=14, color=Design.TEXT_SUB).set_z_index(cfg.z_header + 9)

            if side == "L":
                ring.move_to(plate.get_left() + RIGHT * 0.60)
                name_txt.next_to(ring, RIGHT, buff=0.22).align_to(plate, UP).shift(DOWN * 0.18)
                sub.next_to(name_txt, DOWN, buff=0.06).align_to(name_txt, LEFT)
            else:
                ring.move_to(plate.get_right() + LEFT * 0.60)
                name_txt.next_to(ring, LEFT, buff=0.22).align_to(plate, UP).shift(DOWN * 0.18)
                sub.next_to(name_txt, DOWN, buff=0.06).align_to(name_txt, RIGHT)

            grp = VGroup(glow, plate, ring, score, name_txt, sub)
            return grp, ring, score, score_t

        p1_card, p1_ring, p1_score, p1_score_t = player_card(p1_name, Design.CYAN, "L")
        p2_card, p2_ring, p2_score, p2_score_t = player_card(p2_name, Design.PINK, "R")

        header_row_y = underline.get_bottom()[1] - 0.82
        p1_card.move_to([sf["left"] + p1_card.width / 2, header_row_y, 0])
        p2_card.move_to([sf["right"] - p2_card.width / 2, header_row_y, 0])

        conn_l = p1_card.get_right() + RIGHT * 0.18
        conn_r = p2_card.get_left() + LEFT * 0.18
        connector = Line(conn_l, conn_r).set_z_index(cfg.z_header + 6)
        connector.set_stroke(color=WHITE, width=2, opacity=0.22)

        vs_chip = RoundedRectangle(width=1.05, height=0.48, corner_radius=0.18).set_z_index(cfg.z_header + 10)
        vs_chip.set_fill(color="#000000", opacity=0.55)
        vs_chip.set_stroke(color=Design.GOLD, width=2, opacity=0.95)
        vs_chip.move_to([sf["cx"], header_row_y, 0])

        vs_txt = Text("VS", font="Montserrat", weight=BOLD, font_size=28, color=Design.GOLD).set_z_index(cfg.z_header + 11)
        _high_contrast_text(vs_txt)
        vs_txt.move_to(vs_chip)

        self.play(
            FadeIn(title, shift=UP * 0.12),
            Create(underline),
            FadeIn(scan_dot),
            run_time=0.55,
            rate_func=rf.ease_out_cubic,
        )
        self.play(
            FadeIn(p1_card, shift=RIGHT * 0.25),
            FadeIn(p2_card, shift=LEFT * 0.25),
            Create(connector),
            FadeIn(vs_chip),
            FadeIn(vs_txt),
            run_time=0.55,
            rate_func=rf.ease_out_cubic,
        )
        self.bring_to_front(p1_score, p2_score)

        # ==========================================
        # 5) TIMELINE
        # ==========================================
        timeline = RoundedRectangle(width=sf["w"], height=cfg.timeline_h, corner_radius=0.18).set_z_index(cfg.z_ui)
        timeline.set_fill(color=Design.GLASS_FILL, opacity=0.60)
        timeline.set_stroke(color=Design.PANEL_STROKE, width=2, opacity=0.90)
        timeline.move_to([sf["cx"], sf["bottom"] + cfg.timeline_h / 2 + cfg.timeline_bottom_lift, 0])

        tl_title = Text("ROUND TIMELINE", font="Montserrat", weight=BOLD, font_size=16, color=Design.TEXT_SUB).set_z_index(cfg.z_ui + 1)
        tl_title.move_to(timeline.get_left() + RIGHT * 1.35).align_to(timeline, UP).shift(DOWN * 0.28)

        meter_w = 2.55
        meter_h = 0.20
        meter_bg = RoundedRectangle(width=meter_w, height=meter_h, corner_radius=0.10).set_z_index(cfg.z_ui + 1)
        meter_bg.set_fill(color="#000000", opacity=0.55)
        meter_bg.set_stroke(color=WHITE, width=1.5, opacity=0.14)
        meter_bg.move_to(timeline.get_right() + LEFT * 1.60).align_to(timeline, UP).shift(DOWN * 0.34)

        meter_mid = Line(meter_bg.get_top(), meter_bg.get_bottom()).set_z_index(cfg.z_ui + 2)
        meter_mid.set_stroke(color=WHITE, width=2, opacity=0.10)
        meter_mid.move_to(meter_bg.get_center())

        p1_fill = RoundedRectangle(width=0.01, height=meter_h, corner_radius=0.10).set_z_index(cfg.z_ui + 2)
        p1_fill.set_fill(color=Design.CYAN, opacity=0.85).set_stroke(width=0)
        p1_fill.align_to(meter_bg, LEFT)

        p2_fill = RoundedRectangle(width=0.01, height=meter_h, corner_radius=0.10).set_z_index(cfg.z_ui + 2)
        p2_fill.set_fill(color=Design.PINK, opacity=0.85).set_stroke(width=0)
        p2_fill.align_to(meter_bg, RIGHT)

        self.add(timeline, tl_title, meter_bg, meter_mid, p1_fill, p2_fill)
        self.bring_to_front(p1_fill, p2_fill, meter_mid)

        n_rounds = max(1, len(attrs))
        chip_gap = 0.10
        chips_left = timeline.get_left()[0] + 0.45
        chips_right = meter_bg.get_left()[0] - 0.35
        chips_w = max(1.0, chips_right - chips_left)

        chip_w = min(1.05, (chips_w - chip_gap * (n_rounds - 1)) / n_rounds)
        chip_w = float(np.clip(chip_w, 0.55, 1.05))
        chip_h = 0.40

        round_chips: List[VGroup] = []
        for i, a in enumerate(attrs):
            chip = RoundedRectangle(width=chip_w, height=chip_h, corner_radius=0.14).set_z_index(cfg.z_ui + 1)
            chip.set_fill(color="#000000", opacity=0.35)
            chip.set_stroke(color=Design.PANEL_STROKE, width=1.6, opacity=0.90)

            short = a[:6] if len(a) > 6 else a
            t = Text(short, font="Montserrat", weight=BOLD, font_size=12, color=Design.TEXT_SUB).set_z_index(cfg.z_ui + 2)
            grp = VGroup(chip, t)

            x = chips_left + chip_w / 2 + i * (chip_w + chip_gap)
            y = timeline.get_center()[1] - 0.12
            grp.move_to([x, y, 0])
            round_chips.append(grp)

        self.add(*round_chips)

        # ==========================================
        # 6) MAIN BUTTERFLY REGION
        # ==========================================
        top_bound = (header_row_y - cfg.header_to_rows_pad) - cfg.rows_shift_down
        bottom_bound = (timeline.get_top()[1] + cfg.rows_to_timeline_pad) - cfg.rows_shift_down
        avail_h = max(2.2, top_bound - bottom_bound)

        row_gap = float(np.clip(avail_h / (n_attr + 0.35), cfg.row_gap_min, cfg.row_gap_max))

        center_x = sf["cx"]
        node_w = cfg.node_w

        left_bar_max = (center_x - sf["left"]) - (node_w / 2) - cfg.bar_tip_gutter
        right_bar_max = (sf["right"] - center_x) - (node_w / 2) - cfg.bar_tip_gutter
        bar_max_w = float(max(2.2, min(left_bar_max, right_bar_max) * 0.98))

        start_y = top_bound - row_gap * 0.20

        spine = Line([center_x, top_bound + 0.10, 0], [center_x, bottom_bound - 0.10, 0]).set_z_index(cfg.z_spine)
        spine.set_stroke(color=WHITE, width=2.2, opacity=0.10)
        self.add(spine)

        def make_node(label: str, stroke_col: str) -> VGroup:
            hexagon = RegularPolygon(n=6, radius=cfg.node_radius)
            hexagon.rotate(90 * DEGREES)
            hexagon.set_fill(color="#0A0A0A", opacity=0.92)
            hexagon.set_stroke(color=stroke_col, width=2.5, opacity=0.90)
            hexagon.set_z_index(cfg.z_node)

            formatted = _format_attr_label(label)
            t = Text(formatted, font="Montserrat", weight=BOLD, font_size=16, color=WHITE).set_z_index(cfg.z_node + 1)
            _high_contrast_text(t)
            t.move_to(hexagon)
            t.scale_to_fit_width(hexagon.width * 0.85)

            glow = hexagon.copy().set_z_index(cfg.z_node - 1)
            glow.set_fill(opacity=0)
            glow.set_stroke(color=stroke_col, width=12, opacity=0.10)

            return VGroup(glow, hexagon, t)

        def make_bar_container() -> VGroup:
            rr = RoundedRectangle(width=bar_max_w + 0.35, height=bar_h, corner_radius=0.14).set_z_index(cfg.z_track)
            rr.set_fill(color=Design.BAR_BG, opacity=0.88)
            rr.set_stroke(color=WHITE, width=1.5, opacity=0.10)
            ln = Line(rr.get_left(), rr.get_right()).set_z_index(cfg.z_track + 1)
            ln.set_stroke(color=WHITE, width=1, opacity=0.05)
            return VGroup(rr, ln)

        def create_spear(length: float, grad_colors, is_left: bool) -> VGroup:
            h = bar_h * 0.92
            length = max(0.10, float(length))
            tip = float(np.clip(cfg.bar_tip_len * (bar_h / 0.48), 0.22, 0.36))

            if is_left:
                pts = [
                    [0, h / 2, 0],
                    [-length, h / 2, 0],
                    [-length - tip, 0, 0],
                    [-length, -h / 2, 0],
                    [0, -h / 2, 0],
                ]
                core_s, core_e = pts[0], pts[2]
                sheen_dir = LEFT
            else:
                pts = [
                    [0, h / 2, 0],
                    [length, h / 2, 0],
                    [length + tip, 0, 0],
                    [length, -h / 2, 0],
                    [0, -h / 2, 0],
                ]
                core_s, core_e = pts[0], pts[2]
                sheen_dir = RIGHT

            body_fill = Polygon(*pts, stroke_width=0).set_z_index(cfg.z_bar)
            body_fill.set_fill(color=grad_colors, opacity=0.92)
            body_fill.set_sheen_direction(sheen_dir)

            outline = Polygon(*pts, stroke_width=2, color=WHITE).set_opacity(0.25).set_z_index(cfg.z_bar + 1)
            core = Line(core_s, core_e, color=WHITE, stroke_width=2).set_opacity(0.85).set_z_index(cfg.z_bar + 2)

            glow = Polygon(*pts, stroke_width=10, color=grad_colors[0]).set_fill(opacity=0).set_z_index(cfg.z_bar - 1)
            glow.set_opacity(0.10)

            return VGroup(glow, body_fill, outline, core)

        def tip_point(spear: VGroup) -> np.ndarray:
            return spear[1].get_vertices()[2]

        # ✅ CHANGED: end-box uses Text+tracker; returns tracker too
        def make_end_box(accent: str, spec: CompactSpec) -> Tuple[VGroup, Text, Text, ValueTracker]:
            w = _nice_endbox_width(spec, negative_possible)
            h = cfg.endbox_h

            box = RoundedRectangle(width=w, height=h, corner_radius=0.14).set_z_index(cfg.z_value)
            box.set_fill(color="#000000", opacity=0.62)
            box.set_stroke(color=accent, width=2.2, opacity=0.95)

            val_t = ValueTracker(0.0)

            num = Text("0", font="Montserrat", weight=BOLD, font_size=18, color=WHITE).set_z_index(cfg.z_value + 2)
            _high_contrast_text(num)

            suffix = Text(spec.suffix, font="Montserrat", weight=BOLD, font_size=14, color=Design.TEXT_SUB).set_z_index(cfg.z_value + 2)

            def _layout(m_num: Text):
                # Keep your previous layout style (same as DecimalNumber branch)
                if spec.suffix:
                    m_num.next_to(box.get_left(), RIGHT, buff=cfg.endbox_text_pad).align_to(box, DOWN).shift(UP * 0.10)
                    suffix.next_to(m_num, RIGHT, buff=0.06).align_to(m_num, DOWN).shift(UP * 0.02)
                else:
                    m_num.move_to(box.get_center())

            def _upd_num(m: Mobject):
                raw = float(val_t.get_value())
                s = _fmt_compact_value(raw, spec)
                new = Text(s, font="Montserrat", weight=BOLD, font_size=18, color=WHITE)
                _high_contrast_text(new)
                new.set_z_index(cfg.z_value + 2)
                m.become(new)
                _layout(m)

            num.add_updater(_upd_num)
            # keep suffix always on top + in correct place (layout called by num updater too)
            suffix.add_updater(lambda m: m.set_z_index(cfg.z_value + 2))

            _layout(num)

            grp = VGroup(box, num, suffix)
            return grp, num, suffix, val_t

        # ==========================================
        # 7) BATTLE LOOP
        # ==========================================
        p1_wins = 0
        p2_wins = 0

        active_glow = SurroundingRectangle(round_chips[0][0], corner_radius=0.16).set_z_index(cfg.z_ui + 3)
        active_glow.set_fill(opacity=0)
        active_glow.set_stroke(color=WHITE, width=3, opacity=0.25)
        self.add(active_glow)

        for i, (attr, v1, v2) in enumerate(zip(attrs, p1_vals, p2_vals)):
            y = start_y - i * row_gap

            stroke_col = Design.CYAN if i % 2 == 0 else Design.PINK
            node = make_node(attr, stroke_col).move_to([center_x, y, 0])

            left_container = make_bar_container().move_to(
                [center_x - (node_w / 2) - (bar_max_w / 2) - 0.30, y, 0]
            )
            right_container = make_bar_container().move_to(
                [center_x + (node_w / 2) + (bar_max_w / 2) + 0.30, y, 0]
            )

            stub_l = Line(node.get_left(), left_container.get_right()).set_z_index(cfg.z_track - 1)
            stub_r = Line(node.get_right(), right_container.get_left()).set_z_index(cfg.z_track - 1)
            stub_l.set_stroke(color=WHITE, width=2, opacity=0.10)
            stub_r.set_stroke(color=WHITE, width=2, opacity=0.10)

            spec_l = _compact_spec_for_target(v1)
            spec_r = _compact_spec_for_target(v2)

            end_l, end_l_num, end_l_suf, end_l_t = make_end_box(Design.CYAN, spec_l)
            end_r, end_r_num, end_r_suf, end_r_t = make_end_box(Design.PINK, spec_r)

            # AUTO placement (fixes off-screen + "unknown box" clipping)
            _place_end_box("L", end_l, left_container[0], sf, cfg.endbox_policy)
            _place_end_box("R", end_r, right_container[0], sf, cfg.endbox_policy)

            # Round start appear
            if i == 0:
                self.play(
                    FadeIn(left_container, shift=LEFT * 0.18),
                    FadeIn(right_container, shift=RIGHT * 0.18),
                    FadeIn(node, scale=0.98),
                    Create(stub_l),
                    Create(stub_r),
                    FadeIn(end_l, scale=0.98),
                    FadeIn(end_r, scale=0.98),
                    run_time=0.38,
                    rate_func=rf.ease_out_cubic,
                )
            else:
                self.play(
                    FadeIn(left_container, shift=LEFT * 0.12),
                    FadeIn(right_container, shift=RIGHT * 0.12),
                    FadeIn(node, scale=0.98),
                    Create(stub_l),
                    Create(stub_r),
                    FadeIn(end_l, scale=0.98),
                    FadeIn(end_r, scale=0.98),
                    active_glow.animate.become(
                        SurroundingRectangle(round_chips[i][0], corner_radius=0.16)
                        .set_fill(opacity=0)
                        .set_stroke(color=WHITE, width=3, opacity=0.25)
                        .set_z_index(cfg.z_ui + 3)
                    ),
                    run_time=0.34,
                    rate_func=rf.ease_out_cubic,
                )

            # Spear targets (abs length)
            w1 = (abs(float(v1)) / max_val) * bar_max_w
            w2 = (abs(float(v2)) / max_val) * bar_max_w

            l_start = create_spear(0.12, Design.P1_GRAD, True)
            r_start = create_spear(0.12, Design.P2_GRAD, False)
            l_end = create_spear(w1, Design.P1_GRAD, True)
            r_end = create_spear(w2, Design.P2_GRAD, False)

            l_start.move_to(left_container.get_right())
            r_start.move_to(right_container.get_left())
            l_end.move_to(l_start.get_center())
            r_end.move_to(r_start.get_center())

            self.add(l_start, r_start)

            # Cinematic count-up
            t1 = ValueTracker(0.0)
            t2 = ValueTracker(0.0)

            # ✅ FIX: drive end-box tracker (Text updater handles rendering/layout)
            def upd_end_l(_, dt):
                end_l_t.set_value(t1.get_value())
                self.bring_to_front(end_l_num, end_l_suf, end_l)

            def upd_end_r(_, dt):
                end_r_t.set_value(t2.get_value())
                self.bring_to_front(end_r_num, end_r_suf, end_r)

            end_l.add_updater(upd_end_l)
            end_r.add_updater(upd_end_r)

            self.play(
                Transform(l_start, l_end),
                Transform(r_start, r_end),
                t1.animate.set_value(float(v1)),
                t2.animate.set_value(float(v2)),
                run_time=0.88,
                rate_func=rf.ease_out_back,
            )

            end_l.remove_updater(upd_end_l)
            end_r.remove_updater(upd_end_r)

            # Winner compare
            winner = 0
            if v1 > v2:
                winner = 1
                p1_wins += 1
            elif v2 > v1:
                winner = 2
                p2_wins += 1

            # Header scores (✅ FIX: animate tracker, not Text)
            if winner == 1:
                self.play(p1_score_t.animate.set_value(p1_wins), run_time=0.18, rate_func=rf.ease_out_cubic)
                self.add_foreground_mobjects(p1_score)  # safe
            elif winner == 2:
                self.play(p2_score_t.animate.set_value(p2_wins), run_time=0.18, rate_func=rf.ease_out_cubic)
                self.add_foreground_mobjects(p2_score)  # safe

            self.bring_to_front(p1_score, p2_score)

            # Meter update (live)
            total_done = i + 1
            p1_ratio = p1_wins / max(1, total_done)
            p2_ratio = p2_wins / max(1, total_done)
            half = 2.55 / 2
            wL = max(0.01, half * p1_ratio)
            wR = max(0.01, half * p2_ratio)

            self.play(
                p1_fill.animate.stretch_to_fit_width(wL).align_to(meter_bg, LEFT),
                p2_fill.animate.stretch_to_fit_width(wR).align_to(meter_bg, RIGHT),
                run_time=0.30,
                rate_func=rf.ease_out_back,
            )
            self.bring_to_front(p1_fill, p2_fill, meter_mid)

            # Timeline chip mark + pulse
            chip_body = round_chips[i][0]
            if winner == 1:
                chip_body.set_fill(color=Design.CYAN, opacity=0.22)
                chip_body.set_stroke(color=Design.CYAN, width=2.2, opacity=0.95)
            elif winner == 2:
                chip_body.set_fill(color=Design.PINK, opacity=0.22)
                chip_body.set_stroke(color=Design.PINK, width=2.2, opacity=0.95)
            else:
                chip_body.set_fill(color=WHITE, opacity=0.06)
                chip_body.set_stroke(color=WHITE, width=1.8, opacity=0.30)

            # Winner highlight
            if winner == 1:
                end_l[0].set_fill(opacity=0.72)
                self.play(
                    Flash(tip_point(l_start), color=WHITE, line_length=0.55, num_lines=14),
                    Indicate(end_l[0], color=Design.CYAN, scale_factor=1.02),
                    Indicate(round_chips[i][0], color=Design.CYAN, scale_factor=1.02),
                    run_time=0.36,
                    rate_func=rf.ease_out_cubic,
                )
            elif winner == 2:
                end_r[0].set_fill(opacity=0.72)
                self.play(
                    Flash(tip_point(r_start), color=WHITE, line_length=0.55, num_lines=14),
                    Indicate(end_r[0], color=Design.PINK, scale_factor=1.02),
                    Indicate(round_chips[i][0], color=Design.PINK, scale_factor=1.02),
                    run_time=0.36,
                    rate_func=rf.ease_out_cubic,
                )
            else:
                self.play(
                    Indicate(node[1], color=WHITE, scale_factor=1.02),
                    Indicate(round_chips[i][0], color=WHITE, scale_factor=1.02),
                    run_time=0.28,
                    rate_func=rf.ease_out_cubic,
                )

            self.wait(0.08)

        # ==========================================
        # 8) WINNER ANNOUNCEMENT
        # ==========================================
        self.wait(0.35)

        if p1_wins > p2_wins:
            winner_name = p1_name
            accent = Design.CYAN
            label = "WINNER"
            border = Design.CYAN
        elif p2_wins > p1_wins:
            winner_name = p2_name
            accent = Design.PINK
            label = "WINNER"
            border = Design.PINK
        else:
            winner_name = "DRAW"
            accent = WHITE
            label = "RESULT"
            border = Design.GOLD

        dim = Rectangle(width=60, height=60).set_fill(color=BLACK, opacity=0.55).set_stroke(width=0).set_z_index(cfg.z_winner_dim)
        self.add(dim)

        banner_h = 1.90
        banner = RoundedRectangle(width=sf["w"], height=banner_h, corner_radius=0.24).set_z_index(cfg.z_winner)
        banner.set_fill(color="#000000", opacity=0.80)
        banner.set_stroke(color=border, width=3.0, opacity=0.92)

        banner_y = sf["bottom"] + sf["h"] * 0.33
        banner.move_to([sf["cx"], banner_y, 0])

        glow = banner.copy().set_z_index(cfg.z_winner - 1)
        glow.set_fill(opacity=0)
        glow.set_stroke(color=border, width=16, opacity=0.08)

        tag = Text(f"{label}:", font="Montserrat", weight=BOLD, font_size=22, color=WHITE).set_z_index(cfg.z_winner + 1)
        _high_contrast_text(tag)

        name_txt = Text(str(winner_name), font="Montserrat", weight=BOLD, font_size=44, color=accent).set_z_index(cfg.z_winner + 1)
        _high_contrast_text(name_txt)

        headline = VGroup(tag, name_txt).arrange(RIGHT, buff=0.18).move_to(banner.get_center() + UP * 0.20)

        score_line = Text(
            f"SCORE: {p1_wins}  —  {p2_wins}",
            font="Montserrat",
            weight=BOLD,
            font_size=18,
            color=Design.TEXT_SUB,
        ).set_z_index(cfg.z_winner + 1)
        score_line.next_to(headline, DOWN, buff=0.14)

        sweep = Line(banner.get_left(), banner.get_right()).set_z_index(cfg.z_winner + 2)
        sweep.set_stroke(color=WHITE, width=3, opacity=0.20)
        sweep.move_to(banner.get_top() + DOWN * 0.26)

        self.play(
            FadeIn(glow),
            GrowFromCenter(banner),
            FadeIn(headline, shift=UP * 0.18),
            FadeIn(score_line, shift=UP * 0.10),
            run_time=0.55,
            rate_func=rf.ease_out_cubic,
        )
        self.play(
            sweep.animate.shift(DOWN * 1.25).set_opacity(0),
            Flash(banner.get_top(), color=WHITE, line_length=0.55, num_lines=12),
            run_time=0.40,
            rate_func=rf.ease_out_cubic,
        )

        self.wait(2.2)
