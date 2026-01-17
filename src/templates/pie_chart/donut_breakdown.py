import sys
import os
import pandas as pd
import numpy as np

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

from manim import *
# Fix for rate functions
from manim import rate_functions as rf
from src.config import *
from src.utils import *

# ===========================
# ⚙️ CONFIGURATION
# ===========================
COLORS = ["#00F0FF", "#BD00FF", "#FF0055", "#FF9900", "#00FF66", "#FFFF00"]


class DonutChartBreakdown(Scene):
    def construct(self):
        # 1. SETUP
        self.camera.background_color = BACKGROUND_COLOR
        self.add(get_branding_border())

        # 2. DATA LOADING
        csv_path = os.path.join(DATA_DIR, "market_share.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
        else:
            df = pd.DataFrame({
                "Category": ["Apple", "Samsung", "Xiaomi", "Oppo", "Vivo", "Others"],
                "Value": [35, 25, 15, 10, 8, 7]
            })

        categories = df.iloc[:, 0].tolist()
        values = df.iloc[:, 1].tolist()
        total = sum(values)
        max_val_index = values.index(max(values))
        winner_name = categories[max_val_index]
        winner_val = values[max_val_index]

        # 3. TITLE
        title = Text("MARKET SHARE 2025", font="Montserrat", font_size=36, color=Theme.TEXT_MAIN)
        title.to_edge(UP, buff=0.8)

        subtitle = Text(f"Total Market Size: 100%", font="Montserrat", font_size=16, color=Theme.TEXT_SUB)
        subtitle.next_to(title, DOWN, buff=0.1)

        self.play(Write(title), FadeIn(subtitle))

        # 4. DONUT ENGINE
        start_angle = 90 * DEGREES

        slices = VGroup()
        labels = VGroup()
        lines = VGroup()

        outer_radius = 2.0
        inner_radius = 1.3

        winner_slice = None
        winner_vector = None
        winner_label_group = None
        chart_data = []

        for i, val in enumerate(values):
            color = COLORS[i % len(COLORS)]
            percentage = val / total
            angle = percentage * 360 * DEGREES

            # Slice
            sector = AnnularSector(
                inner_radius=inner_radius,
                outer_radius=outer_radius,
                angle=angle,
                start_angle=start_angle,
                fill_color=color,
                fill_opacity=1,
                stroke_color=BACKGROUND_COLOR,
                stroke_width=4
            )

            # Label Geometry
            mid_angle = start_angle + (angle / 2)
            start_point = np.array([np.cos(mid_angle) * outer_radius, np.sin(mid_angle) * outer_radius, 0])
            end_point = np.array(
                [np.cos(mid_angle) * (outer_radius + 0.8), np.sin(mid_angle) * (outer_radius + 0.8), 0])
            pop_vector = np.array([np.cos(mid_angle), np.sin(mid_angle), 0]) * 0.3

            # Line
            line = Line(start_point, end_point, color=color, stroke_width=2).set_opacity(0.6)
            dot = Dot(end_point, color=color, radius=0.05)
            line_group = VGroup(line, dot)

            # Label
            pct_text = Text(f"{int(val)}%", font="Montserrat", font_size=20, color=color, weight=BOLD)
            cat_text = Text(categories[i], font="Montserrat", font_size=14, color=Theme.TEXT_MAIN)

            label_group = VGroup(pct_text, cat_text).arrange(DOWN, buff=0.05)
            label_group.move_to(end_point)

            if np.cos(mid_angle) > 0:
                label_group.next_to(dot, RIGHT, buff=0.1)
            else:
                label_group.next_to(dot, LEFT, buff=0.1)

            slices.add(sector)
            labels.add(label_group)
            lines.add(line_group)

            if i == max_val_index:
                winner_slice = sector
                winner_vector = pop_vector
                winner_label_group = VGroup(label_group, line_group)

            chart_data.append({"slice": sector, "line": line_group, "label": label_group})
            start_angle += angle

        full_chart = VGroup(slices, lines, labels)
        full_chart.move_to(DOWN * 0.2)

        # 5. ANIMATION SEQUENCE

        # A. Construction (Draw Slices)
        for item in chart_data:
            self.play(Create(item["slice"]), run_time=0.3, rate_func=linear)

        # B. Center Text (Initial State)
        center_text_init = VGroup(
            Text("GLOBAL", font="Montserrat", font_size=18, color=Theme.TEXT_SUB),
            Text("DATA", font="Montserrat", font_size=22, color=Theme.TEXT_MAIN)
        ).arrange(DOWN, buff=0.1)
        center_text_init.move_to(slices.get_center())
        self.play(Write(center_text_init))

        # C. Lines & Labels
        self.play(
            LaggedStart(
                *[AnimationGroup(Create(item["line"]),
                                 FadeIn(item["label"], shift=item["line"].get_center() - item["label"].get_center()))
                  for item in chart_data],
                lag_ratio=0.3
            ),
            run_time=1.5
        )

        self.wait(0.5)

        # D. THE DYNAMIC POP (Upgraded)

        others_slices = [s for s in slices if s is not winner_slice]
        others_labels = [l for l in labels if l is not winner_label_group[0]]
        others_lines = [l for l in lines if l is not winner_label_group[1]]

        # Create New Center Text for Winner
        center_text_winner = VGroup(
            Text("LEADER", font="Montserrat", font_size=16, color=Theme.TEXT_SUB),
            Text(f"{winner_name}", font="Montserrat", font_size=24, color=COLORS[max_val_index], weight=BOLD)
        ).arrange(DOWN, buff=0.1)
        center_text_winner.move_to(slices.get_center())

        self.play(
            # 1. Winner Pops Out
            winner_slice.animate.shift(winner_vector).scale(1.1),
            winner_label_group.animate.shift(winner_vector),

            # 2. Focus Effect (Dim others)
            *[s.animate.set_opacity(0.3) for s in others_slices],
            *[l.animate.set_opacity(0.3) for l in others_labels],
            *[line.animate.set_opacity(0.1) for line in others_lines],

            # 3. Dynamic Center Change (Transform)
            Transform(center_text_init, center_text_winner),

            run_time=1.2,
            rate_func=rf.ease_out_elastic  # Bounce effect
        )

        self.play(Indicate(winner_slice, color=COLORS[max_val_index], scale_factor=1.05))
        self.wait(3)