# butterfly_chart.py  (FINAL - GOD TIER v1.2: Stable Intro + Clean Header + Visible Attributes + Visible Timeline + Robust CSV)
# Manim Community v0.19.1

import sys
import os
import pandas as pd
import numpy as np
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
        clamp_x,
        clamp_y,
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

    def clamp_x(x, mob_width=0.0, margin=0.60):
        sf = get_safe_frame(margin)
        half = float(mob_width) / 2
        return float(np.clip(x, sf["left"] + half, sf["right"] - half))

    def clamp_y(y, mob_height=0.0, margin=0.60):
        sf = get_safe_frame(margin)
        half = float(mob_height) / 2
        return float(np.clip(y, sf["bottom"] + half, sf["top"] - half))

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
    GLASS_OP = 0.70
    PANEL_STROKE = "#1B2A33"
    PANEL_STROKE_OP = 0.90

    BAR_BG = "#070A0C"
    BAR_BG_OP = 0.88

    GRID_OP = 0.05

    P1_GRAD = [CYAN, "#0055FF"]
    P2_GRAD = [PINK, "#8800FF"]


# ==========================
# CSV helpers (supports meta first line: "#P1=...,P2=...")
# ==========================
def _parse_players_from_first_line(path: str):
    """
    Supports:
      #P1=ITEM A,P2=ITEM B
    Returns (p1_name, p2_name)
    """
    p1 = "ITEM A"
    p2 = "ITEM B"
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("#") and ("P1=" in first) and ("P2=" in first):
            # remove starting '#'
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


def _load_butterfly_df(csv_path: str):
    """
    Loads df with required cols: Attribute, P1_Value, P2_Value
    - Skips comment lines starting '#'
    - If headers mismatch, maps first 3 columns -> Attribute, P1_Value, P2_Value
    """
    df = pd.read_csv(csv_path, comment="#")
    df.columns = [str(c).strip() for c in df.columns]

    # direct match
    if {"Attribute", "P1_Value", "P2_Value"}.issubset(set(df.columns)):
        pass
    else:
        # map first 3 columns
        if len(df.columns) >= 3:
            attr_col, p1_col, p2_col = df.columns[0], df.columns[1], df.columns[2]
            df = df.rename(columns={attr_col: "Attribute", p1_col: "P1_Value", p2_col: "P2_Value"})
        else:
            raise ValueError(f"CSV columns mismatch. Found: {list(df.columns)}")

    # sanitize
    df = df.copy()
    df["Attribute"] = df["Attribute"].astype(str).str.strip().str.upper()
    df["P1_Value"] = pd.to_numeric(df["P1_Value"], errors="coerce").fillna(0.0)
    df["P2_Value"] = pd.to_numeric(df["P2_Value"], errors="coerce").fillna(0.0)

    # drop empties
    df = df[df["Attribute"].astype(str).str.len() > 0]
    df = df.reset_index(drop=True)
    return df


class ButterflyChart(Scene):
    def construct(self):
        self.camera.background_color = Design.BG
        sf = get_safe_frame(margin=0.60)

        # ==========================================
        # 1) INTRO (ONLY utils IntroManager; do not add anything else here)
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
        # 2) DATA (robust + player names from meta line)
        # ==========================================
        csv_candidates = [
            os.path.join(project_root, "Data", "butterfly_data.csv"),
            os.path.join(current_dir, "Data", "butterfly_data.csv"),
            os.path.join(current_dir, "butterfly_data.csv"),
            os.path.join(project_root, "butterfly_data.csv"),
            "butterfly_data.csv",
        ]
        csv_path = None
        for p in csv_candidates:
            if os.path.exists(p):
                csv_path = p
                break

        if csv_path:
            P1_NAME, P2_NAME = _parse_players_from_first_line(csv_path)
            df = _load_butterfly_df(csv_path)
        else:
            P1_NAME, P2_NAME = "ITEM A", "ITEM B"
            df = pd.DataFrame(
                [
                    {"Attribute": "SPEED", "P1_Value": 88, "P2_Value": 92},
                    {"Attribute": "HANDLING", "P1_Value": 95, "P2_Value": 80},
                    {"Attribute": "ACCEL", "P1_Value": 78, "P2_Value": 88},
                    {"Attribute": "LUXURY", "P1_Value": 90, "P2_Value": 65},
                    {"Attribute": "TECH", "P1_Value": 85, "P2_Value": 95},
                ]
            )

        attrs = df["Attribute"].tolist()
        p1_vals = df["P1_Value"].astype(float).tolist()
        p2_vals = df["P2_Value"].astype(float).tolist()
        max_val = float(max(100.0, np.max(np.array(p1_vals + p2_vals))))

        # ==========================================
        # 3) ATMOSPHERE (grid + rings + particles)
        # ==========================================
        grid = NumberPlane(
            x_range=[-10, 10, 2],
            y_range=[-16, 16, 2],
            background_line_style={"stroke_color": Design.CYAN, "stroke_width": 1, "stroke_opacity": Design.GRID_OP},
            axis_config={"stroke_width": 0},
        )
        grid.set_z_index(0)
        self.add(grid)

        ring1 = DashedVMobject(Circle(radius=3.2), num_dashes=36).set_z_index(1)
        ring1.set_stroke(color=Design.CYAN, width=2.2, opacity=0.14)

        ring2 = DashedVMobject(Circle(radius=4.8), num_dashes=54).set_z_index(1)
        ring2.set_stroke(color=Design.PINK, width=1.8, opacity=0.10)

        ring3 = Circle(radius=6.4).set_z_index(1)
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
                margin=0.60,
            )
            particles.set_z_index(2)
            self.add(particles)
        except Exception:
            pass

        # ==========================================
        # 4) HEADER (clean spacing + visible counters)
        # ==========================================
        header_top_y = sf["top"] - 0.85

        title = Text("WHO WILL DOMINATE?", font="Montserrat", weight=BOLD, font_size=26, color=Design.TEXT_SUB)
        title.move_to([sf["cx"], header_top_y, 0]).set_z_index(60)

        underline = Line(LEFT * 3.0, RIGHT * 3.0).set_z_index(60)
        underline.set_stroke(width=3, color=[Design.CYAN, Design.PINK], opacity=0.85)
        underline.next_to(title, DOWN, buff=0.22)

        scan_dot = Dot(radius=0.06, color=WHITE).set_z_index(61)
        scan_dot.move_to(underline.get_left())

        # IMPORTANT: dt param name must be exactly "dt"
        def _scan(m, dt):
            if not hasattr(m, "_phase"):
                m._phase = 0.0
            m._phase += dt
            t = (np.sin(m._phase * 2.0) + 1) / 2
            m.move_to(underline.get_left() + (underline.get_right() - underline.get_left()) * t)

        scan_dot.add_updater(_scan)

        def player_card(name: str, color: str, side: str):
            plate_w = 3.10
            plate_h = 1.10

            plate = RoundedRectangle(width=plate_w, height=plate_h, corner_radius=0.22).set_z_index(65)
            plate.set_fill(color=Design.GLASS_FILL, opacity=0.62)
            plate.set_stroke(color=Design.PANEL_STROKE, width=2, opacity=0.95)

            glow = plate.copy().set_z_index(64)
            glow.set_fill(opacity=0)
            glow.set_stroke(color=color, width=10, opacity=0.08)

            ring = Circle(radius=0.42).set_z_index(67)
            ring.set_fill(color="#0A0A0A", opacity=1.0)
            ring.set_stroke(color=color, width=3, opacity=0.95)

            # counter MUST be visible
            score = Integer(0, font_size=36, color=WHITE).set_z_index(68)
            score.move_to(ring)

            name_txt = Text(name, font="Montserrat", weight=BOLD, font_size=22, color=WHITE).set_z_index(68)
            sub = Text("SCORE", font="Montserrat", font_size=14, color=Design.TEXT_SUB).set_z_index(68)

            if side == "L":
                ring.move_to(plate.get_left() + RIGHT * 0.60)
                name_txt.next_to(ring, RIGHT, buff=0.22).align_to(plate, UP).shift(DOWN * 0.18)
                sub.next_to(name_txt, DOWN, buff=0.06).align_to(name_txt, LEFT)
            else:
                ring.move_to(plate.get_right() + LEFT * 0.60)
                name_txt.next_to(ring, LEFT, buff=0.22).align_to(plate, UP).shift(DOWN * 0.18)
                sub.next_to(name_txt, DOWN, buff=0.06).align_to(name_txt, RIGHT)

            group = VGroup(glow, plate, ring, score, name_txt, sub).set_z_index(65)
            return group, score

        p1_card, p1_score = player_card(P1_NAME, Design.CYAN, "L")
        p2_card, p2_score = player_card(P2_NAME, Design.PINK, "R")

        header_row_y = underline.get_bottom()[1] - 0.82
        p1_card.move_to([sf["left"] + p1_card.width / 2, header_row_y, 0])
        p2_card.move_to([sf["right"] - p2_card.width / 2, header_row_y, 0])

        conn_l = p1_card.get_right() + RIGHT * 0.18
        conn_r = p2_card.get_left() + LEFT * 0.18
        connector = Line(conn_l, conn_r).set_z_index(66)
        connector.set_stroke(color=WHITE, width=2, opacity=0.22)

        vs_chip = RoundedRectangle(width=1.05, height=0.48, corner_radius=0.18).set_z_index(70)
        vs_chip.set_fill(color="#000000", opacity=0.55)
        vs_chip.set_stroke(color=Design.GOLD, width=2, opacity=0.95)
        vs_chip.move_to([sf["cx"], header_row_y, 0])

        vs_txt = Text("VS", font="Montserrat", weight=BOLD, font_size=28, color=Design.GOLD).set_z_index(71)
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

        # ==========================================
        # 5) TIMELINE (MUST be visible)
        # ==========================================
        timeline_h = 1.10
        timeline = RoundedRectangle(width=sf["w"], height=timeline_h, corner_radius=0.18).set_z_index(55)
        timeline.set_fill(color=Design.GLASS_FILL, opacity=0.60)
        timeline.set_stroke(color=Design.PANEL_STROKE, width=2, opacity=0.90)
        timeline.move_to([sf["cx"], sf["bottom"] + timeline_h / 2 + 0.40, 0])

        tl_title = Text("ROUND TIMELINE", font="Montserrat", weight=BOLD, font_size=16, color=Design.TEXT_SUB).set_z_index(56)
        tl_title.move_to(timeline.get_left() + RIGHT * 1.35).align_to(timeline, UP).shift(DOWN * 0.25)

        meter_w = 2.55
        meter_h = 0.18
        meter_bg = RoundedRectangle(width=meter_w, height=meter_h, corner_radius=0.09).set_z_index(56)
        meter_bg.set_fill(color="#000000", opacity=0.55)
        meter_bg.set_stroke(color=WHITE, width=1.5, opacity=0.14)
        meter_bg.move_to(timeline.get_right() + LEFT * 1.60).align_to(timeline, UP).shift(DOWN * 0.30)

        meter_mid = Line(meter_bg.get_top(), meter_bg.get_bottom()).set_z_index(57)
        meter_mid.set_stroke(color=WHITE, width=2, opacity=0.10)
        meter_mid.move_to(meter_bg.get_center())

        p1_fill = RoundedRectangle(width=0.01, height=meter_h, corner_radius=0.09).set_z_index(57)
        p1_fill.set_fill(color=Design.CYAN, opacity=0.85).set_stroke(width=0)
        p1_fill.align_to(meter_bg, LEFT)

        p2_fill = RoundedRectangle(width=0.01, height=meter_h, corner_radius=0.09).set_z_index(57)
        p2_fill.set_fill(color=Design.PINK, opacity=0.85).set_stroke(width=0)
        p2_fill.align_to(meter_bg, RIGHT)

        self.add(timeline, tl_title, meter_bg, meter_mid, p1_fill, p2_fill)

        n_rounds = max(1, len(attrs))
        chip_gap = 0.10
        chips_left = timeline.get_left()[0] + 0.45
        chips_right = meter_bg.get_left()[0] - 0.35
        chips_w = max(1.0, chips_right - chips_left)

        chip_w = min(1.05, (chips_w - chip_gap * (n_rounds - 1)) / n_rounds)
        chip_w = float(np.clip(chip_w, 0.55, 1.05))
        chip_h = 0.38

        round_chips = []
        for i, a in enumerate(attrs):
            chip = RoundedRectangle(width=chip_w, height=chip_h, corner_radius=0.14).set_z_index(56)
            chip.set_fill(color="#000000", opacity=0.35)
            chip.set_stroke(color=Design.PANEL_STROKE, width=1.6, opacity=0.90)

            short = a[:6] if len(a) > 6 else a
            t = Text(short, font="Montserrat", weight=BOLD, font_size=12, color=Design.TEXT_SUB).set_z_index(57)
            grp = VGroup(chip, t)

            x = chips_left + chip_w / 2 + i * (chip_w + chip_gap)
            y = timeline.get_center()[1] - 0.10
            grp.move_to([x, y, 0])
            round_chips.append(grp)

        self.add(*round_chips)

        # ==========================================
        # 6) MAIN BUTTERFLY REGION (auto-fit, centered)
        # ==========================================
        top_bound = header_row_y - 1.00
        bottom_bound = timeline.get_top()[1] + 0.70
        avail_h = max(2.2, top_bound - bottom_bound)

        n = max(1, len(attrs))
        row_gap = min(1.35, avail_h / (n + 0.35))
        row_gap = float(np.clip(row_gap, 0.88, 1.30))
        bar_h = 0.48

        tip_gutter = 0.90
        center_x = sf["cx"]
        node_w = 0.82

        left_bar_max = (center_x - sf["left"]) - (node_w / 2) - tip_gutter
        right_bar_max = (sf["right"] - center_x) - (node_w / 2) - tip_gutter
        bar_max_w = float(np.clip(min(left_bar_max, right_bar_max), 2.05, 2.70))

        start_y = top_bound - row_gap * 0.20

        spine = Line([center_x, top_bound + 0.10, 0], [center_x, bottom_bound - 0.10, 0]).set_z_index(10)
        spine.set_stroke(color=WHITE, width=2.2, opacity=0.10)
        self.add(spine)

        def make_node(label: str, stroke_col: str):
            hexagon = RegularPolygon(n=6, radius=0.40)
            hexagon.rotate(90 * DEGREES)
            hexagon.set_fill(color="#0A0A0A", opacity=0.92)
            hexagon.set_stroke(color=stroke_col, width=2.5, opacity=0.90)
            hexagon.set_z_index(35)

            # ATTRIBUTE MUST be visible
            t = Text(label, font="Montserrat", weight=BOLD, font_size=12, color=WHITE).set_z_index(36)
            t.move_to(hexagon)

            glow = hexagon.copy().set_z_index(34)
            glow.set_fill(opacity=0)
            glow.set_stroke(color=stroke_col, width=12, opacity=0.10)

            return VGroup(glow, hexagon, t)

        def make_bar_container():
            rr = RoundedRectangle(width=bar_max_w + 0.35, height=bar_h, corner_radius=0.14).set_z_index(20)
            rr.set_fill(color=Design.BAR_BG, opacity=Design.BAR_BG_OP)
            rr.set_stroke(color=WHITE, width=1.5, opacity=0.10)

            ln = Line(rr.get_left(), rr.get_right()).set_z_index(21)
            ln.set_stroke(color=WHITE, width=1, opacity=0.05)
            return VGroup(rr, ln)

        def create_spear(length: float, grad_colors, is_left: bool):
            h = bar_h * 0.92
            length = max(0.10, float(length))

            if is_left:
                pts = [[0, h / 2, 0], [-length, h / 2, 0], [-length - 0.26, 0, 0], [-length, -h / 2, 0], [0, -h / 2, 0]]
                core_s, core_e = pts[0], pts[2]
                sheen_dir = LEFT
            else:
                pts = [[0, h / 2, 0], [length, h / 2, 0], [length + 0.26, 0, 0], [length, -h / 2, 0], [0, -h / 2, 0]]
                core_s, core_e = pts[0], pts[2]
                sheen_dir = RIGHT

            body_fill = Polygon(*pts, stroke_width=0).set_z_index(28)
            body_fill.set_fill(color=grad_colors, opacity=0.92)
            body_fill.set_sheen_direction(sheen_dir)

            outline = Polygon(*pts, stroke_width=2, color=WHITE).set_opacity(0.25).set_z_index(29)
            core = Line(core_s, core_e, color=WHITE, stroke_width=2).set_opacity(0.85).set_z_index(30)

            glow = Polygon(*pts, stroke_width=10, color=grad_colors[0]).set_fill(opacity=0).set_z_index(27)
            glow.set_opacity(0.10)

            return VGroup(glow, body_fill, outline, core)

        def tip_point(spear: VGroup):
            # spear[1] is body_fill
            return spear[1].get_vertices()[2]

        def value_chip(color: str):
            num = DecimalNumber(0, num_decimal_places=0, font_size=14, color=WHITE).set_z_index(80)
            box = RoundedRectangle(width=max(0.92, num.width + 0.42), height=0.40, corner_radius=0.14).set_z_index(79)
            box.set_fill(color="#000000", opacity=0.60)
            box.set_stroke(color=color, width=2, opacity=0.95)
            grp = VGroup(box, num).set_z_index(79)
            num.move_to(box)
            return grp, num, box

        # ==========================================
        # 7) BATTLE LOOP (stable + visible chips + visible winners)
        # ==========================================
        p1_wins = 0
        p2_wins = 0

        for i, (attr, v1, v2) in enumerate(zip(attrs, p1_vals, p2_vals)):
            y = start_y - i * row_gap

            stroke_col = Design.CYAN if i % 2 == 0 else Design.PINK
            node = make_node(attr, stroke_col).move_to([center_x, y, 0])

            left_container = make_bar_container().move_to([center_x - (node_w / 2) - (bar_max_w / 2) - 0.30, y, 0])
            right_container = make_bar_container().move_to([center_x + (node_w / 2) + (bar_max_w / 2) + 0.30, y, 0])

            stub_l = Line(node.get_left(), left_container.get_right()).set_z_index(19)
            stub_r = Line(node.get_right(), right_container.get_left()).set_z_index(19)
            stub_l.set_stroke(color=WHITE, width=2, opacity=0.10)
            stub_r.set_stroke(color=WHITE, width=2, opacity=0.10)

            self.play(
                FadeIn(left_container, shift=LEFT * 0.20),
                FadeIn(right_container, shift=RIGHT * 0.20),
                FadeIn(node, scale=0.98),
                Create(stub_l),
                Create(stub_r),
                run_time=0.30,
                rate_func=rf.ease_out_cubic,
            )

            w1 = (float(v1) / max_val) * bar_max_w
            w2 = (float(v2) / max_val) * bar_max_w

            l_start = create_spear(0.12, Design.P1_GRAD, True)
            r_start = create_spear(0.12, Design.P2_GRAD, False)
            l_end = create_spear(w1, Design.P1_GRAD, True)
            r_end = create_spear(w2, Design.P2_GRAD, False)

            # anchor spears at container inner edge (center-facing)
            l_start.move_to(left_container.get_right())
            r_start.move_to(right_container.get_left())
            l_end.move_to(l_start.get_center())
            r_end.move_to(r_start.get_center())

            chip_l, num_l, box_l = value_chip(Design.CYAN)
            chip_r, num_r, box_r = value_chip(Design.PINK)

            t1 = ValueTracker(0.0)
            t2 = ValueTracker(0.0)

            # Use dt-safe updater signature (dt name!)
            def upd_left(m, dt):
                num_l.set_value(t1.get_value())
                bw = max(0.92, num_l.width + 0.42)
                box_l.become(
                    RoundedRectangle(width=bw, height=0.40, corner_radius=0.14)
                    .set_fill(color="#000000", opacity=0.60)
                    .set_stroke(color=Design.CYAN, width=2, opacity=0.95)
                )
                box_l.set_z_index(79)
                num_l.set_z_index(80)

                tip = tip_point(l_start)
                pos = tip + LEFT * (box_l.width / 2 + 0.20)
                x = clamp_x(pos[0], box_l.width, 0.60)
                y2 = clamp_y(pos[1], box_l.height, 0.60)
                chip_l.move_to([x, y2, 0])
                num_l.move_to(chip_l)

            def upd_right(m, dt):
                num_r.set_value(t2.get_value())
                bw = max(0.92, num_r.width + 0.42)
                box_r.become(
                    RoundedRectangle(width=bw, height=0.40, corner_radius=0.14)
                    .set_fill(color="#000000", opacity=0.60)
                    .set_stroke(color=Design.PINK, width=2, opacity=0.95)
                )
                box_r.set_z_index(79)
                num_r.set_z_index(80)

                tip = tip_point(r_start)
                pos = tip + RIGHT * (box_r.width / 2 + 0.20)
                x = clamp_x(pos[0], box_r.width, 0.60)
                y2 = clamp_y(pos[1], box_r.height, 0.60)
                chip_r.move_to([x, y2, 0])
                num_r.move_to(chip_r)

            chip_l.add_updater(upd_left)
            chip_r.add_updater(upd_right)

            self.add(l_start, r_start, chip_l, chip_r)

            self.play(
                Transform(l_start, l_end),
                Transform(r_start, r_end),
                t1.animate.set_value(float(v1)),
                t2.animate.set_value(float(v2)),
                run_time=0.62,
                rate_func=rf.ease_out_cubic,
            )

            chip_l.remove_updater(upd_left)
            chip_r.remove_updater(upd_right)

            winner = 0
            if v1 > v2:
                winner = 1
                p1_wins += 1
            elif v2 > v1:
                winner = 2
                p2_wins += 1

            # update header scores
            if winner == 1:
                self.play(ChangeDecimalToValue(p1_score, p1_wins), run_time=0.18)
            elif winner == 2:
                self.play(ChangeDecimalToValue(p2_score, p2_wins), run_time=0.18)

            # update meter (rebuild fills)
            total_done = i + 1
            p1_ratio = p1_wins / max(1, total_done)
            p2_ratio = p2_wins / max(1, total_done)

            half = meter_w / 2
            wL = max(0.01, half * p1_ratio)
            wR = max(0.01, half * p2_ratio)

            p1_fill.become(RoundedRectangle(width=wL, height=meter_h, corner_radius=0.09).set_fill(Design.CYAN, 0.85).set_stroke(width=0))
            p1_fill.align_to(meter_bg, LEFT).set_z_index(57)

            p2_fill.become(RoundedRectangle(width=wR, height=meter_h, corner_radius=0.09).set_fill(Design.PINK, 0.85).set_stroke(width=0))
            p2_fill.align_to(meter_bg, RIGHT).set_z_index(57)

            # mark timeline chip
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

            # winner hit (strong + clean)
            if winner == 1:
                tp = tip_point(l_start)
                self.play(
                    Flash(tp, color=WHITE, line_length=0.55, num_lines=14),
                    l_start[0].animate.set_opacity(0.22),
                    run_time=0.34,
                    rate_func=rf.ease_out_cubic,
                )
            elif winner == 2:
                tp = tip_point(r_start)
                self.play(
                    Flash(tp, color=WHITE, line_length=0.55, num_lines=14),
                    r_start[0].animate.set_opacity(0.22),
                    run_time=0.34,
                    rate_func=rf.ease_out_cubic,
                )
            else:
                self.play(Indicate(node[1], color=WHITE, scale_factor=1.02), run_time=0.24)

            self.wait(0.08)

        # ==========================================
        # 8) WINNER ANNOUNCEMENT (premium + clean color)
        # ==========================================
        self.wait(0.35)

        if p1_wins > p2_wins:
            w_text = f"WINNER: {P1_NAME}"
            w_col = Design.CYAN
        elif p2_wins > p1_wins:
            w_text = f"WINNER: {P2_NAME}"
            w_col = Design.PINK
        else:
            w_text = "RESULT: DRAW"
            w_col = WHITE

        dim = Rectangle(width=60, height=60).set_fill(color=BLACK, opacity=0.55).set_stroke(width=0)
        dim.set_z_index(120)
        self.add(dim)

        banner_h = 2.00
        banner = RoundedRectangle(width=sf["w"], height=banner_h, corner_radius=0.22).set_z_index(140)
        banner.set_fill(color="#000000", opacity=0.78)
        banner.set_stroke(color=w_col, width=3.2, opacity=0.95)
        banner.move_to([sf["cx"], sf["cy"] - 0.10, 0])  # center (not too low)

        glow = banner.copy().set_z_index(139)
        glow.set_fill(opacity=0)
        glow.set_stroke(color=w_col, width=16, opacity=0.10)

        big = Text(w_text, font="Montserrat", weight=BOLD, font_size=44, color=w_col).set_z_index(141)
        big.move_to(banner.get_center() + UP * 0.25)

        small = Text(f"SCORE: {p1_wins}  —  {p2_wins}", font="Montserrat", weight=BOLD, font_size=18, color=Design.TEXT_SUB).set_z_index(141)
        small.next_to(big, DOWN, buff=0.18)

        sweep = Line(banner.get_left(), banner.get_right()).set_z_index(142)
        sweep.set_stroke(color=WHITE, width=3, opacity=0.28)
        sweep.move_to(banner.get_top() + DOWN * 0.28)

        self.play(
            FadeIn(glow),
            GrowFromCenter(banner),
            FadeIn(big, shift=UP * 0.25),
            FadeIn(small, shift=UP * 0.12),
            run_time=0.55,
            rate_func=rf.ease_out_cubic,
        )
        self.play(
            sweep.animate.shift(DOWN * 1.35).set_opacity(0),
            Flash(banner.get_top(), color=WHITE, line_length=0.55, num_lines=12),
            run_time=0.40,
            rate_func=rf.ease_out_cubic,
        )

        self.wait(2.2)
