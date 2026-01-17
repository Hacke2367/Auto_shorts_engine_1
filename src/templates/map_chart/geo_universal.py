import sys
import os
import pandas as pd
import numpy as np

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

from manim import *
from manim import rate_functions as rf
from src.config import *
from src.utils import *
from src.data.map_coords import COORDINATES

# ===========================
# ⚙️ MAP CALIBRATION
# ===========================
MAP_Y_SCALE = 1.4
MAP_Y_OFFSET = -0.2

GROUP_COLORS = {
    "Group1": "#00F0FF",
    "Group2": "#FF0055",
    "Group3": "#FFFF00",
    "A": "#00F0FF",
}


class GeoUniversalMap(Scene):
    def construct(self):
        # 1. SETUP
        self.camera.background_color = "#050505"
        self.add(get_branding_border())

        # 2. DATA LOADING
        csv_path = os.path.join(DATA_DIR, "map_data.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError("CRITICAL: map_data.csv nahi mila.")

        df = pd.read_csv(csv_path)
        df.columns = [c.strip().title() for c in df.columns]

        if "Group" not in df.columns: df["Group"] = "Global"
        if "Value" not in df.columns: df["Value"] = 0

        unique_groups = df["Group"].unique()
        is_alliance_mode = len(unique_groups) > 1

        group_color_map = {}
        for i, g in enumerate(unique_groups):
            colors = list(GROUP_COLORS.values())
            group_color_map[g] = colors[i % len(colors)]

        # 3. TITLE
        title_text = "GLOBAL ANALYSIS" if is_alliance_mode else "DATA INSIGHTS"
        title = Text(title_text, font="Montserrat", font_size=36, color=Theme.TEXT_MAIN)
        title.to_edge(UP, buff=0.5)

        # 4. MAP ENGINE
        svg_path = os.path.join(ASSETS_DIR, "svgs", "world.svg")
        world_map = VGroup()
        map_width = 1;
        map_height = 1;
        map_center = ORIGIN;
        map_left = 0;
        map_bottom = 0

        if os.path.exists(svg_path):
            world_map = SVGMobject(svg_path)
            world_map.set_fill(color="#1c2533", opacity=1)
            world_map.set_stroke(color="#3b4d66", width=1)

            safe_width = config.frame_width * 0.95
            world_map.scale_to_fit_width(safe_width)
            world_map.move_to(ORIGIN)

            map_left = world_map.get_left()[0]
            map_right = world_map.get_right()[0]
            map_width = map_right - map_left
            map_bottom = world_map.get_bottom()[1]
            map_top = world_map.get_top()[1]
            map_height = map_top - map_bottom
            map_center = world_map.get_center()

            scan_line = Line(LEFT * 4, RIGHT * 4, color="#00F0FF", stroke_width=4).to_edge(UP)
            scan_line.set_shadow(0.5)

            self.play(Write(title), run_time=0.5)
            self.play(
                FadeIn(world_map, run_time=1.5),
                scan_line.animate.to_edge(DOWN).set_opacity(0),
                run_time=1.5
            )
        else:
            raise FileNotFoundError("Missing world.svg")

        def lat_lon_to_point(lat, lon):
            x_rel = (lon + 180) / 360
            x = map_left + (x_rel * map_width)
            y_rel = (lat + 90) / 180
            y = (y_rel - 0.5) * map_height * MAP_Y_SCALE + map_center[1] + MAP_Y_OFFSET
            return np.array([x, y, 0])

        # 5. PINS GENERATION
        pins_group = VGroup()
        group_dots_map = {g: [] for g in unique_groups}

        df['temp_lon'] = df['Country'].apply(lambda c: COORDINATES.get(c, (0, 0))[1])
        df = df.sort_values('temp_lon')

        for i, (index, row) in enumerate(df.iterrows()):
            country = row['Country']
            group = row['Group']
            val = row['Value']

            if country in COORDINATES:
                lat, lon = COORDINATES[country]
                pos = lat_lon_to_point(lat, lon)
                color = group_color_map.get(group, "#00F0FF")

                dot = Dot(point=pos, color=color, radius=0.06)
                ring = Circle(radius=0.15, color=color, stroke_width=2).move_to(pos)
                target_lock = VGroup(dot, ring)

                is_top = pos[1] > 0
                levels = [3.2, 2.4, 1.6] if is_top else [-3.2, -2.4, -1.6]
                card_y = levels[i % 3]

                name_txt = Text(country.upper(), font="Montserrat", font_size=18, color=color, weight=BOLD)
                sub_txt_str = f"${val}T" if val > 0 else group
                sub_txt = Text(sub_txt_str, font="Montserrat", font_size=12, color=Theme.TEXT_SUB)
                text_group = VGroup(name_txt, sub_txt).arrange(DOWN, buff=0.1)

                card_bg = RoundedRectangle(
                    corner_radius=0.1, height=text_group.height + 0.3, width=text_group.width + 0.5,
                    fill_color=BACKGROUND_COLOR, fill_opacity=0.9, stroke_color=color, stroke_width=1
                )

                card = VGroup(card_bg, text_group)
                card_x = np.clip(pos[0], -3.2, 3.2)
                card.move_to([card_x, card_y, 0])

                p1 = pos
                elbow_clearance = pos[1] + (0.3 if is_top else -0.3)
                p2 = np.array([pos[0], elbow_clearance, 0])
                p3 = np.array([card_x, elbow_clearance, 0])
                card_edge = card.get_bottom()[1] if is_top else card.get_top()[1]
                p4 = np.array([card_x, card_edge, 0])

                connector = VMobject(color=color, stroke_width=2).set_opacity(0.8)
                connector.set_points_as_corners([p1, p2, p3, p4])

                full_assembly = VGroup(target_lock, connector, card)
                pins_group.add(full_assembly)

                if is_alliance_mode:
                    group_dots_map[group].append(dot)

        # 6. ANIMATION
        for pin in pins_group:
            self.play(
                ScaleInPlace(pin[0], 0, rate_func=rf.ease_out_back),
                Create(pin[1], rate_func=rf.linear),
                FadeIn(pin[2], shift=UP * 0.2),
                run_time=0.6
            )

        # 7. CONNECTIONS (With Tracer Packet Preparation)
        travel_paths = []  # Store paths for tracer packets

        if is_alliance_mode:
            connections = VGroup()
            for group_name, dots in group_dots_map.items():
                if len(dots) > 1:
                    color = group_color_map.get(group_name, WHITE)
                    for k in range(len(dots) - 1):
                        p1 = dots[k].get_center()
                        p2 = dots[k + 1].get_center()

                        # The solid path (invisible, for calculation)
                        base_arc = ArcBetweenPoints(p1, p2, angle=PI / 5, color=color)

                        # The visible path (Dashed)
                        arc = DashedVMobject(
                            base_arc.copy(), num_dashes=15,
                            color=color, stroke_width=2
                        )
                        connections.add(arc)

                        # Store info for Tracer: (Path, Color)
                        travel_paths.append((base_arc, color))

            if len(connections) > 0:
                self.play(Create(connections), run_time=1.5)

        # 8. FINAL SCENE: ACTIVE TRAFFIC & PULSE 📡
        if is_alliance_mode:
            # A. Create Tracers
            tracers = []
            anims = []

            for path, color in travel_paths:
                # Glowing Packet
                tracer = Dot(radius=0.08, color=WHITE).set_opacity(0.8)
                tracer.set_glow_factor(0.5)
                # Ensure it starts at the beginning of the path
                tracer.move_to(path.get_start())
                tracers.append(tracer)

                # Add MoveAnimation
                # run_time is slightly randomized for natural look
                anims.append(MoveAlongPath(tracer, path, run_time=2.0, rate_func=linear))

            # B. Add Tracers to Scene & Play
            if len(tracers) > 0:
                self.add(*tracers)  # Add dots to scene
                # Play Movement + Card Flash together
                self.play(
                    *anims,
                    *[Flash(pin[2][0], color=pin[2][0].get_stroke_color(), flash_radius=1.0) for pin in pins_group],
                    run_time=2.0
                )
                # Clean up tracers (fade out)
                self.play(*[FadeOut(t) for t in tracers], run_time=0.5)
            else:
                # Fallback if no paths (single country groups)
                self.play(*[Indicate(pin[0], color=WHITE) for pin in pins_group])

        else:
            # DATA MODE: Pop Winner
            if len(pins_group) > 0:
                self.play(Indicate(pins_group[-1][0], color=WHITE, scale_factor=1.2), run_time=2.0)

        self.wait(2)