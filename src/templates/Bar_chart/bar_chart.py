# bar_chart/bar_chart.py  (FINAL - V2 BASE + VALUE GUTTER FIX + NO FEATURE LOSS)

import sys
import os
import numpy as np
import random
import pandas as pd
from manim import *
from manim import rate_functions as rf

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

# --- IMPORTS (Robust) ---
try:
    from src.config import Theme, BACKGROUND_COLOR
    from src.utils import (
        IntroManager,
        get_safe_frame,
        clamp_x,
        clamp_y,
        make_floating_particles,
        Brand,
    )
except Exception:
    BACKGROUND_COLOR = "#050505"

    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_GREEN = "#00FF66"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"
        AXIS_COLOR = "#00F0FF"
        C_CONTAINER_FILL = "#050505"
        C_CONTAINER_STROKE = "#004488"
        C_BAR_GRADIENT = ["#0033CC", "#0088FF", "#00FFFF"]
        C_DOT_CORE = "#FFFFFF"
        C_DOT_GLOW = "#00FFFF"
        C_LINE_CORE = "#FFFFFF"
        C_LINE_GLOW = "#00FFFF"

    # minimal safe-frame fallbacks
    config.frame_height = 16.0
    config.frame_width = 9.0

    class Brand:
        CYAN = "#00F0FF"
        PINK = "#FF0055"
        GREEN = "#00FF66"
        WHITE = "#FFFFFF"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"

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


class BarChartTemplate(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR

        # ============================================================
        # 1) INTRO (adds border + overlay + timer + watermark via utils)
        # ============================================================
        try:
            IntroManager.play_intro(
                self,
                brand_title="BIGDATA LEAK",
                brand_sub="> FEED VERIFIED",
                feed_text="FEED_BAR // MARKET",
                footer_text="CONFIDENTIAL // LEAKED_SOURCE",
            )
        except Exception as e:
            print(f"Intro Error: {e}")

        # ============================================================
        # 2) SAFE FRAME (we will layout everything inside it)
        # ============================================================
        sf = get_safe_frame(margin=0.70)

        # ============================================================
        # 3) ATMOSPHERE
        # ============================================================
        grid = NumberPlane(
            x_range=(-10, 10, 1),
            y_range=(-20, 20, 1),
            background_line_style={
                "stroke_color": Theme.NEON_BLUE,
                "stroke_width": 1,
                "stroke_opacity": 0.06,
            },
            axis_config={"stroke_width": 0},
        )
        self.add(grid)

        # Particles (subtle)
        try:
            particles = make_floating_particles(
                n=26,
                color=Theme.NEON_BLUE,
                radius_range=(0.02, 0.05),
                opacity_range=(0.10, 0.25),
                drift=0.05,
                margin=0.75,
            )
            self.add(particles)
        except:
            pass

        # ============================================================
        # 4) HEADER (safe)
        # ============================================================
        title = Text(
            "MARKET LEADERS",
            font="Montserrat",
            weight=BOLD,
            font_size=52,
            color=Theme.TEXT_MAIN,
        )
        title.move_to([sf["cx"], sf["top"] - 1.05, 0])

        underline = Line(LEFT * 2.8, RIGHT * 2.8)
        underline.set_stroke(width=4, color=[Theme.NEON_PINK, Theme.NEON_BLUE])
        underline.next_to(title, DOWN, buff=0.18)

        # header scanner (premium)
        scanner_dot = Dot(color=WHITE, radius=0.07)
        scanner_dot.move_to(underline.get_left())
        scanner_dot.set_z_index(50)

        def _scan(m, dt):
            t = (np.sin(self.time * 2.0) + 1) / 2
            m.move_to(underline.get_left() + (underline.get_right() - underline.get_left()) * t)

        scanner_dot.add_updater(_scan)

        subtitle = Text(
            "Tech leaders comparison",
            font="Montserrat",
            font_size=22,
            color=Theme.TEXT_SUB,
        )
        subtitle.next_to(underline, DOWN, buff=0.25)

        self.play(
            Write(title, run_time=0.7),
            GrowFromCenter(underline, run_time=0.7),
            FadeIn(scanner_dot, run_time=0.3),
            FadeIn(subtitle, shift=UP * 0.2, run_time=0.8),
        )

        # ============================================================
        # 5) DATA (CSV ready later; for now same demo set)
        # ============================================================
        names = ["Nvidia", "Microsoft", "Apple", "Google", "Amazon"]
        values = [95, 88, 82, 76, 70]
        max_val = 100

        # sort safety (so it works even if user provides random order)
        rows = sorted(list(zip(names, values)), key=lambda x: x[1], reverse=True)
        names = [r[0] for r in rows]
        values = [r[1] for r in rows]

        num_items = len(names)

        # ============================================================
        # 6) LAYOUT (SAFE)
        # ============================================================
        # Vertical layout bounds for bars
        top_y = sf["top"] - 3.2
        bottom_y = sf["bottom"] + 2.1
        available_h = top_y - bottom_y
        GAP_Y = min(1.75, available_h / (num_items + 0.2))
        START_Y = top_y

        # Horizontal layout
        RAIL_X = sf["left"] + 0.55
        RANK_X = RAIL_X + 0.60
        LABEL_X = RANK_X + 1.10
        BAR_START_X = LABEL_X + 1.10

        # -----------------------------
        # ✅ FIX: Reserve a VALUE GUTTER
        # -----------------------------
        # This ensures right-side numbers NEVER overlap bars.
        VALUE_GUTTER_W = 0.95  # reserved column width
        BAR_RIGHT_LIMIT = sf["right"] - VALUE_GUTTER_W
        BAR_MAX_WIDTH = BAR_RIGHT_LIMIT - BAR_START_X

        # value anchor (fixed column, safe)
        VALUE_ANCHOR_X = sf["right"] - 0.30

        BAR_HEIGHT = 0.62

        # ---- Left RANK RAIL ----
        rail_top = START_Y + 0.55
        rail_bottom = START_Y - (num_items - 1) * GAP_Y - 0.55

        rail = Line([RAIL_X, rail_top, 0], [RAIL_X, rail_bottom, 0])
        rail.set_stroke(color=Theme.NEON_BLUE, width=3, opacity=0.35)
        rail.set_z_index(20)

        rail_glow = rail.copy()
        rail_glow.set_stroke(color=WHITE, width=10, opacity=0.06)
        rail_glow.set_z_index(19)

        rail_label = Text("RANK", font="Montserrat", weight=BOLD, font_size=16, color=Theme.NEON_PINK)
        rail_label.rotate(90 * DEGREES)
        rail_label.move_to([RAIL_X - 0.35, (rail_top + rail_bottom) / 2, 0])
        rail_label.set_opacity(0.85)
        rail_label.set_z_index(25)

        # rail scanner dot
        rail_scanner = Dot(color=WHITE, radius=0.06).move_to([RAIL_X, rail_top, 0])
        rail_scanner.set_z_index(30)

        def _rail_scan(m, dt):
            speed = 0.9
            y = rail_top - (self.time * speed) % max(0.001, (rail_top - rail_bottom))
            m.move_to([RAIL_X, y, 0])

        rail_scanner.add_updater(_rail_scan)

        self.play(FadeIn(rail_glow), Create(rail), FadeIn(rail_label), FadeIn(rail_scanner), run_time=0.6)

        # ---- Milestones (inside safe) ----
        milestones = [0, 25, 50, 75, 100]
        guide_group = VGroup()
        for m in milestones:
            x_pos = BAR_START_X + (m / 100) * BAR_MAX_WIDTH
            v_line = DashedLine(
                start=[x_pos, START_Y + 0.75, 0],
                end=[x_pos, rail_bottom - 0.25, 0],
                dash_length=0.18,
                dashed_ratio=0.6,
            )
            v_line.set_stroke(Theme.NEON_BLUE, width=2, opacity=0.12)

            label = Text(str(m), font="Arial", font_size=14, color=Theme.TEXT_SUB)
            label.move_to([x_pos, rail_bottom - 0.55, 0])
            guide_group.add(v_line, label)

        self.play(Create(guide_group, run_time=0.8, lag_ratio=0.08))

        # ============================================================
        # 7) BAR ENGINE
        # ============================================================
        winner_index = int(np.argmax(values))
        bar_groups = []

        for i, (name, value) in enumerate(zip(names, values)):
            y_pos = START_Y - (i * GAP_Y)
            target_width = (value / max_val) * BAR_MAX_WIDTH

            # Branch from rail to rank circle
            branch = Line([RAIL_X, y_pos, 0], [RANK_X - 0.18, y_pos, 0])
            branch.set_stroke(color=Theme.NEON_BLUE, width=2, opacity=0.25)
            bolt = Dot(color=WHITE, radius=0.035).move_to(branch.get_start())
            bolt.set_opacity(0.6)

            # Rank badge
            rank_bg = Circle(radius=0.25, color="#0B0B0B", fill_opacity=1).set_stroke(
                Theme.NEON_BLUE, width=2, opacity=0.7
            )
            rank_bg.move_to([RANK_X, y_pos, 0])
            rank_num = Text(f"{i + 1}", font="Montserrat", weight=BOLD, font_size=20, color=WHITE).move_to(rank_bg)

            # Label plate
            name_text = Text(str(name).upper(), font="Montserrat", weight=BOLD, font_size=24, color=WHITE)
            text_plate = RoundedRectangle(corner_radius=0.12, width=name_text.width + 0.55, height=0.52)
            text_plate.set_fill(color="#000000", opacity=0.70).set_stroke(width=0)
            text_plate.move_to([LABEL_X, y_pos + 0.45, 0])
            name_text.move_to(text_plate)

            # Keep label inside safe
            text_plate.move_to(
                [
                    clamp_x(text_plate.get_x(), text_plate.width, 0.70),
                    clamp_y(text_plate.get_y(), text_plate.height, 0.70),
                    0,
                ]
            )
            name_text.move_to(text_plate)

            label_group = VGroup(text_plate, name_text)

            self.play(
                FadeIn(branch, run_time=0.25),
                FadeIn(bolt, run_time=0.25),
                FadeIn(rank_bg, shift=RIGHT * 0.15, run_time=0.35),
                FadeIn(rank_num, shift=RIGHT * 0.15, run_time=0.35),
                FadeIn(label_group, shift=RIGHT * 0.15, run_time=0.4),
            )

            # Bar container (ends BEFORE value gutter)
            container = RoundedRectangle(corner_radius=0.12, width=BAR_MAX_WIDTH + 0.20, height=BAR_HEIGHT)
            container.set_stroke(Theme.NEON_BLUE, width=2, opacity=0.35)
            container.set_fill("#060606", opacity=0.85)
            container.move_to([BAR_START_X + BAR_MAX_WIDTH / 2, y_pos, 0])
            self.add(container)

            # DOTS + LINE run
            num_dots = 12
            dot_positions = []
            dots_group = VGroup()

            for k in range(num_dots):
                t = k / (num_dots - 1)
                x = BAR_START_X + t * target_width
                y_offset = 0.14 if k % 2 else -0.14
                if k == 0 or k == num_dots - 1:
                    y_offset = 0
                pos = np.array([x, y_pos + y_offset, 0])
                dot_positions.append(pos)

                d = Dot(radius=0.055, color="#3A3A3A")
                d.active_color = WHITE
                d.move_to(pos)
                ring = Circle(radius=0.10, color=Theme.NEON_BLUE, stroke_width=1.4).set_opacity(0.25)
                ring.move_to(pos)
                dots_group.add(d, ring)

            self.add(dots_group)

            zig_line = VMobject().set_stroke(color=WHITE, width=3, opacity=0.9)
            zig_glow = VMobject().set_stroke(color=Theme.NEON_BLUE, width=10, opacity=0.22)
            spark = Dot(radius=0.11, color=WHITE)
            spark.set_opacity(0.9)

            line_group = VGroup(zig_glow, zig_line, spark)
            self.add(line_group)

            # Final bar (morph target)
            final_bar = RoundedRectangle(corner_radius=0.10, width=max(0.10, target_width), height=BAR_HEIGHT - 0.16)
            final_bar.set_stroke(width=0)
            final_bar.set_fill(
                color=Theme.C_BAR_GRADIENT if hasattr(Theme, "C_BAR_GRADIENT") else [Theme.NEON_BLUE, Theme.NEON_PINK],
                opacity=1,
            )
            final_bar.align_to(container, LEFT).shift(RIGHT * 0.10).set_y(y_pos).set_opacity(0)

            sheen = RoundedRectangle(corner_radius=0.10, width=max(0.10, target_width), height=(BAR_HEIGHT - 0.16) / 2)
            sheen.set_stroke(width=0).set_fill(color=WHITE, opacity=0.18)
            sheen.align_to(final_bar, UP).align_to(final_bar, LEFT).set_opacity(0)

            # Value number (FIXED COLUMN -> NEVER overlaps bars)
            val_num = DecimalNumber(0, num_decimal_places=0, font_size=24, color=Theme.NEON_BLUE)
            val_num.set_z_index(60)
            self.add(val_num)

            # optional: small pill behind value for readability
            val_pill = RoundedRectangle(corner_radius=0.12, width=1.15, height=0.46)
            val_pill.set_fill(color=BLACK, opacity=0.55).set_stroke(width=0)
            val_pill.set_z_index(55)
            self.add(val_pill)

            tracker = ValueTracker(0)
            flashed_indices = set()

            def update_single_bar(_):
                t = tracker.get_value()
                val_num.set_value(t * value)

                # keep value in a dedicated gutter column
                # adjust x for changing digit width
                x = VALUE_ANCHOR_X - (val_num.width / 2)
                x = clamp_x(x, val_num.width, 0.70)
                val_num.move_to([x, y_pos, 0])

                # pill follows (auto width)
                pill_w = max(1.10, val_num.width + 0.35)
                val_pill.become(
                    RoundedRectangle(corner_radius=0.12, width=pill_w, height=0.46)
                    .set_fill(color=BLACK, opacity=0.55)
                    .set_stroke(width=0)
                )
                val_pill.set_z_index(55)
                val_pill.move_to(val_num)

                total_segments = num_dots - 1
                exact_pos = t * total_segments
                current_idx = int(exact_pos)
                remainder = exact_pos - current_idx
                if current_idx >= total_segments:
                    current_idx = total_segments - 1
                    remainder = 1.0

                p1 = dot_positions[current_idx]
                p2 = dot_positions[current_idx + 1]
                current_tip = p1 + (p2 - p1) * remainder
                spark.move_to(current_tip)

                points = [dot_positions[0]]
                for kk in range(1, current_idx + 1):
                    points.append(dot_positions[kk])
                    points.append(dot_positions[kk])
                points.append(current_tip)

                zig_line.set_points_as_corners(points)
                zig_glow.set_points_as_corners(points)

                if current_idx not in flashed_indices and remainder > 0.12:
                    flashed_indices.add(current_idx)
                    real_idx = current_idx * 2
                    dot_obj = dots_group[real_idx]
                    ring_obj = dots_group[real_idx + 1]
                    dot_obj.set_color(dot_obj.active_color)
                    ring_obj.set_stroke(opacity=0.9).set_stroke(width=2)

            line_group.add_updater(update_single_bar)

            self.play(tracker.animate.set_value(1.0), run_time=1.4, rate_func=linear)

            line_group.remove_updater(update_single_bar)

            # Morph to bar
            temp_straight = Line(dot_positions[0], dot_positions[-1], color=WHITE, stroke_width=4)
            self.add(temp_straight)
            self.remove(line_group, dots_group)

            final_bar.set_opacity(1)
            sheen.set_opacity(1)

            shockwave = Circle(radius=0.08, color=WHITE, stroke_width=4).move_to(final_bar.get_right())
            self.play(
                ReplacementTransform(temp_straight, final_bar),
                FadeIn(sheen, run_time=0.15),
                Flash(final_bar.get_right(), color=WHITE, line_length=0.9, flash_radius=0.45),
                shockwave.animate.scale(6).set_opacity(0),
                run_time=0.42,
                rate_func=rf.ease_out_back,
            )
            self.remove(shockwave)

            bar_groups.append(
                VGroup(branch, bolt, rank_bg, rank_num, label_group, container, final_bar, sheen, val_pill, val_num)
            )

        # ============================================================
        # 8) WINNER REVEAL (premium outro)
        # ============================================================
        self.wait(0.4)

        winner = bar_groups[winner_index]
        others = [g for j, g in enumerate(bar_groups) if j != winner_index]

        self.play(*[g.animate.set_opacity(0.25) for g in others], run_time=0.35)

        winner_bar = winner[6]
        winner_val = winner[9]
        winner_label = winner[4]

        banner_h = 1.65
        banner = RoundedRectangle(width=sf["w"], height=banner_h, corner_radius=0.18)
        banner.set_fill(color="#000000", opacity=0.85)
        banner.set_stroke(color=Theme.NEON_PINK, width=3, opacity=0.8)
        banner.move_to([sf["cx"], sf["bottom"] + (banner_h / 2) + 0.35, 0])
        banner.set_z_index(200)

        win_name = names[winner_index].upper()
        win_val = values[winner_index]

        t1 = Text("TOP LEADER", font="Montserrat", weight=BOLD, font_size=22, color=Theme.TEXT_SUB)
        t2 = Text(win_name, font="Montserrat", weight=BOLD, font_size=46, color=Theme.TEXT_MAIN)
        t3 = Text(f"SCORE: {win_val}", font="Montserrat", weight=BOLD, font_size=22, color=Theme.NEON_BLUE)

        txt = VGroup(t1, t2, t3).arrange(DOWN, buff=0.12).move_to(banner)
        txt.set_z_index(201)

        dimmer = Rectangle(width=60, height=60).set_fill(color=BLACK, opacity=0.25).set_stroke(width=0)
        dimmer.set_z_index(180)
        self.add(dimmer)

        self.play(
            winner.animate.set_opacity(1.0),
            winner_bar.animate.scale(1.05),
            winner_val.animate.set_color(WHITE),
            Indicate(winner_label, color=WHITE, scale_factor=1.02),
            run_time=0.45,
            rate_func=rf.ease_out_back
        )

        self.play(
            GrowFromCenter(banner),
            FadeIn(txt, shift=UP * 0.2),
            run_time=0.6,
            rate_func=rf.ease_out_cubic
        )

        self.play(
            Flash(banner.get_top(), color=WHITE, line_length=0.6, num_lines=10),
            Flash(winner_bar.get_right(), color=Theme.NEON_BLUE, line_length=0.6, num_lines=8),
            run_time=0.35
        )

        self.wait(2.2)