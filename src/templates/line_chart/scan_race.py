# scan_race.py  (FINAL - Glass Dock TOP + FULL-WIDTH GRAPH BELOW + NO INTRO OVERLAP)

import sys
import os
import numpy as np
import pandas as pd
import random
from manim import *
from manim import rate_functions as rf

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

# --- IMPORTS (Robust) ---
try:
    from src.config import DATA_DIR, BACKGROUND_COLOR, Theme
    from src.utils import (
        Brand,
        get_safe_frame,
        clamp_x,
        clamp_y,
        make_floating_particles,
        get_branding_border_lines,
        get_cinematic_overlay,
        get_rotating_watermark,
    )
except Exception:
    DATA_DIR = "./Data"
    BACKGROUND_COLOR = "#050505"

    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_GREEN = "#00FF66"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"

    class Brand:
        CYAN = "#00F0FF"
        PINK = "#FF0055"
        GREEN = "#00FF66"
        WHITE = "#FFFFFF"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"

    config.frame_height = 16.0
    config.frame_width = 9.0

    def get_safe_frame(margin=0.70):
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

    def clamp_x(x, mob_width=0.0, margin=0.70):
        sf = get_safe_frame(margin)
        half = float(mob_width) / 2
        return float(np.clip(x, sf["left"] + half, sf["right"] - half))

    def clamp_y(y, mob_height=0.0, margin=0.70):
        sf = get_safe_frame(margin)
        half = float(mob_height) / 2
        return float(np.clip(y, sf["bottom"] + half, sf["top"] - half))

    def make_floating_particles(*args, **kwargs):
        return VGroup()

    def get_branding_border_lines(*args, **kwargs):
        return (VGroup(), VGroup(), VGroup(), VGroup())

    def get_cinematic_overlay(*args, **kwargs):
        return VGroup()

    def get_rotating_watermark(*args, **kwargs):
        return VGroup()


# ==========================
# DESIGN (matches bar_chart vibe)
# ==========================
class Design:
    BG = "#050505"
    TEXT_MAIN = "#FFFFFF"
    TEXT_SUB = "#B8B8B8"

    CYAN = Brand.CYAN
    PINK = Brand.PINK
    GREEN = Brand.GREEN
    WHITE = Brand.WHITE

    GOLD = "#FFD700"

    GLASS_FILL = "#0B0F12"
    GLASS_OP = 0.72
    PANEL_STROKE = "#1B2A33"
    PANEL_STROKE_OP = 0.9

    GRID_OP = 0.06
    AXIS_OP = 0.45

    CHIP_FILL = "#070A0C"
    CHIP_OP = 0.88


RACE_COLORS = [
    "#00F0FF",  # Cyan
    "#FF0055",  # Neon Red
    "#00FF66",  # Green
    "#BD00FF",  # Purple
    "#FFFF00",  # Yellow
    "#FF9900",  # Orange
]


class CinematicLineRace(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR if "BACKGROUND_COLOR" in globals() else Design.BG

        # ==========================================
        # 1) INTRO (NO OVERLAP, NO RE-APPEAR)
        # Branding assets from utils ONLY
        # ==========================================
        cover = Rectangle(width=60, height=60).set_fill(color=BLACK, opacity=1).set_stroke(width=0)
        cover.set_z_index(999)
        self.add(cover)

        breach = Text("> SYSTEM BREACH DETECTED", font="Montserrat", weight=BOLD, font_size=26, color=Design.PINK)
        breach.move_to([0, -0.15, 0]).set_z_index(1000)

        brand = Text("BIGDATA LEAK", font="Montserrat", weight=BOLD, font_size=48, color=Design.CYAN)
        brand.move_to([0, 0.10, 0]).set_z_index(1000)

        self.play(FadeIn(breach, shift=UP * 0.08), run_time=0.18)
        self.play(Flash(breach, color=WHITE, line_length=0.35, num_lines=10), run_time=0.18)
        self.play(FadeOut(breach, shift=UP * 0.08), run_time=0.16)

        self.play(Write(brand), run_time=0.35)
        self.play(Flash(brand, color=WHITE, line_length=0.55, num_lines=12), run_time=0.20)
        self.play(FadeOut(brand, shift=UP * 0.06), run_time=0.18)

        # add persistent branding layer (border + overlay + watermark)
        top, right, bottom, left = get_branding_border_lines(stroke_w=6, opacity=1.0)
        overlay = get_cinematic_overlay(self, feed_text="FEED_RACE // LIVE", footer_text="CONFIDENTIAL // VERIFIED")
        watermark = get_rotating_watermark()

        self.add(top, right, bottom, left, overlay, watermark)

        self.play(
            FadeOut(cover),
            Create(top), Create(right), Create(bottom), Create(left),
            run_time=0.75,
            rate_func=rate_functions.ease_out_cubic
        )

        # ==========================================
        # 2) SAFE FRAME + DATA
        # ==========================================
        sf = get_safe_frame(margin=0.70)

        csv_path = os.path.join(DATA_DIR, "race_data.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df.columns = df.columns.str.strip()
        else:
            years = np.arange(2000, 2025)
            data = {
                "Year": years,
                "USA": np.linspace(10, 26, 25),
                "China": np.linspace(2, 24, 25) * 1.15,
                "Japan": np.linspace(5, 6, 25),
                "Germany": np.linspace(2, 5, 25),
                "India": np.exp(np.linspace(0.5, 3.2, 25)),
                "UK": np.linspace(1.5, 3.8, 25),
                "France": np.linspace(1.4, 3.5, 25),
            }
            df = pd.DataFrame(data)

        years = df.iloc[:, 0].values.astype(float)
        labels = df.columns[1:]
        series = {c: df[c].values.astype(float) for c in labels}

        min_year, max_year = float(np.min(years)), float(np.max(years))
        raw_max = float(df.iloc[:, 1:].max().max())
        y_max = (int(raw_max // 5) + 1) * 5

        # y step smart
        y_step = 5
        if y_max >= 60:
            y_step = 10
        if y_max >= 150:
            y_step = 25

        TOPK = 5

        self.tracker = ValueTracker(min_year)
        self.current_ranks = {c: 99 for c in labels}

        def interp_value(c, t):
            idx = int(np.searchsorted(years, t) - 1)
            idx = max(0, min(idx, len(years) - 2))
            t1, t2 = years[idx], years[idx + 1]
            v1, v2 = series[c][idx], series[c][idx + 1]
            if t2 == t1:
                return float(v1)
            a = (t - t1) / (t2 - t1)
            return float(v1 + (v2 - v1) * a)

        # ==========================================
        # 3) ATMOSPHERE
        # ==========================================
        grid = NumberPlane(
            x_range=[-10, 10, 2],
            y_range=[-16, 16, 2],
            background_line_style={"stroke_color": Design.CYAN, "stroke_width": 1, "stroke_opacity": Design.GRID_OP},
            axis_config={"stroke_width": 0},
        )
        self.add(grid)

        try:
            particles = make_floating_particles(
                n=26,
                color=Design.CYAN,
                radius_range=(0.02, 0.05),
                opacity_range=(0.08, 0.22),
                drift=0.05,
                margin=0.75,
            )
            self.add(particles)
        except Exception:
            pass

        # ==========================================
        # 4) HEADER
        # ==========================================
        header_y = sf["top"] - 0.75

        title = Text("GDP GROWTH RACE", font="Montserrat", weight=BOLD, font_size=42, color=Design.TEXT_MAIN)
        title.move_to([sf["cx"], header_y, 0]).set_z_index(60)

        underline = Line(LEFT * 2.8, RIGHT * 2.8)
        underline.set_stroke(width=4, color=[Design.PINK, Design.CYAN])
        underline.next_to(title, DOWN, buff=0.18).set_z_index(60)

        scan_dot = Dot(color=WHITE, radius=0.07).move_to(underline.get_left()).set_z_index(61)

        def _scan(m, dt):
            tt = (np.sin(self.time * 2.0) + 1) / 2
            m.move_to(underline.get_left() + (underline.get_right() - underline.get_left()) * tt)

        scan_dot.add_updater(_scan)

        subtitle = Text("Live trajectory + ranking HUD", font="Montserrat", font_size=18, color=Design.TEXT_SUB)
        subtitle.next_to(underline, DOWN, buff=0.20).set_z_index(60)

        self.play(
            Write(title, run_time=0.55),
            GrowFromCenter(underline, run_time=0.55),
            FadeIn(scan_dot, run_time=0.2),
            FadeIn(subtitle, shift=UP * 0.1, run_time=0.45),
        )

        # ==========================================
        # 5) GLASS DOCK (TOP-LEFT under header)
        # ==========================================
        dock_w = float(np.clip(sf["w"] * 0.45, 3.2, 4.2))
        dock_h = float(np.clip(sf["h"] * 0.34, 3.8, 4.8))

        dock_top = underline.get_bottom()[1] - 0.30
        dock_center_y = dock_top - dock_h / 2

        panel = RoundedRectangle(width=dock_w, height=dock_h, corner_radius=0.18)
        panel.set_fill(color=Design.GLASS_FILL, opacity=Design.GLASS_OP)
        panel.set_stroke(color=Design.PANEL_STROKE, width=2, opacity=Design.PANEL_STROKE_OP)
        panel.move_to([sf["left"] + dock_w / 2, dock_center_y, 0]).set_z_index(40)

        panel_glow = panel.copy()
        panel_glow.set_stroke(color=Design.CYAN, width=10, opacity=0.06)
        panel_glow.set_fill(opacity=0)
        panel_glow.set_z_index(39)

        strip_h = 0.55
        strip = RoundedRectangle(width=dock_w - 0.25, height=strip_h, corner_radius=0.14)
        strip.set_fill(color="#000000", opacity=0.35).set_stroke(width=0)
        strip.move_to(panel.get_top() + DOWN * (strip_h / 2 + 0.12)).set_z_index(41)

        live_dot = Dot(radius=0.05, color=Design.GREEN).set_z_index(42)
        live_dot.move_to(strip.get_left() + RIGHT * 0.22)

        def _blink(m, dt):
            m.set_opacity(0.25 + 0.75 * (0.5 + 0.5 * np.sin(self.time * 6.5)))

        live_dot.add_updater(_blink)

        dock_title = Text("LIVE RANKING", font="Montserrat", weight=BOLD, font_size=16, color=Design.GOLD)
        dock_title.set_z_index(42)
        dock_title.next_to(live_dot, RIGHT, buff=0.10).align_to(strip, LEFT)

        self.play(FadeIn(panel_glow), FadeIn(panel), FadeIn(strip), FadeIn(live_dot), FadeIn(dock_title), run_time=0.45)

        # rail inside panel
        rail_x = panel.get_left()[0] + 0.20
        rail_top = strip.get_bottom()[1] - 0.20
        rail_bottom = panel.get_bottom()[1] + 0.35

        rail = Line([rail_x, rail_top, 0], [rail_x, rail_bottom, 0])
        rail.set_stroke(color=Design.CYAN, width=2.2, opacity=0.30).set_z_index(41)

        rail_scanner = Dot(color=WHITE, radius=0.04).move_to([rail_x, rail_top, 0]).set_z_index(42)

        def _rail_scan(m, dt):
            span = max(0.001, rail_top - rail_bottom)
            y = rail_top - (self.time * 0.75) % span
            m.move_to([rail_x, y, 0])

        rail_scanner.add_updater(_rail_scan)
        self.add(rail, rail_scanner)

        # slots for top-5
        slot_gap = (rail_top - rail_bottom) / TOPK
        slot_ys = [rail_top - slot_gap * (i + 0.5) for i in range(TOPK)]

        color_map = {c: RACE_COLORS[i % len(RACE_COLORS)] for i, c in enumerate(labels)}

        def make_slot_card(y):
            card_w = dock_w - 0.55
            card_h = 0.62
            x0 = rail_x + 0.18

            branch = Line([rail_x, y, 0], [x0 - 0.10, y, 0]).set_z_index(42)
            branch.set_stroke(color=Design.CYAN, width=2, opacity=0.25)

            bolt = Dot(radius=0.035, color=WHITE).move_to([x0 - 0.10, y, 0]).set_z_index(43)
            bolt.set_opacity(0.85)

            glow = RoundedRectangle(width=card_w, height=card_h, corner_radius=0.14)
            glow.set_fill(color=WHITE, opacity=0.0).set_stroke(width=0)
            glow.move_to([x0 + card_w / 2, y, 0]).set_z_index(43)

            body = RoundedRectangle(width=card_w, height=card_h, corner_radius=0.14)
            body.set_fill(color="#0A0D10", opacity=0.86)
            body.set_stroke(color=Design.CYAN, width=2, opacity=0.35)
            body.move_to(glow).set_z_index(44)

            accent = RoundedRectangle(width=0.10, height=card_h - 0.12, corner_radius=0.08)
            accent.set_fill(color=Design.CYAN, opacity=0.9).set_stroke(width=0)
            accent.move_to(body.get_left() + RIGHT * 0.12).set_z_index(45)

            badge = Circle(radius=0.18, color=WHITE).set_fill(color="#0B0F12", opacity=1)
            badge.set_stroke(color=Design.CYAN, width=2, opacity=0.7)
            badge.move_to(body.get_left() + RIGHT * 0.38).set_z_index(46)

            rank_txt = Text("1", font="Montserrat", weight=BOLD, font_size=16, color=WHITE).move_to(badge).set_z_index(47)

            name_txt = Text("COUNTRY", font="Montserrat", weight=BOLD, font_size=13, color=WHITE).set_z_index(47)
            name_txt.move_to(body.get_left() + RIGHT * 0.95)

            val_txt = Text("0.0T", font="Arial", weight=BOLD, font_size=13, color=Design.CYAN).set_z_index(47)
            val_txt.move_to(body.get_right() + LEFT * 0.40)

            return {
                "group": VGroup(branch, bolt, glow, body, accent, badge, rank_txt, name_txt, val_txt),
                "branch": branch,
                "bolt": bolt,
                "glow": glow,
                "body": body,
                "accent": accent,
                "badge": badge,
                "rank_txt": rank_txt,
                "name_txt": name_txt,
                "val_txt": val_txt,
                "y": y,
            }

        slot_cards = [make_slot_card(y) for y in slot_ys]
        self.add(*[c["group"] for c in slot_cards])

        # ==========================================
        # 6) FULL-WIDTH PLOT (UNDER DOCK)
        # ==========================================
        plot_top = panel.get_bottom()[1] - 0.35
        plot_bottom = sf["bottom"] + 0.70

        # Reserve a little left inset for Y labels so they don't go out of safe frame
        left_inset = 0.55
        right_inset = 0.10

        plot_left = sf["left"] + left_inset
        plot_right = sf["right"] - right_inset

        plot_w = plot_right - plot_left
        plot_h = plot_top - plot_bottom
        plot_center_x = (plot_left + plot_right) / 2
        plot_center_y = (plot_top + plot_bottom) / 2

        ax = Axes(
            x_range=[min_year, max_year + 2, 5],
            y_range=[0, y_max, y_step],
            x_length=plot_w,
            y_length=plot_h,
            axis_config={
                "include_numbers": False,
                "stroke_color": Design.CYAN,
                "stroke_width": 2,
                "stroke_opacity": Design.AXIS_OP,
                "include_tip": True,
                "tip_shape": ArrowTriangleFilledTip,
                "tip_style": {"fill_opacity": 1.0, "stroke_width": 0},
            },
        ).move_to([plot_center_x, plot_center_y, 0]).set_z_index(20)

        guides = VGroup()
        for v in np.arange(y_step, y_max + 0.001, y_step):
            left = ax.c2p(min_year, v)
            right = ax.c2p(max_year + 2, v)
            ln = DashedLine(left, right, dash_length=0.18, dashed_ratio=0.6)
            ln.set_stroke(color=Design.CYAN, width=1.2, opacity=0.10)
            guides.add(ln)

        x_labels = VGroup()
        for yr in range(int(min_year), int(max_year) + 1, 5):
            pos = ax.c2p(yr, 0)
            lbl = Text(str(yr), font="Arial", weight=BOLD, font_size=13, color=Design.TEXT_SUB)
            lbl.next_to(pos, DOWN, buff=0.20)
            x_labels.add(lbl)

        y_labels = VGroup()
        for v in np.arange(0, y_max + 0.001, y_step):
            pos = ax.c2p(min_year, v)
            txt = f"{int(v)}T" if v > 0 else "0"
            lbl = Text(txt, font="Arial", weight=BOLD, font_size=12, color=Design.TEXT_SUB)
            lbl.next_to(pos, LEFT, buff=0.12)
            y_labels.add(lbl)

        # Center year counter (clearly visible, NOT under dock)
        wm = Text(str(int(min_year)), font="Montserrat", weight=BOLD, font_size=130)
        wm.set_stroke(color=WHITE, width=2, opacity=0.10)
        wm.set_fill(color=WHITE, opacity=0.04)
        wm.move_to([sf["cx"], plot_center_y + 0.4, 0]).set_z_index(1)

        def wm_updater(m):
            m.become(
                Text(str(int(self.tracker.get_value())), font="Montserrat", weight=BOLD, font_size=130)
                .set_stroke(color=WHITE, width=2, opacity=0.10)
                .set_fill(color=WHITE, opacity=0.04)
                .move_to([sf["cx"], plot_center_y + 0.4, 0])
                .set_z_index(1)
            )

        wm.add_updater(lambda m: wm_updater(m))

        self.play(
            FadeIn(ax, run_time=0.35),
            Create(guides, run_time=0.45),
            FadeIn(x_labels, run_time=0.35),
            FadeIn(y_labels, run_time=0.35),
            FadeIn(wm, run_time=0.35),
        )

        # Plot bounds for chips (so they never go into dock zone)
        plot_bounds = {
            "left": plot_left,
            "right": plot_right,
            "top": plot_top,
            "bottom": plot_bottom,
        }

        def clamp_to_plot(x, w=0.0):
            half = float(w) / 2
            return float(np.clip(x, plot_bounds["left"] + half, plot_bounds["right"] - half))

        def clampy_to_plot(y, h=0.0):
            half = float(h) / 2
            return float(np.clip(y, plot_bounds["bottom"] + half, plot_bounds["top"] - half))

        # ==========================================
        # 7) LINE ENGINE + CHIPS + DOCK UPDATE
        # ==========================================
        pulse = {c: 0.0 for c in labels}
        slot_pulse = [0.0 for _ in range(TOPK)]
        prev_order = [None for _ in range(TOPK)]

        def line_for_country(c):
            col = color_map[c]

            def redraw():
                t = float(self.tracker.get_value())
                rank = int(self.current_ranks.get(c, 99))
                is_top = rank < TOPK

                valid = years <= t
                if np.sum(valid) == 0:
                    return VGroup()

                xs = years[valid]
                ys = series[c][valid]
                pts = [ax.c2p(x, y) for x, y in zip(xs, ys)]

                val = interp_value(c, t)
                pts.append(ax.c2p(t, val))

                if len(pts) < 2:
                    return VGroup()

                grp = VGroup()

                start_dot = Dot(radius=0.04, color=col).move_to(pts[0]).set_opacity(0.35)
                grp.add(start_dot)

                if is_top:
                    glow = VMobject().set_points_as_corners(pts)
                    glow.set_stroke(color=col, width=14, opacity=0.22)

                    core = VMobject().set_points_as_corners(pts)
                    core.set_stroke(color=WHITE, width=3.2, opacity=0.95)

                    end_dot = Dot(radius=0.07, color=col).move_to(pts[-1]).set_opacity(1)
                    ring = DashedVMobject(Circle(radius=0.12, color=WHITE, stroke_width=2), num_dashes=7)
                    ring.move_to(pts[-1])
                    ring.rotate(self.time * 2.8)

                    grp.add(glow, core, ring, end_dot)
                else:
                    faint = VMobject().set_points_as_corners(pts)
                    faint.set_stroke(color=col, width=2, opacity=0.08)
                    grp.add(faint)

                grp.set_z_index(10 if is_top else 5)
                return grp

            return redraw

        for c in labels:
            self.add(always_redraw(line_for_country(c)))

        def chips_group():
            t = float(self.tracker.get_value())
            scores = [(c, interp_value(c, t)) for c in labels]
            scores.sort(key=lambda x: x[1], reverse=True)
            top = scores[:TOPK]

            endpoints = []
            for (c, v) in top:
                p = ax.c2p(t, v)
                endpoints.append((c, v, p))

            chips = []
            for (c, v, p) in endpoints:
                col = color_map[c]
                txt = Text(f"{v:.1f}T", font="Arial", weight=BOLD, font_size=13, color=WHITE)
                pad_x, pad_y = 0.18, 0.10

                box = RoundedRectangle(
                    width=txt.width + pad_x * 2,
                    height=txt.height + pad_y * 2,
                    corner_radius=0.12,
                )
                box.set_fill(color=Design.CHIP_FILL, opacity=Design.CHIP_OP)
                box.set_stroke(color=col, width=2, opacity=0.85)

                cx = p[0] + 0.55 + box.width / 2
                cy = p[1]

                cx = clamp_to_plot(cx, box.width)
                cy = clampy_to_plot(cy, box.height)

                chips.append([c, v, p, col, box, txt, cx, cy])

            # simple vertical repel
            chips.sort(key=lambda k: k[7], reverse=True)
            min_gap = 0.38
            for i in range(1, len(chips)):
                prev = chips[i - 1]
                cur = chips[i]
                if prev[7] - cur[7] < min_gap:
                    cur[7] = prev[7] - min_gap

            for ch in chips:
                ch[7] = clampy_to_plot(ch[7], ch[4].height)

            g = VGroup()
            for (c, v, p, col, box, txt, cx, cy) in chips:
                box.move_to([cx, cy, 0])
                txt.move_to(box)

                start = p
                end = box.get_left() + RIGHT * 0.02
                conn = Line(start, end)
                conn.set_stroke(color=col, width=2, opacity=0.55)

                if pulse[c] > 0:
                    ring = Circle(radius=0.10, color=WHITE, stroke_width=3).move_to(p)
                    ring.set_opacity(min(0.9, pulse[c] * 2.2))
                    g.add(ring)

                g.add(conn, box, txt)

            g.set_z_index(25)
            return g

        self.add(always_redraw(chips_group))

        # Dock updater driver
        dock_driver = VMobject()
        dock_driver.set_opacity(0)

        def update_dock(m, dt):
            t = float(self.tracker.get_value())
            scores = [(c, interp_value(c, t)) for c in labels]
            scores.sort(key=lambda x: x[1], reverse=True)

            for r, (c, _) in enumerate(scores):
                self.current_ranks[c] = r

            top = scores[:TOPK]
            top_order = [c for c, _ in top]

            for i in range(TOPK):
                if prev_order[i] is None:
                    prev_order[i] = top_order[i]
                elif prev_order[i] != top_order[i]:
                    slot_pulse[i] = 0.35
                    pulse[top_order[i]] = max(pulse[top_order[i]], 0.28)
                    prev_order[i] = top_order[i]

            for i in range(TOPK):
                slot_pulse[i] = max(0.0, slot_pulse[i] - dt)
            for c in labels:
                pulse[c] = max(0.0, pulse[c] - dt)

            for i in range(TOPK):
                c, v = top[i]
                col = color_map[c]

                card = slot_cards[i]
                body = card["body"]
                accent = card["accent"]
                badge = card["badge"]

                card["rank_txt"].become(
                    Text(str(i + 1), font="Montserrat", weight=BOLD, font_size=16, color=WHITE).move_to(badge)
                )

                nm = Text(str(c).upper(), font="Montserrat", weight=BOLD, font_size=13, color=WHITE)
                nm.move_to(body.get_left() + RIGHT * 0.95)

                vt = Text(f"{v:.1f}T", font="Arial", weight=BOLD, font_size=13, color=Design.CYAN)
                vt.move_to(body.get_right() + LEFT * 0.40)

                max_w = (vt.get_left()[0] - nm.get_left()[0]) - 0.15
                if nm.width > max_w and max_w > 0.45:
                    nm.scale_to_fit_width(max_w)

                card["name_txt"].become(nm)
                card["val_txt"].become(vt)

                accent.set_fill(col, opacity=0.9)
                badge.set_stroke(col, width=2, opacity=0.85)

                if slot_pulse[i] > 0:
                    k = slot_pulse[i] / 0.35
                    body.set_stroke(color=WHITE, width=2 + 3 * k, opacity=0.9)
                    card["glow"].set_fill(color=WHITE, opacity=0.18 * k)
                    card["branch"].set_stroke(color=col, width=2.5, opacity=0.55)
                else:
                    body.set_stroke(color=Design.CYAN, width=2, opacity=0.28)
                    card["glow"].set_fill(opacity=0.0)
                    card["branch"].set_stroke(color=Design.CYAN, width=2, opacity=0.25)

                if i == 0:
                    body.set_stroke(color=col, width=2.5, opacity=0.65)

        dock_driver.add_updater(update_dock)
        self.add(dock_driver)

        # ==========================================
        # 8) LAUNCH
        # ==========================================
        self.play(
            self.tracker.animate.set_value(max_year),
            run_time=20,
            rate_func=linear,
        )
        self.wait(2)
