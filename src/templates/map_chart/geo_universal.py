import os
import sys
import pandas as pd
import numpy as np

from manim import *
from manim import rate_functions as rf

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

from src.config import DATA_DIR, ASSETS_DIR, BACKGROUND_COLOR, Theme
from src.utils import IntroManager, get_safe_frame, make_floating_particles
from src.data.map_coords import COORDINATES

# ===========================
# MAP CALIBRATION
# ===========================
MAP_Y_SCALE = 1.40
MAP_Y_OFFSET = -0.20

# Group color fallback (for unknown groups)
GROUP_FALLBACK = [
    Theme.NEON_BLUE,
    Theme.NEON_PINK,
    Theme.NEON_GREEN,
    Theme.NEON_PURPLE,
    Theme.NEON_YELLOW,
    Theme.NEON_ORANGE,
]


def _parse_meta_first_line(path: str) -> dict:
    """
    Meta line format (optional):
    #TITLE=...,SUB=...,MODE=ALLIANCE|METRIC|COMPARE,METRIC=...,UNIT=...,MAX=10
    """
    meta = {
        "TITLE": "GLOBAL ALLIANCE MAP",
        "SUB": "Live alliances + metric overlay",
        "MODE": "ALLIANCE",
        "METRIC": "POWER INDEX",
        "UNIT": "pts",
        "MAX": "10",
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


def _safe_int(x, default=None):
    try:
        if x is None:
            return default
        if isinstance(x, str) and x.strip() == "":
            return default
        if pd.isna(x):
            return default
        return int(round(float(x)))
    except Exception:
        return default


class GeoUniversalMap(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR

        # ✅ SAME INTRO (utils.py) — DO NOT CHANGE
        try:
            IntroManager.play_intro(
                self,
                brand_title="BIGDATA LEAK",
                brand_sub="SYSTEM BREACH DETECTED",
                feed_text="FEED_MAP // GEO",
                footer_text="CONFIDENTIAL // VERIFIED",
            )
        except Exception:
            pass

        sf = get_safe_frame(margin=0.70)

        # subtle particles
        try:
            self.add(
                make_floating_particles(
                    n=18,
                    color=Theme.NEON_BLUE,
                    radius_range=(0.02, 0.05),
                    opacity_range=(0.06, 0.16),
                    drift=0.03,
                    margin=0.75,
                )
            )
        except Exception:
            pass

        # ===========================
        # LOAD DATA + META
        # ===========================
        csv_path = os.path.join(DATA_DIR, "map_data.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError("CRITICAL: map_data.csv nahi mila.")

        meta = _parse_meta_first_line(csv_path)
        mode = (meta.get("MODE") or "ALLIANCE").strip().upper()
        metric_name = (meta.get("METRIC") or "METRIC").strip()
        unit = (meta.get("UNIT") or "").strip()

        try:
            max_items = int(meta.get("MAX", "10"))
        except Exception:
            max_items = 10
        max_items = int(np.clip(max_items, 1, 10))

        df = pd.read_csv(csv_path, comment="#")
        df.columns = [c.strip().title() for c in df.columns]

        if "Country" not in df.columns:
            raise ValueError("CSV must have column: Country")

        if "Group" not in df.columns:
            df["Group"] = "Global"
        if "Value" not in df.columns:
            df["Value"] = np.nan

        df["Country"] = df["Country"].astype(str).str.strip()
        df["Group"] = df["Group"].astype(str).str.strip()

        # keep only known coords
        df = df[df["Country"].isin(COORDINATES.keys())].copy()

        # limit MAX
        df = df.head(max_items).reset_index(drop=True)

        unique_groups = list(df["Group"].unique())
        group_color_map = {}
        for i, g in enumerate(unique_groups):
            group_color_map[g] = GROUP_FALLBACK[i % len(GROUP_FALLBACK)]

        is_alliance_mode = len(unique_groups) > 1

        # ===========================
        # HEADER (safe)  (STATIC)
        # ===========================
        title = Text(
            meta.get("TITLE", "GLOBAL ALLIANCE MAP"),
            font="Montserrat",
            weight=BOLD,
            font_size=42,
            color=Theme.TEXT_MAIN,
        ).set_z_index(80)
        title.move_to([sf["cx"], sf["top"] - 0.95, 0])

        underline = Line(LEFT * 3.0, RIGHT * 3.0).set_z_index(80)
        underline.set_stroke(width=4, color=[Theme.NEON_PINK, Theme.NEON_BLUE], opacity=0.90)
        underline.next_to(title, DOWN, buff=0.18)

        sub = Text(
            meta.get("SUB", "Live alliances + metric overlay"),
            font="Montserrat",
            font_size=18,
            color=Theme.TEXT_SUB,
        ).set_z_index(80)
        sub.next_to(underline, DOWN, buff=0.18)

        self.add(title, underline, sub)

        # ===========================
        # LEGEND (compact rectangle HUD)  (DESIGN SAME)
        # NOTE: We do NOT self.add(legend) yet. We'll reveal via animation safely.
        # ===========================
        legend_w = 3.15
        legend_h = 1.55

        legend_bg = RoundedRectangle(width=legend_w, height=legend_h, corner_radius=0.18).set_z_index(85)
        legend_bg.set_fill(color="#05080B", opacity=0.70)
        legend_bg.set_stroke(color=Theme.NEON_BLUE, width=1.6, opacity=0.35)

        legend_title = Text(
            "DATAHUD",
            font="Montserrat",
            weight=BOLD,
            font_size=16,
            color=Theme.NEON_YELLOW,
        ).set_z_index(86)

        t_mode = Text(f"MODE : {mode}", font="Consolas", font_size=12, color=Theme.TEXT_MAIN).set_z_index(86)
        t_metric = Text(f"METRIC : {metric_name}", font="Consolas", font_size=12, color=Theme.TEXT_MAIN).set_z_index(86)

        t_unit = None
        if unit:
            t_unit = Text(f"UNIT : {unit}", font="Consolas", font_size=12, color=Theme.TEXT_MAIN).set_z_index(86)

        g_label = Text("GROUPS", font="Montserrat", weight=BOLD, font_size=12, color=Theme.TEXT_SUB).set_z_index(86)

        bullets = VGroup().set_z_index(86)
        for g in unique_groups[:3]:
            col = group_color_map.get(g, Theme.NEON_BLUE)
            dot = Dot(radius=0.035, color=col)
            txt = Text(str(g), font="Montserrat", font_size=12, color=Theme.TEXT_MAIN)
            row = VGroup(dot, txt).arrange(RIGHT, buff=0.10)
            bullets.add(row)
        bullets.arrange(DOWN, aligned_edge=LEFT, buff=0.08)

        # layout inside legend
        legend_left = legend_bg.get_left()[0]
        legend_top = legend_bg.get_top()[1]

        legend_title.move_to([legend_left + 0.70, legend_top - 0.22, 0])

        info_col = VGroup(t_mode, t_metric).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
        if t_unit is not None:
            info_col.add(t_unit)
            info_col.arrange(DOWN, aligned_edge=LEFT, buff=0.06)

        info_col.move_to([legend_left + 1.10, legend_top - 0.70, 0]).align_to(legend_bg, LEFT)

        g_block = VGroup(g_label, bullets).arrange(DOWN, aligned_edge=LEFT, buff=0.10)
        g_block.move_to([legend_bg.get_right()[0] - 1.10, legend_top - 0.72, 0]).align_to(legend_bg, RIGHT)

        legend = VGroup(legend_bg, legend_title, info_col, g_block).set_z_index(85)
        legend.move_to([sf["right"] - legend_w / 2 - 0.05, sub.get_bottom()[1] - legend_h / 2 - 0.15, 0])

        # ===========================
        # MAP (fit between lanes)  (DESIGN SAME)
        # NOTE: We do NOT self.add(world) yet. We'll reveal via animation safely.
        # ===========================
        svg_path = os.path.join(ASSETS_DIR, "svgs", "world.svg")
        if not os.path.exists(svg_path):
            raise FileNotFoundError("Missing assets/svgs/world.svg")

        world = SVGMobject(svg_path).set_z_index(10)
        world.set_fill(color="#1c2533", opacity=1.0)
        world.set_stroke(color="#3b4d66", width=1)

        map_target_w = sf["w"] * 0.62
        world.scale_to_fit_width(map_target_w)

        lane_top = legend.get_bottom()[1] - 0.35
        lane_bottom = sf["bottom"] + 0.85
        map_center_y = (lane_top + lane_bottom) / 2 + 0.25
        world.move_to([sf["cx"], map_center_y, 0])

        # compute bounds for latlon conversion
        map_left = world.get_left()[0]
        map_right = world.get_right()[0]
        map_bottom = world.get_bottom()[1]
        map_top = world.get_top()[1]
        map_w = map_right - map_left
        map_h = map_top - map_bottom
        map_center = world.get_center()

        def lat_lon_to_point(lat, lon):
            x_rel = (lon + 180) / 360.0
            x = map_left + x_rel * map_w
            y_rel = (lat + 90) / 180.0
            y = (y_rel - 0.5) * map_h * MAP_Y_SCALE + map_center[1] + MAP_Y_OFFSET
            return np.array([x, y, 0])

        # ===========================
        # SLOT LANES (DESIGN SAME)
        # ===========================
        slots_per_side = 5
        span = max(1.0, lane_top - lane_bottom)
        step = span / slots_per_side

        lane_pad = 0.10
        left_lane_x = sf["left"] + 0.15
        right_lane_x = sf["right"] - 0.15

        items = []
        for _, row in df.iterrows():
            c = row["Country"]
            g = row["Group"]
            v = row["Value"]
            lat, lon = COORDINATES.get(c, (0, 0))
            items.append((c, g, v, lat, lon))

        left_items = [it for it in items if it[4] < 0]
        right_items = [it for it in items if it[4] >= 0]

        while len(left_items) > slots_per_side and len(right_items) < slots_per_side:
            right_items.append(left_items.pop())
        while len(right_items) > slots_per_side and len(left_items) < slots_per_side:
            left_items.append(right_items.pop())

        left_items.sort(key=lambda x: x[3], reverse=True)
        right_items.sort(key=lambda x: x[3], reverse=True)

        left_slots_y = [lane_top - step * (i + 0.5) for i in range(slots_per_side)]
        right_slots_y = [lane_top - step * (i + 0.5) for i in range(slots_per_side)]

        placed = []
        for i, it in enumerate(left_items[:slots_per_side]):
            placed.append((it, "L", np.array([0, left_slots_y[i], 0])))
        for i, it in enumerate(right_items[:slots_per_side]):
            placed.append((it, "R", np.array([0, right_slots_y[i], 0])))

        # ===========================
        # CARD FACTORY (DESIGN SAME) + store meter final width for animation
        # ===========================
        vals_numeric = pd.to_numeric(df["Value"], errors="coerce")
        vmax = float(np.nanmax(vals_numeric.values)) if np.isfinite(np.nanmax(vals_numeric.values)) else 100.0
        vmax = max(1.0, vmax)

        def make_card(country, group, value, col, side):
            name = Text(str(country).upper(), font="Montserrat", weight=BOLD, font_size=18, color=WHITE)
            grp = Text(str(group), font="Montserrat", font_size=12, color=Theme.TEXT_SUB)

            iv = _safe_int(value, default=None)
            if iv is None:
                val_str = "–"
            else:
                val_str = f"{iv}{unit}" if unit else f"{iv}"

            val_txt = Text(val_str, font="Arial", weight=BOLD, font_size=16, color=col)
            chip = RoundedRectangle(corner_radius=0.16, width=val_txt.width + 0.38, height=0.44)
            chip.set_fill(color="#070A0C", opacity=0.90)
            chip.set_stroke(color=col, width=1.8, opacity=0.90)
            val_txt.move_to(chip)

            left_block = VGroup(name, grp).arrange(DOWN, buff=0.06, aligned_edge=LEFT)
            row = VGroup(left_block, VGroup(chip, val_txt)).arrange(RIGHT, buff=0.28)

            pad_x, pad_y = 0.22, 0.18
            bg = RoundedRectangle(
                width=row.width + pad_x * 2,
                height=max(0.74, row.height + pad_y * 2),
                corner_radius=0.20,
            )
            bg.set_fill(color="#05080B", opacity=0.62)
            bg.set_stroke(color=col, width=2.2, opacity=0.80)

            glow = bg.copy()
            glow.set_fill(opacity=0)
            glow.set_stroke(color=col, width=10, opacity=0.10)

            strip = RoundedRectangle(width=0.10, height=bg.height - 0.18, corner_radius=0.08)
            strip.set_fill(color=col, opacity=0.95).set_stroke(width=0)

            if side == "L":
                strip.move_to(bg.get_left() + RIGHT * 0.14)
            else:
                strip.move_to(bg.get_right() + LEFT * 0.14)

            row.move_to(bg)

            meter_w = bg.width - 0.40
            meter_h = 0.08
            meter_bg = RoundedRectangle(width=meter_w, height=meter_h, corner_radius=0.04)
            meter_bg.set_fill(color="#0B0F12", opacity=0.85).set_stroke(width=0)

            meter_fill = RoundedRectangle(width=meter_w, height=meter_h, corner_radius=0.04)
            meter_fill.set_fill(color=col, opacity=0.70).set_stroke(width=0)

            if iv is None:
                frac = 0.08
            else:
                frac = float(np.clip(iv / vmax, 0.08, 1.0))

            final_w = meter_w * frac

            # Start tiny (safe), animate later to final_w
            meter_fill.stretch_to_fit_width(0.01)
            meter_fill.align_to(meter_bg, LEFT)

            meter = VGroup(meter_bg, meter_fill)
            meter.next_to(bg, DOWN, buff=0.10)

            card = VGroup(glow, bg, strip, row, meter).set_z_index(90)
            max_w = 3.65
            if card.width > max_w:
                card.scale_to_fit_width(max_w)

            # store final meter width (after potential scaling)
            # (meter_fill already scaled with card if card scaled)
            # compute final in current scale:
            scale_factor = meter_bg.width / meter_w if meter_w != 0 else 1.0
            card.meter_final_width = max(0.01, float(final_w * scale_factor))

            return card

        # ===========================
        # DOTS + U-TURN LINES (DESIGN SAME) but animate safely (Create core only)
        # ===========================
        def make_dot(col, p):
            glow = Circle(radius=0.20).move_to(p)
            glow.set_stroke(color=col, width=10, opacity=0.10)

            ring = Circle(radius=0.14).move_to(p)
            ring.set_stroke(color=col, width=3, opacity=0.85)

            core = Dot(point=p, radius=0.05, color=WHITE).set_opacity(0.95)

            return VGroup(glow, ring, core).set_z_index(70)

        def uturn_route(p_pin, p_card_edge, side):
            dirx = 1 if side == "R" else -1

            base_out = 0.85
            extra = 0.25
            out_dx = base_out + extra

            p1 = p_pin
            p2 = np.array([p1[0] + dirx * out_dx, p1[1], 0])

            bump = 0.35
            p3 = np.array([p2[0], p2[1] + bump, 0])

            target_y = float(np.clip(p_card_edge[1], lane_bottom + 0.25, lane_top - 0.25))
            p4 = np.array([p2[0], target_y, 0])

            p5 = np.array([p_card_edge[0], target_y, 0])
            p6 = p_card_edge

            return [p1, p2, p3, p4, p5, p6]

        def make_line(points, col):
            core = VMobject()
            core.set_points_as_corners(points)
            core.set_fill(opacity=0)
            core.set_stroke(color=col, width=3, opacity=0.72)

            glow = core.copy()
            glow.set_stroke(color=col, width=10, opacity=0.12)

            return VGroup(glow, core).set_z_index(75)

        # ===========================
        # BUILD ALL (cards + dots + lines)
        # ===========================
        all_cards = []
        all_lines = []
        all_dots = []
        meta_items = []  # (country, group, col)

        group_dots_map = {g: [] for g in unique_groups}  # for STEP 3 (alliance traffic)

        for (country, group, value, lat, lon), side, slot_anchor in placed:
            col = group_color_map.get(group, Theme.NEON_BLUE)

            p_pin = lat_lon_to_point(lat, lon)
            dot = make_dot(col, p_pin)

            card = make_card(country, group, value, col, side)

            y = float(slot_anchor[1])
            if side == "L":
                x = left_lane_x + card.width / 2 + lane_pad
                card.move_to([x, y, 0])
                card_edge = card.get_right() + LEFT * 0.05
            else:
                x = right_lane_x - card.width / 2 - lane_pad
                card.move_to([x, y, 0])
                card_edge = card.get_left() + RIGHT * 0.05

            pts = uturn_route(p_pin, card_edge, side)
            ln = make_line(pts, col)

            all_dots.append(dot)
            all_cards.append(card)
            all_lines.append(ln)
            meta_items.append((country, group, col))

            # store core dot for alliance arcs
            try:
                group_dots_map[group].append(dot[2])
            except Exception:
                pass

        # =====================================================
        # ✅ STEP 1: BOOT (legend + map reveal)  — NO opacity hacks
        # =====================================================
        # map scan line (temporary)
        scan = Line(LEFT * 6, RIGHT * 6).set_z_index(60)
        scan.set_stroke(color=Theme.NEON_BLUE, width=4, opacity=0.85)
        scan.scale_to_fit_width(sf["w"] * 0.80)
        scan.move_to([sf["cx"], world.get_top()[1] + 0.25, 0])

        self.play(
            FadeIn(legend, shift=UP * 0.12, scale=0.98),
            run_time=0.55,
            rate_func=rf.ease_out_back,
        )
        self.play(
            FadeIn(world, scale=1.02),
            scan.animate.move_to([sf["cx"], world.get_bottom()[1] - 0.25, 0]).set_opacity(0),
            run_time=1.10,
            rate_func=rf.ease_out_cubic,
        )
        self.remove(scan)

        # legend tiny pulse
        self.play(
            legend_bg.animate.set_stroke(width=2.4, opacity=0.60),
            run_time=0.45,
            rate_func=rf.there_and_back,
        )

        # =====================================================
        # ✅ STEP 2: DATA REVEAL (dot ping → line core draw → glow → card lock)
        # =====================================================
        # A) Dots appear (lagged)
        self.play(
            LaggedStart(*[FadeIn(d, scale=0.70) for d in all_dots], lag_ratio=0.08),
            run_time=1.05,
        )

        # B) Each item sequence
        for dot, ln, card, (country, group, col) in zip(all_dots, all_lines, all_cards, meta_items):
            glow, core = ln[0], ln[1]

            # dot ping ring
            ping = Circle(radius=0.12).move_to(dot[2].get_center()).set_z_index(72)
            ping.set_stroke(color=col, width=6, opacity=0.35)

            self.add(ping)
            self.play(
                Flash(dot[2].get_center(), color=col, flash_radius=0.22, time_width=0.25),
                dot.animate.scale(1.12),
                ping.animate.scale(2.4).set_opacity(0),
                run_time=0.30,
                rate_func=rf.ease_out_cubic,
            )
            self.remove(ping)
            self.play(dot.animate.scale(1.00), run_time=0.12, rate_func=rf.ease_out_cubic)

            # line: CREATE ONLY CORE (prevents wedges/white spikes), then fade glow
            self.play(Create(core, rate_func=rf.linear), run_time=0.55)
            self.play(FadeIn(glow), run_time=0.12)

            # card lock (slide in)
            self.play(
                FadeIn(card, shift=UP * 0.12, scale=0.985),
                run_time=0.45,
                rate_func=rf.ease_out_back,
            )

            # meter fill animate to final width (only fill)
            try:
                meter_bg = card[4][0]
                meter_fill = card[4][1]
                final_w = getattr(card, "meter_final_width", meter_fill.width)
                self.play(
                    meter_fill.animate.stretch_to_fit_width(max(0.01, final_w)).align_to(meter_bg, LEFT),
                    run_time=0.32,
                    rate_func=rf.ease_out_cubic,
                )
            except Exception:
                pass

            # subtle card border pulse
            try:
                bg = card[1]
                self.play(
                    bg.animate.set_stroke(width=3.0, opacity=0.95),
                    run_time=0.22,
                    rate_func=rf.there_and_back,
                )
            except Exception:
                pass

            self.wait(0.05)

        # =====================================================
        # ✅ STEP 3: ALLIANCE TRAFFIC / ENDING (no timepass)
        # =====================================================
        if is_alliance_mode:
            connections = VGroup().set_z_index(65)
            travel_paths = []  # (base_arc, color)

            for gname, dots in group_dots_map.items():
                if len(dots) < 2:
                    continue
                color = group_color_map.get(gname, Theme.NEON_BLUE)

                # stable order left->right
                dots_sorted = sorted(dots, key=lambda d: d.get_center()[0])

                for k in range(len(dots_sorted) - 1):
                    p1 = dots_sorted[k].get_center()
                    p2 = dots_sorted[k + 1].get_center()

                    base_arc = ArcBetweenPoints(p1, p2, angle=PI / 6)
                    base_arc.set_stroke(color=color, width=2, opacity=0)  # invisible helper
                    dashed = DashedVMobject(base_arc.copy(), num_dashes=14)
                    dashed.set_stroke(color=color, width=2, opacity=0.55)

                    connections.add(dashed)
                    travel_paths.append((base_arc, color))

            if len(connections) > 0:
                self.play(Create(connections), run_time=1.2, rate_func=rf.ease_in_out_sine)

                # tracer packets
                tracers = []
                anims = []
                for path, c in travel_paths:
                    tracer = Dot(radius=0.06, color=WHITE).set_opacity(0.85).set_z_index(95)
                    tracer.move_to(path.get_start())
                    tracers.append(tracer)
                    anims.append(MoveAlongPath(tracer, path, run_time=2.2, rate_func=linear))

                if len(tracers) > 0:
                    self.add(*tracers)

                    # flash cards subtly during traffic
                    flashes = []
                    for card in all_cards:
                        try:
                            flashes.append(Flash(card[1].get_center(), color=Theme.TEXT_MAIN, flash_radius=0.55))
                        except Exception:
                            pass

                    self.play(
                        *anims,
                        *flashes,
                        run_time=2.2,
                    )
                    self.play(*[FadeOut(t) for t in tracers], run_time=0.4)

                # settle
                self.play(
                    connections.animate.set_opacity(0.35),
                    run_time=0.6,
                    rate_func=rf.ease_out_cubic,
                )

        else:
            # metric-style ending: highlight max
            vals = pd.to_numeric(df["Value"], errors="coerce")
            if len(vals.dropna()) > 0:
                winner_idx = int(np.nanargmax(vals.values))
                winner = all_cards[winner_idx]
                self.play(winner.animate.scale(1.04), run_time=0.25, rate_func=rf.ease_out_cubic)
                try:
                    self.play(
                        winner[1].animate.set_stroke(color=Theme.NEON_YELLOW, width=4.0, opacity=1.0),
                        run_time=0.35,
                        rate_func=rf.there_and_back,
                    )
                except Exception:
                    pass
                self.play(winner.animate.scale(1.00), run_time=0.15)

        # legend final micro pulse (premium)
        self.play(
            legend_bg.animate.set_stroke(width=2.2, opacity=0.55),
            run_time=0.55,
            rate_func=rf.there_and_back,
        )

        self.wait(2.0)
