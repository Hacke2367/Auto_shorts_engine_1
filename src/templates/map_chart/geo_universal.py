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

GROUP_FALLBACK = [
    Theme.NEON_BLUE,
    Theme.NEON_PINK,
    Theme.NEON_GREEN,
    Theme.NEON_PURPLE,
    Theme.NEON_YELLOW,
    Theme.NEON_ORANGE,
]


def _parse_meta_first_line(path: str) -> dict:
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


def _pick_compare_cols(df: pd.DataFrame):
    cols = {c.lower(): c for c in df.columns}
    pairs = [
        ("valuea", "valueb"),
        ("a", "b"),
        ("p1", "p2"),
        ("left", "right"),
        ("v1", "v2"),
    ]
    for a, b in pairs:
        if a in cols and b in cols:
            return cols[a], cols[b]
    return None, None


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

        # ===========================
        # BACKGROUND (UPDATED): grid + vignette
        # ===========================
        bg_fx = VGroup().set_z_index(1)

        grid = VGroup()
        x0, x1 = sf["left"], sf["right"]
        y0, y1 = sf["bottom"], sf["top"]
        grid_step = 0.85
        x = x0
        while x <= x1 + 1e-6:
            ln = Line([x, y0, 0], [x, y1, 0])
            ln.set_stroke(color=Theme.NEON_BLUE, width=1, opacity=0.035)
            grid.add(ln)
            x += grid_step
        y = y0
        while y <= y1 + 1e-6:
            ln = Line([x0, y, 0], [x1, y, 0])
            ln.set_stroke(color=Theme.NEON_BLUE, width=1, opacity=0.028)
            grid.add(ln)
            y += grid_step
        bg_fx.add(grid)

        edge_dark = VGroup(
            Rectangle(width=sf["w"] + 2.0, height=1.5)
            .set_fill(color=BLACK, opacity=0.18)
            .set_stroke(width=0)
            .move_to([sf["cx"], sf["top"] + 0.55, 0]),
            Rectangle(width=sf["w"] + 2.0, height=1.5)
            .set_fill(color=BLACK, opacity=0.18)
            .set_stroke(width=0)
            .move_to([sf["cx"], sf["bottom"] - 0.55, 0]),
            Rectangle(width=1.8, height=sf["h"] + 2.0)
            .set_fill(color=BLACK, opacity=0.18)
            .set_stroke(width=0)
            .move_to([sf["left"] - 0.55, sf["cy"], 0]),
            Rectangle(width=1.8, height=sf["h"] + 2.0)
            .set_fill(color=BLACK, opacity=0.18)
            .set_stroke(width=0)
            .move_to([sf["right"] + 0.55, sf["cy"], 0]),
        ).set_z_index(2)
        bg_fx.add(edge_dark)

        self.add(bg_fx)

        # subtle particles (unchanged)
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

        df = df[df["Country"].isin(COORDINATES.keys())].copy()
        df = df.head(max_items).reset_index(drop=True)

        unique_groups = list(df["Group"].unique())
        group_color_map = {g: GROUP_FALLBACK[i % len(GROUP_FALLBACK)] for i, g in enumerate(unique_groups)}
        is_alliance_mode = len(unique_groups) > 1

        compare_a, compare_b = _pick_compare_cols(df)

        # ===========================
        # HEADER (animated)  (UNCHANGED)
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

        self.play(Write(title), run_time=0.60, rate_func=rf.ease_out_cubic)
        self.play(Create(underline), run_time=0.45, rate_func=rf.ease_out_cubic)
        self.play(FadeIn(sub, shift=UP * 0.06), run_time=0.40, rate_func=rf.ease_out_cubic)
        self.play(underline.animate.set_opacity(1.0), run_time=0.30, rate_func=rf.there_and_back)

        # =====================================================
        # ✅ LIVE FEED TICKER (UPDATED FINAL) — replaces legend completely
        # =====================================================
        ticker_w = sf["w"] * 0.88
        ticker_h = 1.02
        pad_x = 0.42

        # Strong readable panel
        ticker_bg = RoundedRectangle(width=ticker_w, height=ticker_h, corner_radius=0.18).set_z_index(110)
        ticker_bg.set_fill(color="#05080B", opacity=0.72)
        ticker_bg.set_stroke(color=Theme.NEON_BLUE, width=2.4, opacity=0.82)

        # Top accent line
        ticker_accent = Line(LEFT, RIGHT).set_z_index(111)
        ticker_accent.set_stroke(color=[Theme.NEON_PINK, Theme.NEON_BLUE], width=3.2, opacity=0.80)
        ticker_accent.scale_to_fit_width(ticker_w * 0.94)
        ticker_accent.move_to(ticker_bg.get_top() + DOWN * 0.18)

        # --- Shorteners (avoid overflow)
        mode_short = str(mode)
        metric_short = str(metric_name)
        if len(mode_short) > 10:
            mode_short = mode_short[:10] + "…"
        if len(metric_short) > 16:
            metric_short = metric_short[:16] + "…"

        # LEFT: feed label
        feed_label = Text("FEED_MAP // GEO", font="Consolas", font_size=13, color=Theme.TEXT_MAIN).set_z_index(112)
        feed_label.set_opacity(0.95)

        # RIGHT: live status
        live_dot = Dot(radius=0.035, color=Theme.NEON_GREEN).set_z_index(112)
        live_txt = Text("LIVE", font="Consolas", font_size=12, color=Theme.TEXT_MAIN).set_z_index(112)
        right_block = VGroup(live_dot, live_txt).arrange(RIGHT, buff=0.10).set_z_index(112)

        # live dot pulse (safe)
        live_dot._pulse_t = 0.0

        def _pulse(mob, dt):
            mob._pulse_t += dt
            op = 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2 * np.pi * 1.2 * mob._pulse_t))
            mob.set_opacity(float(op))

        live_dot.add_updater(_pulse)

        # Center chips (minimal, readable)
        def _ticker_chip(label, value, col):
            t_label = Text(str(label), font="Consolas", font_size=10, color=Theme.TEXT_SUB).set_z_index(112)
            t_val = Text(str(value), font="Consolas", font_size=12, color=Theme.TEXT_MAIN, weight=BOLD).set_z_index(112)
            txt = VGroup(t_label, t_val).arrange(DOWN, buff=0.04, aligned_edge=LEFT)
            box = RoundedRectangle(corner_radius=0.14, width=txt.width + 0.36, height=0.46).set_z_index(111)
            box.set_fill(color="#070A0C", opacity=0.75)
            box.set_stroke(color=col, width=1.6, opacity=0.60)
            txt.move_to(box)
            return VGroup(box, txt).set_z_index(112)

        chips = VGroup(
            _ticker_chip("MODE", mode_short, Theme.NEON_GREEN),
            _ticker_chip("METRIC", metric_short, Theme.NEON_BLUE),
            _ticker_chip("MAX", str(max_items), Theme.NEON_YELLOW),
        ).arrange(RIGHT, buff=0.18).set_z_index(112)

        # Center message (Transform-safe: same object instance)
        if mode == "ALLIANCE":
            initial_msg = "Boot sequence: links scanning…"
        elif mode == "COMPARE":
            initial_msg = "Compare scan: deltas priming…"
        else:
            initial_msg = "Metric scan: indexing nodes…"

        feed_text = Text(initial_msg, font="Consolas", font_size=14, color=Theme.TEXT_MAIN).set_z_index(112)

        # Compose ticker
        ticker = VGroup(ticker_bg, ticker_accent, feed_label, chips, right_block, feed_text).set_z_index(110)
        ticker.move_to([sf["cx"], sub.get_bottom()[1] - ticker_h / 2 - 0.18, 0])

        # Anchor left/right
        feed_label.move_to(ticker_bg.get_left() + RIGHT * (pad_x + feed_label.width / 2)).shift(UP * 0.02)
        right_block.move_to(ticker_bg.get_right() + LEFT * (pad_x + right_block.width / 2)).shift(UP * 0.02)

        # Fit chips inside remaining space
        available = ticker_bg.width - (2 * pad_x) - feed_label.width - right_block.width - 0.60
        available = max(1.2, float(available))
        chips.scale_to_fit_width(available * 0.62)
        chips.move_to(ticker_bg.get_center() + UP * 0.06)

        # Feed text width fits remaining below chips
        feed_available = ticker_bg.width - 0.85
        feed_text.scale_to_fit_width(feed_available)
        feed_text.move_to(ticker_bg.get_center() + DOWN * 0.22)

        # One-time sweep highlight (not loop)
        ticker_sweep = Rectangle(width=ticker_w * 0.18, height=ticker_h * 0.70).set_z_index(109)
        ticker_sweep.set_fill(color=Theme.NEON_BLUE, opacity=0.10).set_stroke(width=0)
        ticker_sweep.move_to(ticker_bg.get_left() + RIGHT * (ticker_sweep.width / 2 + 0.05))
        ticker_sweep.set_opacity(0)

        # message setter (no NameError / no group break)
        def ticker_set(msg: str, animate: bool = True):
            new_mob = Text(str(msg), font="Consolas", font_size=14, color=Theme.TEXT_MAIN).set_z_index(112)
            new_mob.scale_to_fit_width(feed_available)
            new_mob.move_to(feed_text.get_center())
            if animate:
                self.play(Transform(feed_text, new_mob), run_time=0.32, rate_func=rf.ease_out_cubic)
            else:
                feed_text.become(new_mob)

        # ===========================
        # MAP (fit between lanes)  (UNCHANGED except: lane_top uses ticker)
        # ===========================
        svg_path = os.path.join(ASSETS_DIR, "svgs", "world.svg")
        if not os.path.exists(svg_path):
            raise FileNotFoundError("Missing assets/svgs/world.svg")

        world = SVGMobject(svg_path).set_z_index(10)
        world.set_fill(color="#1c2533", opacity=1.0)
        world.set_stroke(color="#3b4d66", width=1)

        map_target_w = sf["w"] * 0.62
        world.scale_to_fit_width(map_target_w)

        # ✅ CHANGED: ticker bottom drives lanes (instead of legend)
        lane_top = ticker.get_bottom()[1] - 0.35
        lane_bottom = sf["bottom"] + 0.85
        map_center_y = (lane_top + lane_bottom) / 2 + 0.25
        world.move_to([sf["cx"], map_center_y, 0])

        # ✅ map HUD panel (unchanged)
        map_panel = RoundedRectangle(
            width=world.width * 1.10,
            height=world.height * 1.35,
            corner_radius=0.25,
        ).set_z_index(6)
        map_panel.set_fill(color="#05080B", opacity=0.22)
        map_panel.set_stroke(color=Theme.NEON_BLUE, width=1.4, opacity=0.14)
        map_panel.move_to(world.get_center())

        bands = VGroup().set_z_index(7)
        for dy, op in [(0.55, 0.05), (0.05, 0.035), (-0.45, 0.05)]:
            r = Rectangle(width=map_panel.width * 0.92, height=0.22)
            r.set_fill(color=Theme.NEON_BLUE, opacity=op).set_stroke(width=0)
            r.move_to(map_panel.get_center() + UP * dy)
            bands.add(r)

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
        # SLOT LANES (ONLY change: slots_per_side dynamic)
        # ===========================
        n_items = int(len(df))
        slots_per_side = int(np.ceil(max(1, n_items) / 2.0))  # ✅ dynamic (1..5 for up to 10 items)

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
            items.append((c, g, v, lat, lon, row))

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
        # CARD FACTORY + meter final width store (UNCHANGED)
        # ===========================
        vals_numeric = pd.to_numeric(df["Value"], errors="coerce")
        vmax = float(np.nanmax(vals_numeric.values)) if np.isfinite(np.nanmax(vals_numeric.values)) else 100.0
        vmax = max(1.0, vmax)

        def _format_value(row_obj, value):
            iv = _safe_int(value, default=None)
            if mode == "COMPARE" and compare_a and compare_b:
                a = _safe_int(row_obj.get(compare_a), default=None)
                b = _safe_int(row_obj.get(compare_b), default=None)
                if a is None and b is None:
                    return "–"
                a = a if a is not None else 0
                b = b if b is not None else 0
                return f"{a}|{b}"
            if iv is None:
                return "–"
            return f"{iv}{unit}" if unit else f"{iv}"

        def make_card(country, group, value, col, side, row_obj):
            name = Text(str(country).upper(), font="Montserrat", weight=BOLD, font_size=18, color=WHITE)
            grp = Text(str(group), font="Montserrat", font_size=12, color=Theme.TEXT_SUB)

            val_str = _format_value(row_obj, value)

            val_txt = Text(val_str, font="Arial", weight=BOLD, font_size=16, color=col)
            chip = RoundedRectangle(corner_radius=0.16, width=val_txt.width + 0.38, height=0.44)
            chip.set_fill(color="#070A0C", opacity=0.90)
            chip.set_stroke(color=col, width=1.8, opacity=0.90)
            val_txt.move_to(chip)

            left_block = VGroup(name, grp).arrange(DOWN, buff=0.06, aligned_edge=LEFT)
            row = VGroup(left_block, VGroup(chip, val_txt)).arrange(RIGHT, buff=0.28)

            pad_xc, pad_yc = 0.22, 0.18
            bg = RoundedRectangle(
                width=row.width + pad_xc * 2,
                height=max(0.74, row.height + pad_yc * 2),
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

            iv = _safe_int(value, default=None)
            if iv is None:
                frac = 0.08
            else:
                frac = float(np.clip(iv / vmax, 0.08, 1.0))

            final_w = meter_w * frac
            meter_fill.stretch_to_fit_width(0.01)
            meter_fill.align_to(meter_bg, LEFT)

            meter = VGroup(meter_bg, meter_fill)
            meter.next_to(bg, DOWN, buff=0.10)

            card = VGroup(glow, bg, strip, row, meter).set_z_index(90)
            max_w = 3.65
            if card.width > max_w:
                card.scale_to_fit_width(max_w)

            scale_factor = meter_bg.width / meter_w if meter_w != 0 else 1.0
            card.meter_final_width = max(0.01, float(final_w * scale_factor))
            return card

        # ===========================
        # DOTS + U-TURN LINES (UNCHANGED)
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
            out_dx = 0.85 + 0.25
            p1 = p_pin
            p2 = np.array([p1[0] + dirx * out_dx, p1[1], 0])
            p3 = np.array([p2[0], p2[1] + 0.35, 0])
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
        # BUILD ALL (UNCHANGED)
        # ===========================
        all_cards, all_lines, all_dots, meta_items = [], [], [], []
        group_dots_map = {g: [] for g in unique_groups}

        for (country, group, value, lat, lon, row_obj), side, slot_anchor in placed:
            col = group_color_map.get(group, Theme.NEON_BLUE)
            p_pin = lat_lon_to_point(lat, lon)
            dot = make_dot(col, p_pin)
            card = make_card(country, group, value, col, side, row_obj)

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
            meta_items.append((str(country).strip().lower(), str(group).strip().lower(), col))

            try:
                group_dots_map[group].append(dot[2])
            except Exception:
                pass

        # =====================================================
        # ✅ STEP 1: BOOT (ticker + map reveal)
        # =====================================================
        self.play(FadeIn(ticker, shift=UP * 0.06, scale=0.99), run_time=0.55, rate_func=rf.ease_out_back)

        self.add(ticker_sweep)
        self.play(ticker_sweep.animate.set_opacity(1.0), run_time=0.08)
        self.play(
            ticker_sweep.animate.move_to(ticker_bg.get_right() + LEFT * (ticker_sweep.width / 2 + 0.05)),
            run_time=0.55,
            rate_func=rf.ease_in_out_sine,
        )
        self.play(ticker_sweep.animate.set_opacity(0), run_time=0.10)
        self.remove(ticker_sweep)

        self.play(live_dot.animate.scale(1.35), run_time=0.12, rate_func=rf.ease_out_cubic)
        self.play(live_dot.animate.scale(1.00), run_time=0.18, rate_func=rf.ease_in_out_sine)

        ticker_set("Boot complete: acquiring world map…", animate=True)

        scan = Line(LEFT * 6, RIGHT * 6).set_z_index(60)
        scan.set_stroke(color=Theme.NEON_BLUE, width=4, opacity=0.85)
        scan.scale_to_fit_width(sf["w"] * 0.80)
        scan.move_to([sf["cx"], world.get_top()[1] + 0.25, 0])

        self.add(map_panel, bands)
        self.add(scan)
        self.play(
            FadeIn(world, scale=1.02),
            scan.animate.move_to([sf["cx"], world.get_bottom()[1] - 0.25, 0]).set_opacity(0),
            run_time=1.05,
            rate_func=rf.ease_out_cubic,
        )
        self.remove(scan)

        self.play(
            ticker_bg.animate.set_stroke(width=3.0, opacity=0.95),
            run_time=0.35,
            rate_func=rf.there_and_back,
        )

        # =====================================================
        # ✅ STEP 2: DATA REVEAL (UNCHANGED)
        # =====================================================
        ticker_set("Signal sweep: deploying nodes…", animate=True)

        self.play(
            LaggedStart(*[FadeIn(d, scale=0.70) for d in all_dots], lag_ratio=0.08),
            run_time=1.00,
            rate_func=rf.ease_out_cubic,
        )

        for dot, ln, card, (cname, gname, col) in zip(all_dots, all_lines, all_cards, meta_items):
            glow, core = ln[0], ln[1]

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

            self.play(Create(core, rate_func=rf.linear), run_time=0.55)
            self.play(FadeIn(glow), run_time=0.12)

            self.play(
                FadeIn(card, shift=UP * 0.12, scale=0.985),
                run_time=0.45,
                rate_func=rf.ease_out_back,
            )

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
        # ✅ STEP 3: ALLIANCE TRAFFIC / ENDING + WINNER (UNCHANGED)
        # =====================================================
        def _winner_metric_index():
            vals = pd.to_numeric(df["Value"], errors="coerce")
            if len(vals.dropna()) > 0:
                return int(np.nanargmax(vals.values))
            return None

        def _winner_compare_index():
            if compare_a and compare_b:
                a = pd.to_numeric(df[compare_a], errors="coerce")
                b = pd.to_numeric(df[compare_b], errors="coerce")
                d = (a - b).abs()
                if len(d.dropna()) > 0:
                    return int(np.nanargmax(d.values))
            return _winner_metric_index()

        def _winner_alliance_group():
            vals = pd.to_numeric(df["Value"], errors="coerce")
            has_numbers = len(vals.dropna()) > 0
            if has_numbers:
                scores = {}
                for g in unique_groups:
                    gvals = pd.to_numeric(df[df["Group"] == g]["Value"], errors="coerce")
                    scores[g] = float(np.nansum(gvals.values))
                return max(scores, key=scores.get) if scores else None
            counts = {g: int((df["Group"] == g).sum()) for g in unique_groups}
            return max(counts, key=counts.get) if counts else None

        if is_alliance_mode:
            ticker_set("Alliance traffic: routing packets…", animate=True)

            connections = VGroup().set_z_index(65)
            travel_paths = []

            for gname, dots in group_dots_map.items():
                if len(dots) < 2:
                    continue
                color = group_color_map.get(gname, Theme.NEON_BLUE)
                dots_sorted = sorted(dots, key=lambda d: d.get_center()[0])
                for k in range(len(dots_sorted) - 1):
                    p1 = dots_sorted[k].get_center()
                    p2 = dots_sorted[k + 1].get_center()
                    base_arc = ArcBetweenPoints(p1, p2, angle=PI / 6)
                    base_arc.set_stroke(color=color, width=2, opacity=0)
                    dashed = DashedVMobject(base_arc.copy(), num_dashes=14)
                    dashed.set_stroke(color=color, width=2, opacity=0.55)
                    connections.add(dashed)
                    travel_paths.append((base_arc, color))

            if len(connections) > 0:
                self.play(Create(connections), run_time=1.15, rate_func=rf.ease_in_out_sine)

                tracers, anims = [], []
                for path, c in travel_paths:
                    tracer = Dot(radius=0.06, color=WHITE).set_opacity(0.85).set_z_index(95)
                    tracer.move_to(path.get_start())
                    tracers.append(tracer)
                    anims.append(MoveAlongPath(tracer, path, run_time=2.2, rate_func=linear))

                if tracers:
                    self.add(*tracers)
                    flashes = []
                    for card in all_cards:
                        try:
                            flashes.append(Flash(card[1].get_center(), color=Theme.TEXT_MAIN, flash_radius=0.52))
                        except Exception:
                            pass
                    self.play(*anims, *flashes, run_time=2.2)
                    self.play(*[FadeOut(t) for t in tracers], run_time=0.4)

                self.play(connections.animate.set_opacity(0.35), run_time=0.6, rate_func=rf.ease_out_cubic)

            win_g = _winner_alliance_group()
            winner_idx = None

            if win_g is not None:
                subdf = df[df["Group"] == win_g].copy()
                leader_country = None
                if len(subdf) > 0:
                    vsub = pd.to_numeric(subdf["Value"], errors="coerce")
                    if len(vsub.dropna()) > 0:
                        leader_country = str(subdf.iloc[int(np.nanargmax(vsub.values))]["Country"]).strip().lower()
                    else:
                        leader_country = str(subdf.iloc[0]["Country"]).strip().lower()

                if leader_country is not None:
                    for i, (cname, gname, _) in enumerate(meta_items):
                        if cname == leader_country:
                            winner_idx = i
                            break
                    if winner_idx is None:
                        for i, (cname, gname, _) in enumerate(meta_items):
                            if gname == str(win_g).strip().lower():
                                winner_idx = i
                                break

            if winner_idx is not None and 0 <= winner_idx < len(all_cards):
                ticker_set("Top signal detected: highlighting node…", animate=True)

                winner = all_cards[winner_idx]
                winner_dot = all_dots[winner_idx]
                self.play(winner.animate.scale(1.04), run_time=0.25, rate_func=rf.ease_out_cubic)
                try:
                    self.play(
                        winner[1].animate.set_stroke(color=Theme.NEON_YELLOW, width=4.0, opacity=1.0),
                        run_time=0.35,
                        rate_func=rf.there_and_back,
                    )
                except Exception:
                    pass
                try:
                    self.play(
                        Flash(winner_dot[2].get_center(), color=Theme.NEON_YELLOW, flash_radius=0.28, time_width=0.35),
                        run_time=0.35,
                    )
                except Exception:
                    pass
                self.play(winner.animate.scale(1.00), run_time=0.15)

        else:
            ticker_set("Final scan: computing top node…", animate=True)

            winner_idx = _winner_compare_index() if mode == "COMPARE" else _winner_metric_index()
            if winner_idx is not None and 0 <= winner_idx < len(all_cards):
                winner = all_cards[winner_idx]
                winner_dot = all_dots[winner_idx]
                self.play(winner.animate.scale(1.04), run_time=0.25, rate_func=rf.ease_out_cubic)
                try:
                    self.play(
                        winner[1].animate.set_stroke(color=Theme.NEON_YELLOW, width=4.0, opacity=1.0),
                        run_time=0.35,
                        rate_func=rf.there_and_back,
                    )
                except Exception:
                    pass
                try:
                    self.play(
                        Flash(winner_dot[2].get_center(), color=Theme.NEON_YELLOW, flash_radius=0.28, time_width=0.35),
                        run_time=0.35,
                    )
                except Exception:
                    pass
                self.play(winner.animate.scale(1.00), run_time=0.15)

        self.play(
            ticker_bg.animate.set_stroke(width=2.6, opacity=0.90),
            run_time=0.45,
            rate_func=rf.there_and_back,
        )

        self.wait(2.0)

        try:
            live_dot.remove_updater(_pulse)
        except Exception:
            pass
