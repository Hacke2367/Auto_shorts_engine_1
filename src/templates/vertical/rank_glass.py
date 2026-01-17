import sys
import os
import pandas as pd

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

from manim import *
from src.config import *
from src.utils import *

# ==========================================
# ⚙️ CONFIGURATION ZONE (Yahan Change Karo)
# ==========================================
# Options: "TECH", "WEALTH", "DANGER", "NATURE"
SELECTED_THEME = "WEALTH"

# Theme Dictionary
THEMES = {
    "TECH": {
        "bars": [Theme.NEON_BLUE, Theme.NEON_PURPLE],
        "rank1": [Theme.NEON_GREEN, Theme.NEON_BLUE],
        "text": Theme.NEON_BLUE
    },
    "WEALTH": {
        "bars": ["#FFD700", "#FF8C00"],  # Gold -> Orange
        "rank1": ["#E0FFFF", "#00FFFF"],  # Diamond
        "text": "#FFD700"
    },
    "DANGER": {
        "bars": ["#FF0000", "#FF4500"],  # Red -> Dark Orange
        "rank1": ["#FFFF00", "#FFFFFF"],  # Yellow -> White
        "text": "#FF0000"
    },
    "NATURE": {
        "bars": ["#32CD32", "#008000"],  # Lime -> Green
        "rank1": ["#ADFF2F", "#32CD32"],  # Bright Lime
        "text": "#32CD32"
    }
}


class RankGlassSpotlight(Scene):
    def construct(self):
        # 1. THEME LOADING
        # Agar spelling mistake hui to default TECH utha lega
        theme = THEMES.get(SELECTED_THEME, THEMES["TECH"])

        # 2. SETUP BACKGROUND
        self.camera.background_color = BACKGROUND_COLOR
        border = get_branding_border()
        self.add(border)

        # -----------------------------------------
        # 3. DATA LOADING (EXCEL / CSV)
        # -----------------------------------------
        csv_path = os.path.join(DATA_DIR, "ai_stats.csv")

        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            # CSV mein columns hone chahiye: 'Name' aur 'Value'
            # Optional: 'Description' column bhi ho sakta hai subtitle ke liye
        else:
            # Fallback Data (Agar CSV na mile)
            df = pd.DataFrame({
                "Name": ["Elon Musk", "Jeff Bezos", "Mark Zuckerberg", "Larry Ellison", "Bernard Arnault"],
                "Value": [250, 210, 180, 150, 130]  # In Billions
            })

        # Logic: Sort High to Low -> Take Top 10 -> Reverse for Countdown (5...1)
        df_sorted = df.sort_values(by="Value", ascending=False).head(10)
        df_reversed = df_sorted.iloc[::-1].reset_index(drop=True)

        names = df_reversed["Name"].tolist()
        values = df_reversed["Value"].tolist()
        max_val = max(values)
        total_items = len(names)

        # -----------------------------------------
        # 4. STAGE LAYOUT (Title & Subtitle)
        # -----------------------------------------

        # Title Gradient Color Theme se aayega
        title_text = "RICHEST PEOPLE 2025"  # CSV se bhi le sakte ho future mein
        title = Text(title_text, font="Montserrat", font_size=42)
        title.set_color(theme["text"])  # Theme color apply
        title.to_edge(UP, buff=1.5)

        # Subtitle
        sub_text = "Net Worth in Billions ($)"  # Ye CSV column header bhi ho sakta hai
        subtitle = Text(sub_text, font="Montserrat", font_size=24, color=Theme.TEXT_SUB)
        subtitle.next_to(title, DOWN, buff=0.2)

        # Axis System
        # Y-Axis Max Value Logic (Thoda buffer upar taaki bar touch na kare)
        y_max = ((max_val // 10) + 1) * 10

        axes = Axes(
            x_range=[0, total_items, 1],
            y_range=[0, y_max + (y_max * 0.1), y_max // 4],  # 10% extra height
            x_length=7,
            y_length=6,
            axis_config={"color": Theme.AXIS_COLOR, "stroke_width": 2, "include_tip": False},
            x_axis_config={"include_numbers": False, "stroke_opacity": 1},
            y_axis_config={"include_numbers": True, "color": Theme.TEXT_SUB, "font_size": 20}
        ).center().to_edge(DOWN, buff=2.5)

        # Intro Animation (Title & Axis)
        self.play(
            Write(title),
            FadeIn(subtitle, shift=UP),
            Create(axes),
            run_time=1.5
        )

        # -----------------------------------------
        # 5. THE ANIMATION LOOP
        # -----------------------------------------
        active_bars = []
        # Dynamic Width: Agar 5 log hain to 0.8 width, agar 10 hain to 0.5
        bar_width = min(0.8, 6.0 / total_items)

        # Rank Counter Setup (Top Right)
        rank_counter = Text("", font="Montserrat", font_size=70, color=theme["text"])
        rank_counter.to_corner(UR, buff=0.8)
        self.add(rank_counter)

        for i in range(total_items):
            name = names[i]
            value = values[i]
            current_rank = total_items - i

            # --- A. Rank Counter ---
            new_rank_text = Text(f"#{current_rank}", font="Montserrat", font_size=70, color=theme["text"])

            # Rank 1 ka color alag hoga (Theme se)
            if current_rank == 1:
                # Rank 1 ka color theme['rank1'][1] (Second color of gradient)
                new_rank_text.set_color(theme["rank1"][1])

            new_rank_text.move_to(rank_counter)

            # --- B. Bar Setup ---
            bar_pos = axes.c2p(i + 0.5, 0)
            target_height = axes.c2p(0, value)[1] - axes.c2p(0, 0)[1]

            bar = Rectangle(width=bar_width, height=target_height)

            # Color Logic from Theme
            bar_colors = theme["bars"]
            if current_rank == 1: bar_colors = theme["rank1"]

            bar.set_fill(color=bar_colors, opacity=0.8)
            bar.set_stroke(color=bar_colors, width=5)
            bar.move_to(bar_pos, aligned_edge=DOWN)

            # --- C. Labels & Numbers ---
            # Name Label
            label = Text(str(name), font="Montserrat", font_size=20, color=Theme.TEXT_SUB)
            label.next_to(bar, DOWN, buff=0.2)

            # Value Number
            val_text = DecimalNumber(0, num_decimal_places=0, font_size=28, color=Theme.TEXT_MAIN)
            val_text.next_to(bar, UP, buff=0.2)

            # --- D. Animation Sequence ---

            # 1. Dim Previous Bars
            if active_bars:
                self.play(
                    *[b.animate.set_opacity(0.3) for b in active_bars],
                    Transform(rank_counter, new_rank_text),
                    run_time=0.4
                )
            else:
                self.play(Transform(rank_counter, new_rank_text), run_time=0.4)

            # 2. Grow Current Bar
            self.play(
                GrowFromEdge(bar, DOWN),
                FadeIn(label, shift=UP),
                ChangeDecimalToValue(val_text, value),
                run_time=0.8
            )

            # 3. Flash Effect
            self.play(Indicate(bar, color=Theme.TEXT_MAIN), run_time=0.4)

            # 4. Store
            group = VGroup(bar, val_text, label)
            active_bars.append(group)

            # 5. Wait (Voiceover Time)
            # Top 3 pe zyada focus
            self.wait(1.5 if current_rank > 3 else 2.5)

        # --- E. FINAL REVEAL ---
        self.play(
            *[b.animate.set_opacity(1) for b in active_bars],
            FadeOut(rank_counter),
            run_time=1.0
        )

        # Subscribe Text (Theme Color)
        sub_text = Text("SUBSCRIBE", font="Montserrat", font_size=60, color=theme["text"])
        self.play(FocusOn(sub_text), Write(sub_text))
        self.wait(2)