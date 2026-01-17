import sys
import os
import pandas as pd
import numpy as np
import random
from manim import *
import manim.utils.rate_functions as rf

# --- 1. PROJECT PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

# --- IMPORTS & FALLBACKS ---
try:
    from src.config import *
    from src.utils import *
except ImportError:
    DATA_DIR = "./"
    ASSETS_DIR = "./assets"


    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PURPLE = "#BD00FF"
        NEON_PINK = "#FF0055"


    def get_branding_border():
        border = Rectangle(height=16 / 9 * 7.5, width=7.5)
        border.set_stroke(width=12, color=[Theme.NEON_BLUE, Theme.NEON_PURPLE, Theme.NEON_PINK], opacity=0.9)
        return border


# --- 2. ROBUST DATA LOADING ---
def load_and_clean_data(csv_filename):
    if not os.path.exists(csv_filename):
        print(f"⚠️ Warning: '{csv_filename}' not found. Creating dummy data.")
        data = {
            'Metric': ['SPEED', 'IQ', 'NET WORTH', 'RIZZ'],
            'P1_Value': ['99', '150', '$200B', 'Yes'],
            'P2_Value': ['80', '140', '$50B', 'No'],
            'Winner': [1, 1, 1, 1]
        }
        return pd.DataFrame(data)

    try:
        df = pd.read_csv(csv_filename)
        df.columns = df.columns.str.strip()
        df['Metric'] = df['Metric'].astype(str).str.strip().str.upper()
        df['P1_Value'] = df['P1_Value'].astype(str).str.strip()
        df['P2_Value'] = df['P2_Value'].astype(str).str.strip()
        df = df[df['Metric'] != 'NAN']
        df = df[df['Metric'] != '']
        df['Winner'] = pd.to_numeric(df['Winner'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        print(f"❌ Critical Error reading CSV: {e}")
        sys.exit(1)


class VsCard(Scene):
    def construct(self):
        self.camera.background_color = "#050505"

        # --- CONFIGURATION ---
        C_P1 = "#00F0FF"  # Cyan (Abhishek)
        C_P2 = "#FF0055"  # Pink (Pandey)
        C_WIN = "#00FF66"  # Green (Generic Win)
        C_GOLD = "#FFD700"  # Gold

        PLAYER_1 = {"name": "ABHISHEK", "color": C_P1, "image": "player1.png"}
        PLAYER_2 = {"name": "PANDEY", "color": C_P2, "image": "player2.png"}

        csv_path = os.path.join(DATA_DIR, "vs_data.csv")
        df = load_and_clean_data(csv_path)

        # LAYERS
        static_layer = VGroup()  # Grid, Border
        bg_anim_layer = VGroup()  # Rain/Streaks

        self.add(static_layer, bg_anim_layer)

        # --- A. BACKGROUND RE-IMAGINED: CYBER RAIN ---
        # Grid (Darker now to let rain shine)
        grid = NumberPlane(
            x_range=[-20, 20, 1], y_range=[-20, 20, 1],
            background_line_style={"stroke_color": "#222222", "stroke_width": 1, "stroke_opacity": 0.4},
            axis_config={"stroke_opacity": 0}
        )
        grid.add_updater(lambda m, dt: m.shift(UL * 0.05 * dt))
        static_layer.add(grid)

        # NEW: High Speed Vertical Streaks (Rain)
        rain_group = VGroup()
        for _ in range(40):  # More particles for fuller screen
            # Lines instead of Dots for speed effect
            length = random.uniform(0.2, 0.6)
            line = Line(start=ORIGIN, end=UP * length)
            line.set_stroke(width=random.uniform(1, 3), color=random.choice([C_P1, C_P2, GREY_B]))
            line.set_opacity(random.uniform(0.3, 0.7))

            # Position ANYWHERE on screen width (Full fill)
            line.move_to([random.uniform(-4, 4), random.uniform(-4, 4), 0])

            # Custom velocity attribute
            line.velocity = DOWN * random.uniform(2.0, 4.0)  # Fast falling
            rain_group.add(line)

        def update_rain(mob, dt):
            for line in mob:
                line.shift(line.velocity * dt)
                if line.get_y() < -4.5:  # Reset to top
                    line.move_to([random.uniform(-4, 4), 4.5, 0])
                    # Randomize speed again for variety
                    line.velocity = DOWN * random.uniform(2.0, 4.0)

        rain_group.add_updater(update_rain)
        bg_anim_layer.add(rain_group)

        # Branding Border
        branding_border = VGroup()
        try:
            bb = get_branding_border()
            bb.move_to(ORIGIN)
            bb.set_z_index(300)
            branding_border.add(bb)
            self.add(branding_border)
        except:
            pass

        # --- B. HEADER ---
        t_p1 = Text(PLAYER_1["name"], font="Montserrat", weight=BOLD, font_size=32, color=C_P1)
        t_vs = Text("VS", font="Montserrat", weight=BOLD, font_size=24, color=C_GOLD)
        t_p2 = Text(PLAYER_2["name"], font="Montserrat", weight=BOLD, font_size=32, color=C_P2)

        header_group = VGroup(t_p1, t_vs, t_p2).arrange(RIGHT, buff=0.4).to_edge(UP, buff=1.2)
        vs_box = Square(side_length=0.8, color=C_GOLD, stroke_width=4).rotate(45 * DEGREES).move_to(t_vs.get_center())

        vs_anim_grp = VGroup(vs_box, t_vs)
        vs_anim_grp.add_updater(lambda m, dt: m.scale(1 + np.sin(self.time * 8) * 0.005))  # Intense Heartbeat

        # --- C. UI CONSTRUCTION ---
        # Positioning
        Y_AVATAR = 0.8
        Y_METRIC = -1.6
        Y_VALUE = -2.9

        # Dimensions
        FRAME_WIDTH = 2.2
        FRAME_HEIGHT = 3.0
        X_OFFSET = 2.0

        def create_player_entity(config, x_pos):
            # 1. Background (Dark Glass)
            bg = RoundedRectangle(width=FRAME_WIDTH, height=FRAME_HEIGHT, corner_radius=0.1, stroke_opacity=0)
            bg.set_fill(color="#050505", opacity=0.95)
            bg.move_to([x_pos, Y_AVATAR, 0])

            # 2. Image
            img_file = os.path.join(ASSETS_DIR, "images", config["image"])
            if os.path.exists(img_file):
                img = ImageMobject(img_file)
                img.scale_to_fit_width(FRAME_WIDTH - 0.1)
                if img.height > (FRAME_HEIGHT - 0.1):
                    img.scale_to_fit_height(FRAME_HEIGHT - 0.1)
            else:
                img = Text(config["name"][0], font="Montserrat", weight=BOLD, font_size=70, color=config["color"])

            img.move_to(bg.get_center())

            # 3. HUD (Tech Corners)
            border = RoundedRectangle(width=FRAME_WIDTH, height=FRAME_HEIGHT, corner_radius=0.1)
            border.set_stroke(color=config["color"], width=1, opacity=0.5)
            border.move_to(bg.get_center())

            c_len = 0.4
            c_color = config["color"]
            corners = VGroup()
            corners.add(VGroup(Line(UL * 0, RIGHT * c_len), Line(UL * 0, DOWN * c_len)).move_to(bg.get_corner(UL)))
            corners.add(VGroup(Line(UR * 0, LEFT * c_len), Line(UR * 0, DOWN * c_len)).move_to(bg.get_corner(UR)))
            corners.add(VGroup(Line(DL * 0, RIGHT * c_len), Line(DL * 0, UP * c_len)).move_to(bg.get_corner(DL)))
            corners.add(VGroup(Line(DR * 0, LEFT * c_len), Line(DR * 0, UP * c_len)).move_to(bg.get_corner(DR)))
            corners.set_stroke(color=c_color, width=4)

            hud_layer = VGroup(border, corners)

            # 4. Badge
            score_circle = Circle(radius=0.35, color=WHITE, stroke_width=2, fill_color="#1a1a1a", fill_opacity=1)
            score_circle.move_to(bg.get_top())
            score_num = Text("0", font="Montserrat", weight=BOLD, font_size=24, color=WHITE).move_to(score_circle)
            badge_grp = VGroup(score_circle, score_num)

            main_group = Group(bg, img, hud_layer, badge_grp)
            return main_group, hud_layer, badge_grp, score_num

        p1_grp, p1_hud, p1_badge, p1_score = create_player_entity(PLAYER_1, -X_OFFSET)
        p2_grp, p2_hud, p2_badge, p2_score = create_player_entity(PLAYER_2, X_OFFSET)

        # Metric & Values
        metric_bg = RoundedRectangle(width=4.5, height=0.7, corner_radius=0.35, color=WHITE, stroke_width=1)
        metric_bg.set_fill(color="#111111", opacity=1)
        metric_bg.move_to([0, Y_METRIC, 0])

        val_box_1 = RoundedRectangle(width=2.0, height=0.9, corner_radius=0.2, color=C_P1, stroke_width=4).move_to(
            [-X_OFFSET, Y_VALUE, 0])
        val_box_1.set_fill(color="#000000", opacity=0.9)

        val_box_2 = RoundedRectangle(width=2.0, height=0.9, corner_radius=0.2, color=C_P2, stroke_width=4).move_to(
            [X_OFFSET, Y_VALUE, 0])
        val_box_2.set_fill(color="#000000", opacity=0.9)

        # --- D. INTRO ---
        self.play(
            LaggedStart(
                FadeIn(header_group, shift=DOWN), Create(vs_box),
                FadeIn(p1_grp, shift=RIGHT), FadeIn(p2_grp, shift=LEFT),
                Create(metric_bg), FadeIn(val_box_1), FadeIn(val_box_2),
                lag_ratio=0.05
            ),
            run_time=1.2
        )
        self.add(vs_anim_grp)

        # --- E. GAME LOOP ---
        p1_points = 0
        p2_points = 0

        curr_m = VGroup()
        curr_v1 = VGroup()
        curr_v2 = VGroup()

        for index, row in df.iterrows():
            metric_text = row['Metric']
            v1_text = row['P1_Value']
            v2_text = row['P2_Value']
            winner = row['Winner']

            t_metric = Text(metric_text, font="Montserrat", weight=BOLD, font_size=22, color=C_GOLD).move_to(metric_bg)
            t_v1 = Text(v1_text, font="Montserrat", weight=BOLD, font_size=28, color=WHITE).move_to(val_box_1)
            t_v2 = Text(v2_text, font="Montserrat", weight=BOLD, font_size=28, color=WHITE).move_to(val_box_2)

            if t_metric.width > 4.0: t_metric.scale_to_fit_width(4.0)
            if t_v1.width > 1.8: t_v1.scale_to_fit_width(1.8)
            if t_v2.width > 1.8: t_v2.scale_to_fit_width(1.8)

            self.play(
                FadeOut(curr_m, shift=UP * 0.2), FadeOut(curr_v1, shift=UP * 0.2), FadeOut(curr_v2, shift=UP * 0.2),
                FadeIn(t_metric, shift=UP * 0.2), FadeIn(t_v1, shift=UP * 0.2), FadeIn(t_v2, shift=UP * 0.2),
                run_time=0.3
            )

            # --- FOCUS LOGIC ---
            win_grp = None
            if winner == 1:
                win_grp = p1_grp
                win_hud_corners = p1_hud[1]
                win_score_obj = p1_score
                win_val_box = val_box_1
                lose_grp = p2_grp
                lose_val_box = val_box_2
                p1_points += 1
            elif winner == 2:
                win_grp = p2_grp
                win_hud_corners = p2_hud[1]
                win_score_obj = p2_score
                win_val_box = val_box_2
                lose_grp = p1_grp
                lose_val_box = val_box_1
                p2_points += 1

            if win_grp:
                win_grp.set_z_index(100)
                lose_grp.set_z_index(0)

                new_score_txt = Text(str(p1_points if winner == 1 else p2_points), font="Montserrat", weight=BOLD,
                                     font_size=24, color=C_WIN).move_to(win_score_obj)

                self.play(
                    win_grp.animate.scale(1.15).set_opacity(1),
                    win_hud_corners.animate.set_stroke(color=C_WIN, width=6),
                    win_val_box.animate.set_stroke(color=C_WIN, width=6),
                    lose_grp.animate.scale(0.9).set_opacity(0.3),
                    lose_val_box.animate.set_opacity(0.3),
                    Transform(win_score_obj, new_score_txt),
                    Flash(win_score_obj, color=C_WIN, line_length=0.2, num_lines=4),
                    run_time=0.4, rate_func=rf.ease_out_back
                )
                self.wait(0.6)

                # Reset
                orig_col_win = C_P1 if winner == 1 else C_P2
                self.play(
                    win_grp.animate.scale(1 / 1.15),
                    win_hud_corners.animate.set_stroke(color=orig_col_win, width=4),
                    win_val_box.animate.set_stroke(color=orig_col_win, width=4),
                    win_score_obj.animate.set_color(WHITE),
                    lose_grp.animate.scale(1 / 0.9).set_opacity(1),
                    lose_val_box.animate.set_opacity(0.9),
                    run_time=0.3
                )
            else:
                self.wait(1.0)

            curr_m = t_metric
            curr_v1 = t_v1
            curr_v2 = t_v2

        # --- F. NEW OUTRO (SIDE TEXT STRATEGY) ---
        final_winner = 0
        if p1_points > p2_points:
            final_winner = 1
        elif p2_points > p1_points:
            final_winner = 2

        # Elements to disappear
        outro_fade = [metric_bg, curr_m, val_box_1, curr_v1, val_box_2, curr_v2, vs_anim_grp, header_group,
                      branding_border]

        winner_grp = None
        win_name = ""
        win_color = WHITE
        text_pos = ORIGIN  # Will change

        if final_winner == 1:
            # P1 (Left) Wins -> Fade P2 (Right) -> Text goes Right
            outro_fade.append(p2_grp)
            winner_grp = p1_grp
            win_name = PLAYER_1["name"]
            win_color = C_P1  # Winner's Color
            text_pos = [2.0, 0.5, 0]  # RIGHT SIDE
        elif final_winner == 2:
            # P2 (Right) Wins -> Fade P1 (Left) -> Text goes Left
            outro_fade.append(p1_grp)
            winner_grp = p2_grp
            win_name = PLAYER_2["name"]
            win_color = C_P2  # Winner's Color
            text_pos = [-2.0, 0.5, 0]  # LEFT SIDE
        else:
            outro_fade.append(p1_grp)
            outro_fade.append(p2_grp)
            text_pos = ORIGIN

        # 1. Fade everything except winner
        self.play(*[FadeOut(m) for m in outro_fade], run_time=0.8)

        if winner_grp:
            # 2. Winner Action (Just slight Zoom, NO MOVE)
            winner_grp.set_z_index(200)

            # Create "Cool" Text
            lbl_text = Text("WINNER", font="Montserrat", weight=BOLD, font_size=30, color=WHITE)
            name_text = Text(win_name, font="Montserrat", weight=BOLD, font_size=50, color=win_color)

            final_text_grp = VGroup(lbl_text, name_text).arrange(DOWN, buff=0.2)
            final_text_grp.move_to(text_pos)  # Opposing side

            self.play(
                winner_grp.animate.scale(1.2),  # Slight zoom in place
                winner_grp[2][1].animate.set_stroke(color=win_color, width=10),  # Glow borders
                Write(final_text_grp),
                run_time=0.8
            )
            # Add Flash behind text for impact
            self.play(Flash(final_text_grp, color=win_color, line_length=0.5, num_lines=8))

        else:
            # Draw
            end_txt = Text("IT'S A DRAW!", font="Montserrat", weight=BOLD, font_size=50, color=WHITE)
            self.play(ScaleInPlace(end_txt, 1.2))

        self.wait(3)