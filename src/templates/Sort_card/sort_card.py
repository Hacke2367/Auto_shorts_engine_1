import sys
import os
import pandas as pd
import numpy as np
import random
from manim import *
import manim.utils.rate_functions as rf

# --- 1. PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

try:
    from src.config import *
    from src.utils import *
except ImportError:
    DATA_DIR = os.path.join(project_root, "data")
    ASSETS_DIR = os.path.join(project_root, "assets")


    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"


    def get_branding_border():
        border = Rectangle(height=16 / 9 * 7.5, width=7.5)
        border.set_stroke(width=10, color=[Theme.NEON_BLUE, Theme.NEON_PINK], opacity=0.8)
        return border


# --- 2. DATA LOADING ---
def load_data(csv_filename):
    if not os.path.exists(csv_filename):
        print(f"⚠️ Warning: '{csv_filename}' not found. Creating dummy data.")
        data = {
            'Image': ['python.jpg', 'java.jpg', 'html.jpg', 'cpp.jpg'],
            'Category': [1, 2, 2, 1],
            'Reason': ['AI KING', 'VERBOSE', 'NOT CODE', 'FAST AF']
        }
        return pd.DataFrame(data)
    try:
        df = pd.read_csv(csv_filename)
        df.columns = df.columns.str.strip()
        if 'Reason' not in df.columns:
            df['Reason'] = ["UNKNOWN"] * len(df)
        return df
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


class SortCard(Scene):
    def construct(self):
        self.camera.background_color = "#050505"

        # ==========================================
        # 🛠️ CONFIG SECTION
        # ==========================================
        TITLE_LEFT = "TIER 1"
        TITLE_RIGHT = "TIER 2"

        C_LEFT = Theme.NEON_BLUE
        C_RIGHT = Theme.NEON_PINK
        C_GOLD = "#FFD700"  # Fixed: Added back for Tie Breaker

        # POSITIONS
        TITLE_Y = 3.5
        ARROW_Y = 2.5
        SPAWN_Y = 1.8
        BOX_Y = -2.2

        LEFT_BOX_POS = [-2.2, BOX_Y, 0]
        RIGHT_BOX_POS = [2.2, BOX_Y, 0]
        # ==========================================

        df = load_data(os.path.join(DATA_DIR, "sort_data.csv"))

        # GROUPS
        static_layer = VGroup()
        shaft_layer = VGroup()
        bin_back_layer = VGroup()
        bin_back_layer.set_z_index(10)
        collected_items_layer = Group()
        collected_items_layer.set_z_index(50)
        bin_front_layer = VGroup()
        bin_front_layer.set_z_index(100)
        ui_layer = VGroup()
        ui_layer.set_z_index(200)

        self.add(static_layer, shaft_layer, bin_back_layer, collected_items_layer, bin_front_layer, ui_layer)

        # --- A. BACKGROUND ---
        bg_grid = NumberPlane(
            x_range=[-10, 10, 1], y_range=[-20, 20, 1],
            background_line_style={"stroke_color": "#222", "stroke_width": 2, "stroke_opacity": 0.2},
            axis_config={"stroke_opacity": 0}
        )
        static_layer.add(bg_grid)

        # Moving Walls
        def create_wall_lines(x_start, direction):
            lines = VGroup()
            for i in range(5):
                x = x_start + (i * 0.5 * direction)
                line = Line(start=DOWN * 8, end=UP * 8)
                line.set_stroke(color=GREY_C, width=2, opacity=0.1 + (0.1 * (5 - i)))
                line.move_to([x, 0, 0])
                lines.add(line)
            return lines

        static_layer.add(create_wall_lines(-3.5, 1), create_wall_lines(3.5, -1))

        # Rungs
        rungs = VGroup()
        for i in range(8):
            y = -4 + (i * 2.0)
            rung = Line(start=LEFT * 4, end=RIGHT * 4)
            rung.set_stroke(color=GREY_B, width=1, opacity=0.3)
            rung.move_to([0, y, 0])
            rungs.add(rung)

        def update_rungs(mob, dt):
            for line in mob:
                line.shift(UP * 2.5 * dt)
                if line.get_y() > 5:
                    line.move_to([0, -5, 0])

        rungs.add_updater(update_rungs)
        shaft_layer.add(rungs)

        # Branding
        try:
            bb = get_branding_border()
            bb.move_to(ORIGIN)
            ui_layer.add(bb)
        except:
            pass

        # --- B. HEADER ---
        txt_left = Text(TITLE_LEFT, font="Montserrat", weight=BOLD, font_size=36, color=WHITE)
        txt_vs = Text("vs", font="Montserrat", weight=BOLD, font_size=28, color=GREY_B)
        txt_right = Text(TITLE_RIGHT, font="Montserrat", weight=BOLD, font_size=36, color=WHITE)

        title_group = VGroup(txt_left, txt_vs, txt_right).arrange(RIGHT, buff=0.2)
        title_group.move_to(UP * TITLE_Y)

        line_width = title_group.width + 0.4
        line_left = Line(LEFT * line_width / 2, ORIGIN).set_stroke(color=C_LEFT, width=4)
        line_right = Line(ORIGIN, RIGHT * line_width / 2).set_stroke(color=C_RIGHT, width=4)
        underline = VGroup(line_left, line_right).arrange(RIGHT, buff=0).next_to(title_group, DOWN, buff=0.1)

        ui_layer.add(title_group, underline)
        spawn_arrow = Triangle(color=GREY_A, fill_opacity=1).scale(0.2).rotate(180 * DEGREES).move_to(UP * ARROW_Y)
        ui_layer.add(spawn_arrow)

        # --- C. THE NEO-PODS ---
        def create_neo_pod(label_text, color, pos):
            w, h = 2.6, 2.2

            p1 = pos + np.array([-w / 2, -h / 2, 0])
            p2 = pos + np.array([w / 2, -h / 2, 0])
            p3 = pos + np.array([w / 2 + 0.2, -h / 2 - 0.4, 0])
            p4 = pos + np.array([-w / 2 - 0.2, -h / 2 - 0.4, 0])
            base = Polygon(p1, p2, p3, p4, color=color, stroke_width=3, fill_opacity=0.3, fill_color=color)

            glass_back = RoundedRectangle(width=w, height=h, corner_radius=0.1)
            glass_back.set_stroke(width=0)
            glass_back.set_fill(color=color, opacity=0.05)
            glass_back.move_to(pos)
            back_grp = VGroup(glass_back, base)

            rim = RoundedRectangle(width=w, height=0.1, corner_radius=0.05, color=color)
            rim.set_fill(color=color, opacity=0.9)
            rim.move_to(pos + UP * h / 2)

            glass_front = RoundedRectangle(width=w, height=h, corner_radius=0.1)
            glass_front.set_stroke(color=color, width=2, opacity=0.5)
            glass_front.move_to(pos)

            label_plate = RoundedRectangle(width=1.8, height=0.4, corner_radius=0.05, color=color, stroke_width=1)
            label_plate.set_fill(color=color, opacity=0.2)
            label_plate.next_to(base.get_top(), DOWN, buff=0.2)
            name_txt = Text(label_text, font="Montserrat", weight=BOLD, font_size=18, color=WHITE).move_to(label_plate)

            counter_bg = RoundedRectangle(width=1.0, height=0.5, corner_radius=0.1, color=color, stroke_width=2)
            counter_bg.set_fill(color=color, opacity=0.3)
            counter_bg.next_to(label_plate, DOWN, buff=0.1)
            counter_txt = Text("0", font="Montserrat", weight=BOLD, font_size=24, color=WHITE).move_to(counter_bg)

            front_grp = VGroup(rim, glass_front, label_plate, name_txt, counter_bg, counter_txt)

            # Group for scaling later
            full_grp = VGroup(back_grp, front_grp)

            return back_grp, front_grp, glass_back, counter_txt, full_grp

        l_back, l_front, l_box, l_count_txt, l_full_grp = create_neo_pod(TITLE_LEFT, C_LEFT, np.array(LEFT_BOX_POS))
        bin_back_layer.add(l_back)
        bin_front_layer.add(l_front)

        r_back, r_front, r_box, r_count_txt, r_full_grp = create_neo_pod(TITLE_RIGHT, C_RIGHT, np.array(RIGHT_BOX_POS))
        bin_back_layer.add(r_back)
        bin_front_layer.add(r_front)

        # Intro
        self.play(
            FadeIn(static_layer), FadeIn(shaft_layer),
            Write(title_group), Create(underline),
            FadeIn(spawn_arrow),
            FadeIn(bin_back_layer, shift=UP), FadeIn(bin_front_layer, shift=UP),
            run_time=1.2
        )

        # --- D. SORTING LOOP ---
        SPAWN_POINT_VEC = UP * SPAWN_Y
        ENTRY_POINT_VEC = UP * SPAWN_Y + RIGHT * 5.0

        def get_slot_pos(box_center, index):
            rows = [-0.6, 0.4]
            cols = [-0.7, 0, 0.7]
            row_idx = index // 3
            col_idx = index % 3
            r = rows[row_idx % 2]
            c = cols[col_idx]
            return box_center + np.array([c, r, 0])

        count_left = 0
        count_right = 0

        for index, row in df.iterrows():
            img_name = row['Image']
            reason_text = str(row['Reason']).upper()
            try:
                category = int(row['Category'])
            except:
                category = 2

            # Spawn
            img_path = os.path.join(ASSETS_DIR, "images", img_name)
            if os.path.exists(img_path):
                item = ImageMobject(img_path)
                item.scale_to_fit_width(1.3)
            else:
                item = Text("?", font_size=60, color=WHITE)

            item.move_to(ENTRY_POINT_VEC)
            item.set_z_index(50)

            self.play(item.animate.move_to(SPAWN_POINT_VEC), run_time=0.4, rate_func=rf.ease_out_quad)

            # Reasoning Phase
            target_color = C_LEFT if category == 1 else C_RIGHT

            reason_bg = RoundedRectangle(width=len(reason_text) * 0.3 + 0.4, height=0.6, corner_radius=0.1,
                                         color=target_color)
            reason_bg.set_fill(color=BLACK, opacity=0.9)
            reason_bg.next_to(item, UP, buff=0.1)
            reason_lbl = Text(reason_text, font="Montserrat", weight=BOLD, font_size=24, color=target_color).move_to(
                reason_bg)
            reason_grp = VGroup(reason_bg, reason_lbl)
            reason_grp.set_z_index(200)

            scan_line = Line(LEFT * 0.7, RIGHT * 0.7, color=WHITE).next_to(item, UP, buff=0)
            self.play(scan_line.animate.next_to(item, DOWN, buff=0), FadeIn(reason_grp, shift=DOWN), run_time=0.3)
            scan_line.set_opacity(0)

            self.wait(0.5)
            self.play(FadeOut(reason_grp), run_time=0.2)

            # Sorting Logic
            if category == 1:
                target_box = l_box
                target_txt = l_count_txt
                curr_count = count_left
                count_left += 1
            else:
                target_box = r_box
                target_txt = r_count_txt
                curr_count = count_right
                count_right += 1

            landing_pos = get_slot_pos(target_box.get_center(), curr_count)
            rim_target = target_box.get_top() + UP * 0.5
            path = ArcBetweenPoints(start=item.get_center(), end=rim_target, angle=-TAU / 6)

            self.play(MoveAlongPath(item, path), run_time=0.4, rate_func=rf.ease_in_quad)

            self.play(item.animate.move_to(landing_pos).scale(0.5), run_time=0.3, rate_func=rf.ease_out_back)

            collected_items_layer.add(item)

            new_val = str(count_left if category == 1 else count_right)
            self.play(
                Transform(target_txt,
                          Text(new_val, font="Montserrat", weight=BOLD, font_size=24, color=WHITE).move_to(target_txt)),
                Flash(target_box, color=target_color, line_length=0.3),
                run_time=0.2
            )

        # --- E. THE FINAL VERDICT ---
        self.wait(0.5)

        winner_text = ""
        win_color = WHITE

        if count_left > count_right:
            winner_text = f"{TITLE_LEFT} WINS!"
            win_color = C_LEFT
            win_grp = l_full_grp
            lose_grp = r_full_grp
        elif count_right > count_left:
            winner_text = f"{TITLE_RIGHT} WINS!"
            win_color = C_RIGHT
            win_grp = r_full_grp
            lose_grp = l_full_grp
        else:
            winner_text = "IT'S A TIE!"
            win_color = C_GOLD  # No error now!
            win_grp = VGroup(l_full_grp, r_full_grp)
            lose_grp = VGroup()

        self.play(
            FadeOut(spawn_arrow),
            FadeOut(title_group), FadeOut(underline),
            lose_grp.animate.set_opacity(0.3).scale(0.9),
            win_grp.animate.scale(1.2).move_to(DOWN * 1.0),
            run_time=0.8
        )

        win_lbl = Text(winner_text, font="Montserrat", weight=BOLD, font_size=60, color=win_color)
        win_lbl.move_to(UP * 2.5)
        glow = win_lbl.copy().set_color(win_color).set_opacity(0.3).set_stroke(width=8, opacity=0.3)

        self.play(
            GrowFromCenter(win_lbl),
            FadeIn(glow),
            Flash(win_lbl, color=win_color, line_length=0.5, num_lines=8),
            run_time=0.6
        )

        self.wait(3)










###  NICE DIYA HUA CODE MIEN WINNER KA ANNOUCMENT WALA ANIMATION NHI HAI


# import sys
# import os
# import pandas as pd
# import numpy as np
# import random
# from manim import *
# import manim.utils.rate_functions as rf
#
# # --- 1. PATH SETUP ---
# current_dir = os.path.dirname(os.path.abspath(__file__))
# project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
# sys.path.append(project_root)
#
# # try:
# #     from src.config import *
# #     from src.utils import *
# except ImportError:
#     DATA_DIR = os.path.join(project_root, "data")
#     ASSETS_DIR = os.path.join(project_root, "assets")


    # class Theme:
    #     NEON_BLUE = "#00F0FF"
    #     NEON_PINK = "#FF0055"


    # def get_branding_border():
    #     border = Rectangle(height=16 / 9 * 7.5, width=7.5)
    #     border.set_stroke(width=10, color=[Theme.NEON_BLUE, Theme.NEON_PINK], opacity=0.8)
    #     return border


# --- 2. DATA LOADING (UPDATED WITH REASONS) ---


# def load_data(csv_filename):
#     if not os.path.exists(csv_filename):
#         print(f"⚠️ Warning: '{csv_filename}' not found. Creating dummy data.")
#         data = {
#             'Image': ['python.jpg', 'java.jpg', 'html.jpg', 'cpp.jpg'],  # Updated extensions
#             'Category': [1, 2, 2, 1],
#             'Reason': ['AI KING', 'VERBOSE', 'NOT CODE', 'FAST AF']  # New Column
#         }
#         return pd.DataFrame(data)
#     try:
#         df = pd.read_csv(csv_filename)
#         df.columns = df.columns.str.strip()
#         # Fallback if Reason column missing
#         if 'Reason' not in df.columns:
#             df['Reason'] = ["UNKNOWN"] * len(df)
#         return df
#     except Exception as e:
#         print(f"❌ Error: {e}")
#         sys.exit(1)


# class SortCard(Scene):
#     def construct(self):
#         self.camera.background_color = "#050505"
#
#         # ==========================================
#         # 🛠️ CONFIG SECTION
#         # ==========================================
#         TITLE_LEFT = "TIER 1"
#         TITLE_RIGHT = "TIER 2"
#
#         C_LEFT = Theme.NEON_BLUE
#         C_RIGHT = Theme.NEON_PINK
#
#         # POSITIONS
#         TITLE_Y = 3.5
#         ARROW_Y = 2.5
#         SPAWN_Y = 1.8
#         BOX_Y = -2.2
#
#         LEFT_BOX_POS = [-2.2, BOX_Y, 0]
#         RIGHT_BOX_POS = [2.2, BOX_Y, 0]
#         # ==========================================
#
#         df = load_data(os.path.join(DATA_DIR, "sort_data.csv"))
#
#         # GROUPS
#         static_layer = VGroup()
#         shaft_layer = VGroup()
#         bin_back_layer = VGroup()
#         bin_back_layer.set_z_index(10)
#         collected_items_layer = Group()
#         collected_items_layer.set_z_index(50)
#         bin_front_layer = VGroup()
#         bin_front_layer.set_z_index(100)
#         ui_layer = VGroup()
#         ui_layer.set_z_index(200)
#
#         self.add(static_layer, shaft_layer, bin_back_layer, collected_items_layer, bin_front_layer, ui_layer)
#
#         # --- A. BACKGROUND ---
#         bg_grid = NumberPlane(
#             x_range=[-10, 10, 1], y_range=[-20, 20, 1],
#             background_line_style={"stroke_color": "#222", "stroke_width": 2, "stroke_opacity": 0.2},
#             axis_config={"stroke_opacity": 0}
#         )
#         static_layer.add(bg_grid)
#
#         def create_wall_lines(x_start, direction):
#             lines = VGroup()
#             for i in range(5):
#                 x = x_start + (i * 0.5 * direction)
#                 line = Line(start=DOWN * 8, end=UP * 8)
#                 line.set_stroke(color=GREY_C, width=2, opacity=0.1 + (0.1 * (5 - i)))
#                 line.move_to([x, 0, 0])
#                 lines.add(line)
#             return lines
#
#         static_layer.add(create_wall_lines(-3.5, 1), create_wall_lines(3.5, -1))
#
#         rungs = VGroup()
#         for i in range(8):
#             y = -4 + (i * 2.0)
#             rung = Line(start=LEFT * 4, end=RIGHT * 4)
#             rung.set_stroke(color=GREY_B, width=1, opacity=0.3)
#             rung.move_to([0, y, 0])
#             rungs.add(rung)
#
#         def update_rungs(mob, dt):
#             for line in mob:
#                 line.shift(UP * 2.5 * dt)
#                 if line.get_y() > 5:
#                     line.move_to([0, -5, 0])
#
#         rungs.add_updater(update_rungs)
#         shaft_layer.add(rungs)
#
#         try:
#             bb = get_branding_border()
#             bb.move_to(ORIGIN)
#             ui_layer.add(bb)
#         except:
#             pass
#
#         # --- B. HEADER (CLEAN DESIGN) ---
#         txt_left = Text(TITLE_LEFT, font="Montserrat", weight=BOLD, font_size=36, color=WHITE)
#         txt_vs = Text("vs", font="Montserrat", weight=BOLD, font_size=28, color=GREY_B)
#         txt_right = Text(TITLE_RIGHT, font="Montserrat", weight=BOLD, font_size=36, color=WHITE)
#
#         title_group = VGroup(txt_left, txt_vs, txt_right).arrange(RIGHT, buff=0.2)
#         title_group.move_to(UP * TITLE_Y)
#
#         line_width = title_group.width + 0.4
#         line_left = Line(LEFT * line_width / 2, ORIGIN).set_stroke(color=C_LEFT, width=4)
#         line_right = Line(ORIGIN, RIGHT * line_width / 2).set_stroke(color=C_RIGHT, width=4)
#         underline = VGroup(line_left, line_right).arrange(RIGHT, buff=0).next_to(title_group, DOWN, buff=0.1)
#
#         ui_layer.add(title_group, underline)
#
#         spawn_arrow = Triangle(color=GREY_A, fill_opacity=1).scale(0.2).rotate(180 * DEGREES).move_to(UP * ARROW_Y)
#         ui_layer.add(spawn_arrow)
#
#         # --- C. THE NEO-PODS ---
#         def create_neo_pod(label_text, color, pos):
#             w, h = 2.6, 2.2
#
#             # Back
#             p1 = pos + np.array([-w / 2, -h / 2, 0])
#             p2 = pos + np.array([w / 2, -h / 2, 0])
#             p3 = pos + np.array([w / 2 + 0.2, -h / 2 - 0.4, 0])
#             p4 = pos + np.array([-w / 2 - 0.2, -h / 2 - 0.4, 0])
#             base = Polygon(p1, p2, p3, p4, color=color, stroke_width=3, fill_opacity=0.3, fill_color=color)
#
#             glass_back = RoundedRectangle(width=w, height=h, corner_radius=0.1)
#             glass_back.set_stroke(width=0)
#             glass_back.set_fill(color=color, opacity=0.05)
#             glass_back.move_to(pos)
#             back_grp = VGroup(glass_back, base)
#
#             # Front
#             rim = RoundedRectangle(width=w, height=0.1, corner_radius=0.05, color=color)
#             rim.set_fill(color=color, opacity=0.9)
#             rim.move_to(pos + UP * h / 2)
#
#             glass_front = RoundedRectangle(width=w, height=h, corner_radius=0.1)
#             glass_front.set_stroke(color=color, width=2, opacity=0.5)
#             glass_front.move_to(pos)
#
#             # Label
#             label_plate = RoundedRectangle(width=1.8, height=0.4, corner_radius=0.05, color=color, stroke_width=1)
#             label_plate.set_fill(color=color, opacity=0.2)
#             label_plate.next_to(base.get_top(), DOWN, buff=0.2)
#             name_txt = Text(label_text, font="Montserrat", weight=BOLD, font_size=18, color=WHITE).move_to(label_plate)
#
#             # Counter
#             counter_bg = RoundedRectangle(width=1.0, height=0.5, corner_radius=0.1, color=color, stroke_width=2)
#             counter_bg.set_fill(color=color, opacity=0.3)
#             counter_bg.next_to(label_plate, DOWN, buff=0.1)
#             counter_txt = Text("0", font="Montserrat", weight=BOLD, font_size=24, color=WHITE).move_to(counter_bg)
#
#             front_grp = VGroup(rim, glass_front, label_plate, name_txt, counter_bg, counter_txt)
#             return back_grp, front_grp, glass_back, counter_txt
#
#         l_back, l_front, l_box, l_count_txt = create_neo_pod(TITLE_LEFT, C_LEFT, np.array(LEFT_BOX_POS))
#         bin_back_layer.add(l_back)
#         bin_front_layer.add(l_front)
#         r_back, r_front, r_box, r_count_txt = create_neo_pod(TITLE_RIGHT, C_RIGHT, np.array(RIGHT_BOX_POS))
#         bin_back_layer.add(r_back)
#         bin_front_layer.add(r_front)
#
#         # Intro
#         self.play(
#             FadeIn(static_layer), FadeIn(shaft_layer),
#             Write(title_group), Create(underline),
#             FadeIn(spawn_arrow),
#             FadeIn(bin_back_layer, shift=UP), FadeIn(bin_front_layer, shift=UP),
#             run_time=1.2
#         )
#
#         # --- D. SORTING LOOP WITH REASONING ---
#         SPAWN_POINT_VEC = UP * SPAWN_Y
#         ENTRY_POINT_VEC = UP * SPAWN_Y + RIGHT * 5.0
#
#         def get_slot_pos(box_center, index):
#             rows = [-0.6, 0.4]
#             cols = [-0.7, 0, 0.7]
#             row_idx = index // 3
#             col_idx = index % 3
#             r = rows[row_idx % 2]
#             c = cols[col_idx]
#             return box_center + np.array([c, r, 0])
#
#         count_left = 0
#         count_right = 0
#
#         for index, row in df.iterrows():
#             img_name = row['Image']
#             reason_text = str(row['Reason']).upper()  # READ REASON
#             try:
#                 category = int(row['Category'])
#             except:
#                 category = 2
#
#             # 1. SPAWN
#             img_path = os.path.join(ASSETS_DIR, "images", img_name)
#             if os.path.exists(img_path):
#                 item = ImageMobject(img_path)
#                 item.scale_to_fit_width(1.3)
#             else:
#                 item = Text("?", font_size=60, color=WHITE)
#
#             item.move_to(ENTRY_POINT_VEC)
#             item.set_z_index(50)
#
#             # Slide In
#             self.play(item.animate.move_to(SPAWN_POINT_VEC), run_time=0.4, rate_func=rf.ease_out_quad)
#
#             # --- THE REASONING PHASE (NEW) ---
#             # Determine Color
#             target_color = C_LEFT if category == 1 else C_RIGHT
#
#             # Create Reason Tag
#             reason_bg = RoundedRectangle(width=len(reason_text) * 0.3 + 0.4, height=0.6, corner_radius=0.1,
#                                          color=target_color)
#             reason_bg.set_fill(color=BLACK, opacity=0.9)
#             reason_bg.next_to(item, UP, buff=0.1)  # Show ABOVE image
#
#             reason_lbl = Text(reason_text, font="Montserrat", weight=BOLD, font_size=24, color=target_color)
#             reason_lbl.move_to(reason_bg)
#
#             reason_grp = VGroup(reason_bg, reason_lbl)
#             reason_grp.set_z_index(200)  # On top of everything
#
#             # Animate: Scan -> Show Text -> Wait -> Hide
#             scan_line = Line(LEFT * 0.7, RIGHT * 0.7, color=WHITE).next_to(item, UP, buff=0)
#
#             self.play(
#                 scan_line.animate.next_to(item, DOWN, buff=0),
#                 FadeIn(reason_grp, shift=DOWN),  # Text pops up
#                 run_time=0.3
#             )
#             scan_line.set_opacity(0)
#
#             # PAUSE FOR READING (User request)
#             self.wait(0.5)
#
#             self.play(FadeOut(reason_grp), run_time=0.2)
#             # -------------------------------
#
#             # Target & Slot
#             if category == 1:
#                 target_box = l_box
#                 target_txt = l_count_txt
#                 curr_count = count_left
#                 count_left += 1
#             else:
#                 target_box = r_box
#                 target_txt = r_count_txt
#                 curr_count = count_right
#                 count_right += 1
#
#             landing_pos = get_slot_pos(target_box.get_center(), curr_count)
#             rim_target = target_box.get_top() + UP * 0.5
#             path = ArcBetweenPoints(start=item.get_center(), end=rim_target, angle=-TAU / 6)
#
#             # Move to Rim
#             self.play(
#                 MoveAlongPath(item, path),
#                 run_time=0.4, rate_func=rf.ease_in_quad
#             )
#
#             # Drop & Shrink
#             self.play(
#                 item.animate.move_to(landing_pos).scale(0.5),
#                 run_time=0.3,
#                 rate_func=rf.ease_out_back
#             )
#
#             collected_items_layer.add(item)
#
#             # Update Counter
#             new_val = str(count_left if category == 1 else count_right)
#             self.play(
#                 Transform(target_txt,
#                           Text(new_val, font="Montserrat", weight=BOLD, font_size=24, color=WHITE).move_to(target_txt)),
#                 Flash(target_box, color=target_color, line_length=0.3),
#                 run_time=0.2
#             )
#
#         self.wait(2)

