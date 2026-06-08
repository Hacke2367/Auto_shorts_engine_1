# # bar_chart/bar_chart.py  (FINAL + AUDIO-SYNC READY)
# # - job.json timeline (Option A) supported
# # - main reveal fast; leftover time -> alive holds (no boring freezes)
#
# import sys
# import os
# import re
# import numpy as np
# import pandas as pd
# from manim import *
# from manim import rate_functions as rf
#
# # --- PATH SETUP ---
# current_dir = os.path.dirname(os.path.abspath(__file__))
# project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
# sys.path.append(project_root)
#
# # --- IMPORTS (Robust) ---
# try:
#     from src.config import Theme, BACKGROUND_COLOR, DATA_DIR
#     from src.utils import (
#         IntroManager,
#         get_safe_frame,
#         clamp_x,
#         clamp_y,
#         make_floating_particles,
#         Brand,
#     )
# except Exception:
#     BACKGROUND_COLOR = "#050505"
#     DATA_DIR = os.path.join(project_root, "data")
#
#     class Theme:
#         NEON_BLUE = "#00F0FF"
#         NEON_PINK = "#FF0055"
#         NEON_PURPLE = "#BD00FF"
#         NEON_GREEN = "#00FF66"
#         TEXT_MAIN = "#FFFFFF"
#         TEXT_SUB = "#B8B8B8"
#         AXIS_COLOR = "#00F0FF"
#         C_BAR_GRADIENT = ["#0033CC", "#0088FF", "#00FFFF"]
#
#     config.frame_height = 16.0
#     config.frame_width = 9.0
#
#     class Brand:
#         CYAN = "#00F0FF"
#         PINK = "#FF0055"
#         GREEN = "#00FF66"
#         WHITE = "#FFFFFF"
#         TEXT_MAIN = "#FFFFFF"
#         TEXT_SUB = "#B8B8B8"
#
#     def get_safe_frame(margin=0.60):
#         half_w = config.frame_width / 2
#         half_h = config.frame_height / 2
#         return {
#             "left": -half_w + margin,
#             "right": half_w - margin,
#             "top": half_h - margin,
#             "bottom": -half_h + margin,
#             "w": config.frame_width - (2 * margin),
#             "h": config.frame_height - (2 * margin),
#             "cx": 0.0,
#             "cy": 0.0,
#         }
#
#     def clamp_x(x, mob_width=0.0, margin=0.60):
#         sf = get_safe_frame(margin)
#         half = float(mob_width) / 2
#         return float(np.clip(x, sf["left"] + half, sf["right"] - half))
#
#     def clamp_y(y, mob_height=0.0, margin=0.60):
#         sf = get_safe_frame(margin)
#         half = float(mob_height) / 2
#         return float(np.clip(y, sf["bottom"] + half, sf["top"] - half))
#
#     def make_floating_particles(*args, **kwargs):
#         return VGroup()
#
# # --- SYNC HELPERS (new) ---
# from src.sync.job import load_job
# from src.sync.timeline import Timeline, clamp
# from src.sync.retention import hold_breathing, banner_scan_hold
#
# # ============================================================
# # CSV loader with optional META line
# # ============================================================
# _META_RE = re.compile(r"([A-Za-z_]+)\s*=\s*([^,]+)")
#
# def load_ai_stats_csv(csv_path: str):
#     meta = {}
#
#     if not os.path.exists(csv_path):
#         names = ["Nvidia", "Microsoft", "Apple", "Google", "Amazon"]
#         values = [95, 88, 82, 76, 70]
#         return meta, names, values, 100.0
#
#     with open(csv_path, "r", encoding="utf-8-sig") as f:
#         first = (f.readline() or "").strip()
#
#     skip_first = False
#     if first.startswith("#"):
#         skip_first = True
#         meta_line = first[1:].strip()
#         for m in _META_RE.finditer(meta_line):
#             meta[m.group(1).strip().upper()] = m.group(2).strip()
#
#     df = pd.read_csv(csv_path, encoding="utf-8-sig", skiprows=1 if skip_first else 0)
#     df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
#
#     name_col = "Name" if "Name" in df.columns else ("Label" if "Label" in df.columns else None)
#     if name_col is None or "Value" not in df.columns:
#         raise ValueError(f"ai_stats.csv must have columns: Name(or Label), Value. Found: {df.columns.tolist()}")
#
#     df[name_col] = df[name_col].astype(str).fillna("").str.strip()
#     df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0.0)
#     df = df[df[name_col] != ""].copy()
#
#     sort_mode = (meta.get("SORT", "DESC") or "DESC").strip().upper()
#     if sort_mode == "ASC":
#         df = df.sort_values("Value", ascending=True)
#     elif sort_mode == "NONE":
#         pass
#     else:
#         df = df.sort_values("Value", ascending=False)
#
#     try:
#         top_n = int(float(meta.get("TOP_N", "0")))
#     except Exception:
#         top_n = 0
#     if top_n and top_n > 0:
#         df = df.head(top_n)
#
#     names = df[name_col].tolist()
#     values = df["Value"].astype(float).tolist()
#
#     try:
#         max_val = float(meta.get("MAX", "100"))
#         if max_val <= 0:
#             max_val = 100.0
#     except Exception:
#         max_val = 100.0
#
#     return meta, names, values, max_val
#
#
# class BarChartTemplate(Scene):
#     def construct(self):
#         self.camera.background_color = BACKGROUND_COLOR
#
#         # ============================================================
#         # ✅ 0) JOB + TIMELINE (Option A)
#         # job.json -> timeline dict:
#         # { "hook":2.6, "setup":1.3, "item_1":2.0, ..., "winner":3.4, "outro":1.2 }
#         # ============================================================
#         job = load_job(default={"template_id": "bar_chart", "timeline": {}})
#
#         job_json_path = os.environ.get("JOB_JSON_PATH", "")
#         job_dir = os.path.dirname(job_json_path) if job_json_path else project_root
#
#         timeline_dict = job.get("timeline", {}) if isinstance(job.get("timeline", {}), dict) else {}
#
#         csv_path = job.get("data_csv") or "data/ai_stats.csv"
#         if not os.path.isabs(csv_path):
#             csv_path = os.path.join(job_dir, csv_path)
#
#         meta, names, values, max_val = load_ai_stats_csv(csv_path)
#
#         if not names:
#             names = ["Nvidia", "Microsoft", "Apple", "Google", "Amazon"]
#             values = [95, 88, 82, 76, 70]
#             max_val = 100.0
#
#         values = [float(v) for v in values]
#         max_val = float(max_val)
#
#         # Optional: enforce sort safety (only if SORT != NONE)
#         sort_mode = (meta.get("SORT", "DESC") or "DESC").strip().upper()
#         if sort_mode != "NONE":
#             reverse = (sort_mode != "ASC")
#             rows = sorted(list(zip(names, values)), key=lambda x: float(x[1]), reverse=reverse)
#             names = [r[0] for r in rows]
#             values = [float(r[1]) for r in rows]
#
#         num_items = len(names)
#
#         # Defaults (if timeline missing)
#         defaults = {"hook": 2.6, "setup": 1.3, "winner": 3.2, "outro": 1.2}
#         for i in range(1, num_items + 1):
#             defaults[f"item_{i}"] = 2.0
#         TL = Timeline.from_dict(timeline_dict, defaults=defaults)
#
#         # ============================================================
#         # 1) INTRO
#         # ============================================================
#         try:
#             IntroManager.play_intro(
#                 self,
#                 brand_title="BIGDATA LEAK",
#                 brand_sub="> system breach detected",
#                 feed_text="FEED_BAR // MARKET",
#                 footer_text="CONFIDENTIAL // LEAKED_SOURCE",
#             )
#         except Exception as e:
#             print(f"Intro Error: {e}")
#
#         # ============================================================
#         # 2) SAFE FRAME
#         # ============================================================
#         sf = get_safe_frame(margin=0.70)
#
#         # ============================================================
#         # 3) ATMOSPHERE
#         # ============================================================
#         grid = NumberPlane(
#             x_range=(-10, 10, 1),
#             y_range=(-20, 20, 1),
#             background_line_style={
#                 "stroke_color": Theme.NEON_BLUE,
#                 "stroke_width": 1,
#                 "stroke_opacity": 0.06,
#             },
#             axis_config={"stroke_width": 0},
#         )
#         self.add(grid)
#
#         try:
#             particles = make_floating_particles(
#                 n=26,
#                 color=Theme.NEON_BLUE,
#                 radius_range=(0.02, 0.05),
#                 opacity_range=(0.10, 0.25),
#                 drift=0.05,
#                 margin=0.75,
#             )
#             self.add(particles)
#         except:
#             pass
#
#         # ============================================================
#         # 5) HEADER (hook segment)
#         # ============================================================
#         title_text = (meta.get("TITLE", "MARKET LEADERS") or "MARKET LEADERS").strip()
#         sub_text = (meta.get("SUB", "Tech leaders comparison") or "Tech leaders comparison").strip()
#
#         title = Text(title_text, font="Montserrat", weight=BOLD, font_size=52, color=Theme.TEXT_MAIN)
#         title.move_to([sf["cx"], sf["top"] - 1.05, 0])
#
#         underline = Line(LEFT * 2.8, RIGHT * 2.8)
#         underline.set_stroke(width=4, color=[Theme.NEON_PINK, Theme.NEON_BLUE])
#         underline.next_to(title, DOWN, buff=0.18)
#
#         scanner_dot = Dot(color=WHITE, radius=0.07)
#         scanner_dot.move_to(underline.get_left())
#         scanner_dot.set_z_index(50)
#
#         def _scan(m, dt):
#             t = (np.sin(self.time * 2.0) + 1) / 2
#             m.move_to(underline.get_left() + (underline.get_right() - underline.get_left()) * t)
#
#         scanner_dot.add_updater(_scan)
#
#         subtitle = Text(sub_text, font="Montserrat", font_size=22, color=Theme.TEXT_SUB)
#         subtitle.next_to(underline, DOWN, buff=0.25)
#
#         hook_total = TL.seg_total("hook", 2.6)
#         # action part ko premium range me rakho, leftover hold banega
#         hook_action = clamp(hook_total * 0.70, 1.2, 2.2)
#         scale = hook_action / 2.5
#
#         rt_title = clamp(0.7 * scale, 0.35, 0.85)
#         rt_line = clamp(0.7 * scale, 0.35, 0.85)
#         rt_dot = clamp(0.3 * scale, 0.18, 0.35)
#         rt_sub = clamp(0.8 * scale, 0.40, 0.95)
#
#         self.play(
#             Write(title, run_time=rt_title),
#             GrowFromCenter(underline, run_time=rt_line),
#             FadeIn(scanner_dot, run_time=rt_dot),
#             FadeIn(subtitle, shift=UP * 0.2, run_time=rt_sub),
#         )
#         TL.consume("hook", hook_action)
#
#         # ✅ leftover time (hook) -> alive hold
#         hold_breathing(self, TL.remaining("hook"), focus=underline)
#
#         # ============================================================
#         # 6) LAYOUT
#         # ============================================================
#         top_y = sf["top"] - 3.2
#         bottom_y = sf["bottom"] + 2.1
#         available_h = top_y - bottom_y
#         GAP_Y = min(1.75, available_h / (num_items + 0.2))
#         START_Y = top_y
#
#         RAIL_X = sf["left"] + 0.55
#         RANK_X = RAIL_X + 0.60
#         LABEL_X = RANK_X + 1.10
#         BAR_START_X = LABEL_X + 1.10
#
#         VALUE_GUTTER_W = 0.95
#         BAR_RIGHT_LIMIT = sf["right"] - VALUE_GUTTER_W
#         BAR_MAX_WIDTH = BAR_RIGHT_LIMIT - BAR_START_X
#         VALUE_ANCHOR_X = sf["right"] - 0.30
#         BAR_HEIGHT = 0.62
#
#         # ============================================================
#         # SETUP segment (rail + guides)
#         # ============================================================
#         rail_top = START_Y + 0.55
#         rail_bottom = START_Y - (num_items - 1) * GAP_Y - 0.55
#
#         rail = Line([RAIL_X, rail_top, 0], [RAIL_X, rail_bottom, 0]).set_stroke(
#             color=Theme.NEON_BLUE, width=3, opacity=0.35
#         )
#         rail.set_z_index(20)
#
#         rail_glow = rail.copy().set_stroke(color=WHITE, width=10, opacity=0.06)
#         rail_glow.set_z_index(19)
#
#         rail_label = Text("RANK", font="Montserrat", weight=BOLD, font_size=16, color=Theme.NEON_PINK)
#         rail_label.rotate(90 * DEGREES)
#         rail_label.move_to([RAIL_X - 0.35, (rail_top + rail_bottom) / 2, 0])
#         rail_label.set_opacity(0.85)
#         rail_label.set_z_index(25)
#
#         rail_scanner = Dot(color=WHITE, radius=0.06).move_to([RAIL_X, rail_top, 0])
#         rail_scanner.set_z_index(30)
#
#         def _rail_scan(m, dt):
#             speed = 0.9
#             y = rail_top - (self.time * speed) % max(0.001, (rail_top - rail_bottom))
#             m.move_to([RAIL_X, y, 0])
#
#         rail_scanner.add_updater(_rail_scan)
#
#         setup_total = TL.seg_total("setup", 1.3)
#         setup_action = clamp(setup_total * 0.75, 0.9, 1.6)
#
#         self.play(FadeIn(rail_glow), Create(rail), FadeIn(rail_label), FadeIn(rail_scanner),
#                   run_time=clamp(setup_action * 0.55, 0.35, 0.75))
#
#         milestones = [0, 25, 50, 75, 100]
#         guide_group = VGroup()
#         for m in milestones:
#             x_pos = BAR_START_X + (m / 100) * BAR_MAX_WIDTH
#             v_line = DashedLine(
#                 start=[x_pos, START_Y + 0.75, 0],
#                 end=[x_pos, rail_bottom - 0.25, 0],
#                 dash_length=0.18,
#                 dashed_ratio=0.6,
#             ).set_stroke(Theme.NEON_BLUE, width=2, opacity=0.12)
#
#             label = Text(str(m), font="Arial", font_size=14, color=Theme.TEXT_SUB)
#             label.move_to([x_pos, rail_bottom - 0.55, 0])
#             guide_group.add(v_line, label)
#
#         self.play(Create(guide_group, run_time=clamp(setup_action * 0.75, 0.55, 1.05), lag_ratio=0.08))
#
#         TL.consume("setup", setup_action)
#         hold_breathing(self, TL.remaining("setup"), focus=rail)
#
#         # ============================================================
#         # 7) BAR ENGINE (item_1 ... item_n)
#         # ============================================================
#         bar_groups = []
#
#         for i, (name, value) in enumerate(zip(names, values)):
#             seg = f"item_{i+1}"
#             item_total = TL.seg_total(seg, 2.0)
#
#             y_pos = START_Y - (i * GAP_Y)
#             denom = max(1e-6, float(max_val))
#             target_width = (float(value) / denom) * BAR_MAX_WIDTH
#
#             branch = Line([RAIL_X, y_pos, 0], [RANK_X - 0.18, y_pos, 0]).set_stroke(
#                 color=Theme.NEON_BLUE, width=2, opacity=0.25
#             )
#             bolt = Dot(color=WHITE, radius=0.035).move_to(branch.get_start())
#             bolt.set_opacity(0.6)
#
#             rank_bg = Circle(radius=0.25, color="#0B0B0B", fill_opacity=1).set_stroke(
#                 Theme.NEON_BLUE, width=2, opacity=0.7
#             ).move_to([RANK_X, y_pos, 0])
#             rank_num = Text(f"{i + 1}", font="Montserrat", weight=BOLD, font_size=20, color=WHITE).move_to(rank_bg)
#
#             name_text = Text(str(name).upper(), font="Montserrat", weight=BOLD, font_size=24, color=WHITE)
#             text_plate = RoundedRectangle(corner_radius=0.12, width=name_text.width + 0.55, height=0.52)
#             text_plate.set_fill(color="#000000", opacity=0.70).set_stroke(width=0)
#             text_plate.move_to([LABEL_X, y_pos + 0.45, 0])
#             name_text.move_to(text_plate)
#
#             text_plate.move_to(
#                 [clamp_x(text_plate.get_x(), text_plate.width, 0.70),
#                  clamp_y(text_plate.get_y(), text_plate.height, 0.70), 0]
#             )
#             name_text.move_to(text_plate)
#             label_group = VGroup(text_plate, name_text)
#
#             # ✅ item segment split: label + tracker + morph (premium range)
#             t_label = clamp(item_total * 0.22, 0.30, 0.55)
#             t_track = clamp(item_total * 0.56, 0.95, 1.60)
#             t_morph = clamp(item_total * 0.22, 0.35, 0.55)
#
#             # keep sum <= item_total (tracker compress first)
#             s = t_label + t_track + t_morph
#             if s > item_total:
#                 overflow = s - item_total
#                 t_track = max(0.75, t_track - overflow)
#
#             self.play(
#                 FadeIn(branch, run_time=t_label),
#                 FadeIn(bolt, run_time=t_label),
#                 FadeIn(rank_bg, shift=RIGHT * 0.15, run_time=t_label),
#                 FadeIn(rank_num, shift=RIGHT * 0.15, run_time=t_label),
#                 FadeIn(label_group, shift=RIGHT * 0.15, run_time=t_label),
#             )
#             TL.consume(seg, t_label)
#
#             container = RoundedRectangle(corner_radius=0.12, width=BAR_MAX_WIDTH + 0.20, height=BAR_HEIGHT)
#             container.set_stroke(Theme.NEON_BLUE, width=2, opacity=0.35)
#             container.set_fill("#060606", opacity=0.85)
#             container.move_to([BAR_START_X + BAR_MAX_WIDTH / 2, y_pos, 0])
#             self.add(container)
#
#             # DOTS + LINE run
#             num_dots = 12
#             dot_positions = []
#             dots_group = VGroup()
#
#             for k in range(num_dots):
#                 t = k / (num_dots - 1)
#                 x = BAR_START_X + t * target_width
#                 y_offset = 0.14 if k % 2 else -0.14
#                 if k == 0 or k == num_dots - 1:
#                     y_offset = 0
#                 pos = np.array([x, y_pos + y_offset, 0])
#                 dot_positions.append(pos)
#
#                 d = Dot(radius=0.055, color="#3A3A3A")
#                 d.active_color = WHITE
#                 d.move_to(pos)
#                 ring = Circle(radius=0.10, color=Theme.NEON_BLUE, stroke_width=1.4).set_opacity(0.25)
#                 ring.move_to(pos)
#                 dots_group.add(d, ring)
#
#             self.add(dots_group)
#
#             zig_line = VMobject().set_stroke(color=WHITE, width=3, opacity=0.9)
#             zig_glow = VMobject().set_stroke(color=Theme.NEON_BLUE, width=10, opacity=0.22)
#             spark = Dot(radius=0.11, color=WHITE).set_opacity(0.9)
#             line_group = VGroup(zig_glow, zig_line, spark)
#             self.add(line_group)
#
#             final_bar = RoundedRectangle(corner_radius=0.10, width=max(0.10, target_width), height=BAR_HEIGHT - 0.16)
#             final_bar.set_stroke(width=0)
#             final_bar.set_fill(
#                 color=Theme.C_BAR_GRADIENT if hasattr(Theme, "C_BAR_GRADIENT") else [Theme.NEON_BLUE, Theme.NEON_PINK],
#                 opacity=1,
#             )
#             final_bar.align_to(container, LEFT).shift(RIGHT * 0.10).set_y(y_pos).set_opacity(0)
#
#             sheen = RoundedRectangle(corner_radius=0.10, width=max(0.10, target_width), height=(BAR_HEIGHT - 0.16) / 2)
#             sheen.set_stroke(width=0).set_fill(color=WHITE, opacity=0.18)
#             sheen.align_to(final_bar, UP).align_to(final_bar, LEFT).set_opacity(0)
#
#             val_num = DecimalNumber(0, num_decimal_places=0, font_size=24, color=Theme.NEON_BLUE)
#             val_num.set_z_index(60)
#             self.add(val_num)
#
#             val_pill = RoundedRectangle(corner_radius=0.12, width=1.15, height=0.46)
#             val_pill.set_fill(color=BLACK, opacity=0.55).set_stroke(width=0)
#             val_pill.set_z_index(55)
#             self.add(val_pill)
#
#             tracker = ValueTracker(0)
#             flashed_indices = set()
#
#             def update_single_bar(_):
#                 t = tracker.get_value()
#                 val_num.set_value(t * float(value))
#
#                 x = VALUE_ANCHOR_X - (val_num.width / 2)
#                 x = clamp_x(x, val_num.width, 0.70)
#                 val_num.move_to([x, y_pos, 0])
#
#                 pill_w = max(1.10, val_num.width + 0.35)
#                 val_pill.become(
#                     RoundedRectangle(corner_radius=0.12, width=pill_w, height=0.46)
#                     .set_fill(color=BLACK, opacity=0.55)
#                     .set_stroke(width=0)
#                 )
#                 val_pill.set_z_index(55)
#                 val_pill.move_to(val_num)
#
#                 total_segments = num_dots - 1
#                 exact_pos = t * total_segments
#                 current_idx = int(exact_pos)
#                 remainder = exact_pos - current_idx
#                 if current_idx >= total_segments:
#                     current_idx = total_segments - 1
#                     remainder = 1.0
#
#                 p1 = dot_positions[current_idx]
#                 p2 = dot_positions[current_idx + 1]
#                 current_tip = p1 + (p2 - p1) * remainder
#                 spark.move_to(current_tip)
#
#                 points = [dot_positions[0]]
#                 for kk in range(1, current_idx + 1):
#                     points.append(dot_positions[kk])
#                     points.append(dot_positions[kk])
#                 points.append(current_tip)
#
#                 zig_line.set_points_as_corners(points)
#                 zig_glow.set_points_as_corners(points)
#
#                 if current_idx not in flashed_indices and remainder > 0.12:
#                     flashed_indices.add(current_idx)
#                     real_idx = current_idx * 2
#                     dot_obj = dots_group[real_idx]
#                     ring_obj = dots_group[real_idx + 1]
#                     dot_obj.set_color(dot_obj.active_color)
#                     ring_obj.set_stroke(opacity=0.9).set_stroke(width=2)
#
#             line_group.add_updater(update_single_bar)
#
#             self.play(tracker.animate.set_value(1.0), run_time=t_track, rate_func=linear)
#             TL.consume(seg, t_track)
#
#             line_group.remove_updater(update_single_bar)
#
#             temp_straight = Line(dot_positions[0], dot_positions[-1], color=WHITE, stroke_width=4)
#             self.add(temp_straight)
#             self.remove(line_group, dots_group)
#
#             final_bar.set_opacity(1)
#             sheen.set_opacity(1)
#
#             shockwave = Circle(radius=0.08, color=WHITE, stroke_width=4).move_to(final_bar.get_right())
#             self.play(
#                 ReplacementTransform(temp_straight, final_bar),
#                 FadeIn(sheen, run_time=min(0.18, t_morph * 0.35)),
#                 Flash(final_bar.get_right(), color=WHITE, line_length=0.9, flash_radius=0.45),
#                 shockwave.animate.scale(6).set_opacity(0),
#                 run_time=t_morph,
#                 rate_func=rf.ease_out_back,
#             )
#             self.remove(shockwave)
#             TL.consume(seg, t_morph)
#
#             # ✅ leftover in item_k -> alive hold on the bar
#             hold_breathing(self, TL.remaining(seg), focus=final_bar)
#
#             bar_groups.append(
#                 VGroup(branch, bolt, rank_bg, rank_num, label_group, container, final_bar, sheen, val_pill, val_num)
#             )
#
#         # ============================================================
#         # 8) WINNER REVEAL (winner segment + outro segment)
#         # ============================================================
#         winner_seg = "winner"
#         winner_total = TL.seg_total(winner_seg, 3.2)
#
#         if bar_groups:
#             winner_index = int(np.argmax(values)) if values else 0
#             winner_index = int(np.clip(winner_index, 0, max(0, len(bar_groups) - 1)))
#
#             winner = bar_groups[winner_index]
#             others = [g for j, g in enumerate(bar_groups) if j != winner_index]
#
#             t_dim = clamp(winner_total * 0.12, 0.25, 0.45)
#             self.play(*[g.animate.set_opacity(0.25) for g in others], run_time=t_dim)
#             TL.consume(winner_seg, t_dim)
#
#             winner_bar = winner[6]
#             winner_val = winner[9]
#             winner_label = winner[4]
#
#             banner_h = 1.65
#             banner = RoundedRectangle(width=sf["w"], height=banner_h, corner_radius=0.18)
#             banner.set_fill(color="#000000", opacity=0.85)
#             banner.set_stroke(color=Theme.NEON_PINK, width=3, opacity=0.8)
#             banner.move_to([sf["cx"], sf["bottom"] + (banner_h / 2) + 0.35, 0])
#             banner.set_z_index(200)
#
#             win_name = str(names[winner_index]).upper()
#             win_val = float(values[winner_index])
#
#             t1 = Text("TOP LEADER", font="Montserrat", weight=BOLD, font_size=22, color=Theme.TEXT_SUB)
#             t2 = Text(win_name, font="Montserrat", weight=BOLD, font_size=46, color=Theme.TEXT_MAIN)
#             t3 = Text(f"SCORE: {int(round(win_val))}", font="Montserrat", weight=BOLD, font_size=22, color=Theme.NEON_BLUE)
#             txt = VGroup(t1, t2, t3).arrange(DOWN, buff=0.12).move_to(banner)
#             txt.set_z_index(201)
#
#             dimmer = Rectangle(width=60, height=60).set_fill(color=BLACK, opacity=0.25).set_stroke(width=0)
#             dimmer.set_z_index(180)
#             self.add(dimmer)
#
#             t_focus = clamp(winner_total * 0.22, 0.35, 0.60)
#             self.play(
#                 winner.animate.set_opacity(1.0),
#                 winner_bar.animate.scale(1.05),
#                 winner_val.animate.set_color(WHITE),
#                 Indicate(winner_label, color=WHITE, scale_factor=1.02),
#                 run_time=t_focus,
#                 rate_func=rf.ease_out_back,
#             )
#             TL.consume(winner_seg, t_focus)
#
#             t_banner = clamp(winner_total * 0.28, 0.45, 0.85)
#             self.play(GrowFromCenter(banner), FadeIn(txt, shift=UP * 0.2),
#                       run_time=t_banner, rate_func=rf.ease_out_cubic)
#             TL.consume(winner_seg, t_banner)
#
#             t_flash = clamp(winner_total * 0.14, 0.25, 0.40)
#             self.play(
#                 Flash(banner.get_top(), color=WHITE, line_length=0.6, num_lines=10),
#                 Flash(winner_bar.get_right(), color=Theme.NEON_BLUE, line_length=0.6, num_lines=8),
#                 run_time=t_flash,
#             )
#             TL.consume(winner_seg, t_flash)
#
#             # ✅ leftover in winner -> banner scan hold
#             banner_scan_hold(self, banner, TL.remaining(winner_seg), color=WHITE)
#
#         # OUTRO segment
#         outro_total = TL.seg_total("outro", 1.2)
#         try:
#             banner_scan_hold(self, banner, outro_total, color=WHITE)
#         except Exception:
#             hold_breathing(self, outro_total, focus=underline)

## -- YAAD TAKHO UPAR DIYA HU CODE SHI HAI, NICHE DIYE HUE CODE MEIN KHUCBU MUCHU HOGYA HAI.

# bar_chart/bar_chart.py  (GOD TIER POLISH + AUDIO-SYNC READY)
# - job.json timeline (Option A) supported
# - main reveal fast; leftover time -> alive holds (no boring freezes)
# - premium micro-polish: vignette + subtle flicker, glow consistency, value settle tick,
#   winner sweep, outro top3 pulse (does NOT break sync logic)

import sys
import os
import re
import json
from pathlib import Path
import numpy as np
import pandas as pd
from manim import *
from manim import rate_functions as rf

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

# --- IMPORTS (Robust) ---
try:
    from src.config import Theme, BACKGROUND_COLOR, DATA_DIR
    from src.utils import (
        IntroManager,
        get_safe_frame,
        clamp_x,
        clamp_y,
        make_floating_particles,
        add_cinematic_background,
        Brand,
    )
except Exception:
    BACKGROUND_COLOR = "#050505"
    DATA_DIR = os.path.join(project_root, "data")

    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_GREEN = "#00FF66"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"
        AXIS_COLOR = "#00F0FF"
        C_BAR_GRADIENT = ["#0033CC", "#0088FF", "#00FFFF"]

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

    def add_cinematic_background(*args, **kwargs):
        return None

# --- SYNC HELPERS ---
from src.sync.job import load_job
from src.sync.timeline import Timeline, clamp
from src.sfx.engine import SFXEngine
try:
    from src.sync.retention import hold_breathing, banner_scan_hold, register_template_accent
    from src.sync.retention_accents import retain_accent_bar_chart
except Exception:
    def hold_breathing(scene, seconds: float, focus=None, text: str = ""):
        if seconds > 0:
            scene.wait(seconds)
    def banner_scan_hold(scene, banner, seconds: float, color=None):
        if seconds > 0:
            scene.wait(seconds)
    def register_template_accent(scene, fn):
        pass
    def retain_accent_bar_chart(scene, focus, seconds, **kw):
        return lambda: None

# ============================================================
# CSV loader with optional META line
# ============================================================
_META_RE = re.compile(r"([A-Za-z_]+)\s*=\s*([^,]+)")

def load_ai_stats_csv(csv_path: str):
    meta = {}

    if not os.path.exists(csv_path):
        names = ["Nvidia", "Microsoft", "Apple", "Google", "Amazon"]
        values = [95, 88, 82, 76, 70]
        return meta, names, values, 100.0

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        first = (f.readline() or "").strip()

    skip_first = False
    if first.startswith("#"):
        skip_first = True
        meta_line = first[1:].strip()
        for m in _META_RE.finditer(meta_line):
            meta[m.group(1).strip().upper()] = m.group(2).strip()

    df = pd.read_csv(csv_path, encoding="utf-8-sig", skiprows=1 if skip_first else 0)
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]

    name_col = "Name" if "Name" in df.columns else ("Label" if "Label" in df.columns else None)
    if name_col is None or "Value" not in df.columns:
        raise ValueError(f"ai_stats.csv must have columns: Name(or Label), Value. Found: {df.columns.tolist()}")

    df[name_col] = df[name_col].astype(str).fillna("").str.strip()
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0.0)
    df = df[df[name_col] != ""].copy()

    sort_mode = (meta.get("SORT", "DESC") or "DESC").strip().upper()
    if sort_mode == "ASC":
        df = df.sort_values("Value", ascending=True)
    elif sort_mode == "NONE":
        pass
    else:
        df = df.sort_values("Value", ascending=False)

    try:
        top_n = int(float(meta.get("TOP_N", "0")))
    except Exception:
        top_n = 0
    if top_n and top_n > 0:
        df = df.head(top_n)

    names = df[name_col].tolist()
    values = df["Value"].astype(float).tolist()

    try:
        max_val = float(meta.get("MAX", "100"))
        if max_val <= 0:
            max_val = 100.0
    except Exception:
        max_val = 100.0

    return meta, names, values, max_val


# ============================================================
# GOD-TIER VISUAL HELPERS (SAFE)
# ============================================================
def _add_soft_vignette(scene: Scene, sf: dict):
    pad = 0.35
    top = Rectangle(width=sf["w"] + 4, height=2.8).set_fill(BLACK, 0.16).set_stroke(width=0)
    bot = Rectangle(width=sf["w"] + 4, height=3.2).set_fill(BLACK, 0.20).set_stroke(width=0)
    left = Rectangle(width=2.2, height=sf["h"] + 6).set_fill(BLACK, 0.14).set_stroke(width=0)
    right = Rectangle(width=2.2, height=sf["h"] + 6).set_fill(BLACK, 0.14).set_stroke(width=0)

    top.move_to([sf["cx"], sf["top"] + 1.0 - pad, 0]).set_z_index(5)
    bot.move_to([sf["cx"], sf["bottom"] - 1.2 + pad, 0]).set_z_index(5)
    left.move_to([sf["left"] - 1.1 + pad, sf["cy"], 0]).set_z_index(5)
    right.move_to([sf["right"] + 1.1 - pad, sf["cy"], 0]).set_z_index(5)

    vignette = VGroup(top, bot, left, right)
    scene.add(vignette)
    return vignette


def _add_subtle_flicker(scene: Scene, sf: dict):
    film = Rectangle(width=sf["w"] + 6, height=sf["h"] + 6).set_fill(BLACK, 0.03).set_stroke(width=0)
    film.move_to([sf["cx"], sf["cy"], 0]).set_z_index(6)

    def _upd(m, dt):
        t = scene.time
        wob = 0.02 + 0.012 * np.sin(t * 3.3) + 0.006 * np.sin(t * 7.9)
        m.set_fill(opacity=float(np.clip(wob, 0.012, 0.045)))

    film.add_updater(_upd)
    scene.add(film)
    return film


def _soft_shadow_text(txt: Text, shift=DOWN * 0.06 + RIGHT * 0.04, opacity=0.25):
    shadow = txt.copy()
    shadow.set_color(BLACK)
    shadow.set_opacity(opacity)
    shadow.shift(shift)
    shadow.set_z_index(txt.z_index - 1 if hasattr(txt, "z_index") else 0)
    return shadow


def _micro_settle(scene: Scene, mobs: list, rt: float):
    if rt <= 0.01 or not mobs:
        return
    up = min(0.08, rt * 0.6)
    down = max(0.02, rt - up)
    scene.play(*[m.animate.scale(1.02) for m in mobs], run_time=up, rate_func=rf.ease_out_cubic)
    scene.play(*[m.animate.scale(1 / 1.02) for m in mobs], run_time=down, rate_func=rf.ease_in_cubic)


def _winner_sweep(scene: Scene, bar: Mobject, rt: float, color_core=WHITE, color_glow=None):
    if rt <= 0.01:
        return
    if color_glow is None:
        color_glow = Theme.NEON_BLUE if hasattr(Theme, "NEON_BLUE") else WHITE

    xL = bar.get_left()[0]
    xR = bar.get_right()[0]
    y0 = bar.get_bottom()[1] + 0.02
    y1 = bar.get_top()[1] - 0.02

    glow = Line([xL, y0, 0], [xL, y1, 0]).set_stroke(color_glow, width=18, opacity=0.18)
    core = Line([xL, y0, 0], [xL, y1, 0]).set_stroke(color_core, width=6, opacity=0.55)
    sweep = VGroup(glow, core).set_z_index(220)

    scene.add(sweep)
    scene.play(sweep.animate.shift(RIGHT * (xR - xL)), run_time=rt, rate_func=rf.linear)
    scene.remove(sweep)


class BarChartTemplate(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        add_cinematic_background(self, accent=Brand.CYAN)

        # ============================================================
        # ✅ 0) JOB + TIMELINE
        # ============================================================
        job = load_job(default={"template_id": "bar_chart", "timeline": {}})

        job_json_path = os.environ.get("JOB_JSON_PATH", "")
        job_dir_env = os.environ.get("JOB_DIR", "")
        job_dir = job_dir_env or (os.path.dirname(job_json_path) if job_json_path else project_root)

        timeline_dict = job.get("timeline", {}) if isinstance(job.get("timeline", {}), dict) else {}

        sfx = SFXEngine(self, job_dir)

        # CSV resolve (job relative to job_dir)
        csv_path = job.get("data_csv") or "data/ai_stats.csv"
        if not os.path.isabs(csv_path):
            csv_path = os.path.join(job_dir, csv_path)

        meta, names, values, max_val = load_ai_stats_csv(csv_path)

        if not names:
            names = ["Nvidia", "Microsoft", "Apple", "Google", "Amazon"]
            values = [95, 88, 82, 76, 70]
            max_val = 100.0

        values = [float(v) for v in values]
        max_val = float(max_val)

        sort_mode = (meta.get("SORT", "DESC") or "DESC").strip().upper()
        if sort_mode != "NONE":
            reverse = (sort_mode != "ASC")
            rows = sorted(list(zip(names, values)), key=lambda x: float(x[1]), reverse=reverse)
            names = [r[0] for r in rows]
            values = [float(r[1]) for r in rows]

        num_items = len(names)

        # Derive item_* segment names from audio.order so ghost padding covers all audio slots.
        # Falls back to num_items only if audio.order is absent (old jobs without audio block).
        _audio_cfg = job.get("audio") if isinstance(job, dict) else {}
        _audio_order = _audio_cfg.get("order", []) if isinstance(_audio_cfg, dict) else []
        _item_segs_audio = [s for s in _audio_order if isinstance(s, str) and s.startswith("item_")]

        # Hook default raised to 4.5s — IntroManager takes ~1.9s, leaving ~2.6s for
        # hook animations + retention breathing room. Real jobs use job.json timeline.
        defaults = {"hook": 4.5, "setup": 1.3, "winner": 3.2, "outro": 1.2}
        for i in range(1, num_items + 1):
            defaults[f"item_{i}"] = 2.0
        # Ensure all audio-order item segments have a default (covers extra ghost slots)
        for seg in _item_segs_audio:
            if seg not in defaults:
                defaults[seg] = 2.0
        TL = Timeline.from_dict(timeline_dict, defaults=defaults)

        # ============================================================
        # 1) INTRO
        # ============================================================
        # ✅ Phase 2 Sync Standard: The 0.0s Intro Rule
        global_start_t0 = float(self.time)

        # Register template-specific retention accent (trailing edge ghost on bars)
        register_template_accent(
            self,
            lambda s, f, t: retain_accent_bar_chart(s, f, t, bar_color=Theme.NEON_BLUE),
        )

        try:
            # (optional) intro SFX single mark at intro start
            sfx.mark("ui_pop", gain_db=-10, meta={"at": "intro_start"})
            IntroManager.play_intro(
                self,
                brand_title="BIGDATA LEAK",
                brand_sub="> system breach detected",
                feed_text="FEED_BAR // MARKET",
                footer_text="CONFIDENTIAL // LEAKED_SOURCE",
            )
        except Exception as e:
            print(f"Intro Error: {e}")

        # Measure how long the intro actually consumed so hook animations
        # are sized against the REMAINING budget, not the full budget.
        post_intro_t = float(self.time)

        # ============================================================
        # 2) SAFE FRAME
        # ============================================================
        sf = get_safe_frame(margin=0.70)

        # ============================================================
        # 3) ATMOSPHERE + GOD-TIER DEPTH
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
        grid.set_z_index(1)
        self.add(grid)

        try:
            particles = make_floating_particles(
                n=26,
                color=Theme.NEON_BLUE,
                radius_range=(0.02, 0.05),
                opacity_range=(0.10, 0.25),
                drift=0.05,
                margin=0.75,
            )
            particles.set_z_index(2)
            self.add(particles)
        except:
            pass

        _add_soft_vignette(self, sf)
        _add_subtle_flicker(self, sf)

        # ============================================================
        # 5) HEADER (hook segment)
        # ============================================================
        title_text = (meta.get("TITLE", "MARKET LEADERS") or "MARKET LEADERS").strip()
        sub_text = (meta.get("SUB", "Tech leaders comparison") or "Tech leaders comparison").strip()

        title = Text(title_text, font="Montserrat", weight=BOLD, font_size=52, color=Theme.TEXT_MAIN)
        title.move_to([sf["cx"], sf["top"] - 1.05, 0])
        title.set_z_index(60)
        title_shadow = _soft_shadow_text(title, opacity=0.28)
        title_shadow.set_z_index(59)
        self.add(title_shadow)

        underline_core = Line(LEFT * 2.8, RIGHT * 2.8)
        underline_core.set_stroke(width=4, color=[Theme.NEON_PINK, Theme.NEON_BLUE], opacity=0.95)
        underline_core.next_to(title, DOWN, buff=0.18)
        underline_core.set_z_index(60)

        underline_glow = underline_core.copy().set_stroke(color=Theme.NEON_BLUE, width=14, opacity=0.14)
        underline_glow.set_z_index(58)

        underline = VGroup(underline_glow, underline_core)

        scanner_dot = Dot(color=WHITE, radius=0.07)
        scanner_dot.move_to(underline_core.get_left())
        scanner_dot.set_z_index(80)

        def _scan(m, dt):
            t = (np.sin(self.time * 2.0) + 1) / 2
            m.move_to(underline_core.get_left() + (underline_core.get_right() - underline_core.get_left()) * t)

        scanner_dot.add_updater(_scan)

        subtitle = Text(sub_text, font="Montserrat", font_size=22, color=Theme.TEXT_SUB)
        subtitle.next_to(underline_core, DOWN, buff=0.25)
        subtitle.set_z_index(60)
        subtitle_shadow = _soft_shadow_text(subtitle, opacity=0.22)
        subtitle_shadow.set_z_index(59)
        self.add(subtitle_shadow)

        hook_total = TL.seg_total("hook", 4.5)
        # Scale animations against budget AFTER intro, not full budget.
        # This prevents the intro duration from eating into animation time
        # and leaves headroom for the retention breathing overlay.
        intro_elapsed = post_intro_t - global_start_t0
        hook_post_intro = max(0.8, hook_total - intro_elapsed)
        hook_action = clamp(hook_post_intro * 0.70, 0.8, 2.2)
        scale = hook_action / 2.5
        
        hook_t0 = global_start_t0

        rt_title = clamp(0.7 * scale, 0.35, 0.85)
        rt_line = clamp(0.7 * scale, 0.35, 0.85)
        rt_dot = clamp(0.3 * scale, 0.18, 0.35)
        rt_sub = clamp(0.8 * scale, 0.40, 0.95)

        # ✅ SFX marks (timing auto uses these run_time vars)
        sfx.mark("charge_up", gain_db=-8, meta={"at": "hook_title_start"})
        sfx.mark("ui_pop", gain_db=-10, offset=max(0.0, rt_title * 0.85), meta={"at": "hook_title_end"})
        sfx.mark("scan_tick", gain_db=-14, offset=max(0.0, rt_title * 0.35), meta={"at": "hook_scan_begin"})

        self.play(
            Write(title, run_time=rt_title),
            GrowFromCenter(underline, run_time=rt_line),
            FadeIn(scanner_dot, run_time=rt_dot),
            FadeIn(subtitle, shift=UP * 0.2, run_time=rt_sub),
        )
        
        TL.consume("hook", float(self.time) - hook_t0)
        hold_breathing(self, TL.remaining("hook"), focus=underline_core)

        # ============================================================
        # 6) LAYOUT
        # ============================================================
        top_y = sf["top"] - 3.2
        bottom_y = sf["bottom"] + 2.1
        available_h = top_y - bottom_y
        GAP_Y = min(1.75, available_h / (num_items + 0.2))
        START_Y = top_y

        RAIL_X = sf["left"] + 0.55
        RANK_X = RAIL_X + 0.60
        LABEL_X = RANK_X + 1.10
        BAR_START_X = LABEL_X + 1.10

        VALUE_GUTTER_W = 0.95
        BAR_RIGHT_LIMIT = sf["right"] - VALUE_GUTTER_W
        BAR_MAX_WIDTH = BAR_RIGHT_LIMIT - BAR_START_X
        VALUE_ANCHOR_X = sf["right"] - 0.30
        BAR_HEIGHT = 0.62

        # ============================================================
        # SETUP segment (rail + guides)
        # ============================================================
        setup_t0 = float(self.time)
        rail_top = START_Y + 0.55
        rail_bottom = START_Y - (num_items - 1) * GAP_Y - 0.55

        rail = Line([RAIL_X, rail_top, 0], [RAIL_X, rail_bottom, 0]).set_stroke(
            color=Theme.NEON_BLUE, width=3, opacity=0.35
        )
        rail.set_z_index(35)

        rail_glow = rail.copy().set_stroke(color=WHITE, width=12, opacity=0.06)
        rail_glow.set_z_index(34)

        rail_label = Text("RANK", font="Montserrat", weight=BOLD, font_size=16, color=Theme.NEON_PINK)
        rail_label.rotate(90 * DEGREES)
        rail_label.move_to([RAIL_X - 0.35, (rail_top + rail_bottom) / 2, 0])
        rail_label.set_opacity(0.85)
        rail_label.set_z_index(40)

        rail_scanner = Dot(color=WHITE, radius=0.06).move_to([RAIL_X, rail_top, 0])
        rail_scanner.set_z_index(45)

        def _rail_scan(m, dt):
            speed = 0.9
            y = rail_top - (self.time * speed) % max(0.001, (rail_top - rail_bottom))
            m.move_to([RAIL_X, y, 0])

        rail_scanner.add_updater(_rail_scan)

        setup_total = TL.seg_total("setup", 1.3)
        setup_action = clamp(setup_total * 0.75, 0.9, 1.6)

        sfx.mark("ui_pop", gain_db=-11, meta={"at": "setup_rail_in"})
        self.play(
            FadeIn(rail_glow),
            Create(rail),
            FadeIn(rail_label),
            FadeIn(rail_scanner),
            run_time=clamp(setup_action * 0.55, 0.35, 0.75),
        )

        milestone_fracs = [0.0, 0.25, 0.50, 0.75, 1.0]
        guide_group = VGroup()
        for frac in milestone_fracs:
            x_pos = BAR_START_X + frac * BAR_MAX_WIDTH
            v_line = DashedLine(
                start=[x_pos, START_Y + 0.75, 0],
                end=[x_pos, rail_bottom - 0.25, 0],
                dash_length=0.18,
                dashed_ratio=0.6,
            ).set_stroke(Theme.NEON_BLUE, width=2, opacity=0.12)

            label_val = int(round(float(max_val) * frac))
            label = Text(str(label_val), font="Montserrat", font_size=14, color=Theme.TEXT_SUB)
            label.move_to([x_pos, rail_bottom - 0.55, 0])
            guide_group.add(v_line, label)

        sfx.mark("scan_tick", gain_db=-16, meta={"at": "setup_guides"})
        self.play(Create(guide_group, run_time=clamp(setup_action * 0.75, 0.55, 1.05), lag_ratio=0.08))
        
        TL.consume("setup", float(self.time) - setup_t0)
        hold_breathing(self, TL.remaining("setup"), focus=rail)

        # ============================================================
        # 7) BAR ENGINE (item_1 ... item_n)
        # ============================================================
        bar_groups = []

        for i, (name, value) in enumerate(zip(names, values)):
            seg = f"item_{i+1}"
            item_t0 = float(self.time)
            item_total = TL.seg_total(seg, 2.0)

            y_pos = START_Y - (i * GAP_Y)
            denom = max(1e-6, float(max_val))
            target_width = float(np.clip((float(value) / denom) * BAR_MAX_WIDTH, 0.0, BAR_MAX_WIDTH))

            branch = Line([RAIL_X, y_pos, 0], [RANK_X - 0.18, y_pos, 0]).set_stroke(
                color=Theme.NEON_BLUE, width=2, opacity=0.25
            )
            bolt = Dot(color=WHITE, radius=0.035).move_to(branch.get_start())
            bolt.set_opacity(0.6)

            rank_bg = Circle(radius=0.25, color="#0B0B0B", fill_opacity=1).set_stroke(
                Theme.NEON_BLUE, width=2, opacity=0.7
            ).move_to([RANK_X, y_pos, 0])
            rank_num = Text(f"{i + 1}", font="Montserrat", weight=BOLD, font_size=20, color=WHITE).move_to(rank_bg)

            name_text = Text(str(name).upper(), font="Montserrat", weight=BOLD, font_size=24, color=WHITE)
            text_plate = RoundedRectangle(corner_radius=0.12, width=name_text.width + 0.55, height=0.52)
            text_plate.set_fill(color="#000000", opacity=0.70).set_stroke(width=0)
            text_plate.move_to([LABEL_X, y_pos + 0.45, 0])
            name_text.move_to(text_plate)

            text_plate.move_to(
                [clamp_x(text_plate.get_x(), text_plate.width, 0.70),
                 clamp_y(text_plate.get_y(), text_plate.height, 0.70), 0]
            )
            name_text.move_to(text_plate)
            label_group = VGroup(text_plate, name_text)

            t_label = clamp(item_total * 0.22, 0.30, 0.55)
            t_track = clamp(item_total * 0.56, 0.95, 1.60)
            t_morph = clamp(item_total * 0.22, 0.35, 0.55)

            s = t_label + t_track + t_morph
            if s > item_total:
                overflow = s - item_total
                t_track = max(0.75, t_track - overflow)

            # ✅ SFX: label pop
            sfx.mark("ui_pop", gain_db=-12, meta={"at": "item_label", "i": i+1})

            self.play(
                FadeIn(branch, run_time=t_label),
                FadeIn(bolt, run_time=t_label),
                FadeIn(rank_bg, shift=RIGHT * 0.15, run_time=t_label),
                FadeIn(rank_num, shift=RIGHT * 0.15, run_time=t_label),
                FadeIn(label_group, shift=RIGHT * 0.15, run_time=t_label),
            )

            container = RoundedRectangle(corner_radius=0.12, width=BAR_MAX_WIDTH + 0.20, height=BAR_HEIGHT)
            container.set_stroke(Theme.NEON_BLUE, width=2, opacity=0.35)
            container.set_fill("#060606", opacity=0.85)
            container.move_to([BAR_START_X + BAR_MAX_WIDTH / 2, y_pos, 0])
            self.add(container)

            num_dots = 12
            dot_positions = []
            dots_group = VGroup()

            for k in range(num_dots):
                tt = k / (num_dots - 1)
                x = BAR_START_X + tt * target_width
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
            spark = Dot(radius=0.11, color=WHITE).set_opacity(0.9)
            line_group = VGroup(zig_glow, zig_line, spark)
            self.add(line_group)

            final_bar = RoundedRectangle(corner_radius=0.10, width=max(0.10, target_width), height=BAR_HEIGHT - 0.16)
            final_bar.set_stroke(color=WHITE, width=1.0, opacity=0.10)
            final_bar.set_fill(
                color=Theme.C_BAR_GRADIENT if hasattr(Theme, "C_BAR_GRADIENT") else [Theme.NEON_BLUE, Theme.NEON_PINK],
                opacity=1,
            )
            final_bar.align_to(container, LEFT).shift(RIGHT * 0.10).set_y(y_pos).set_opacity(0)

            sheen = RoundedRectangle(corner_radius=0.10, width=max(0.10, target_width), height=(BAR_HEIGHT - 0.16) / 2)
            sheen.set_stroke(width=0).set_fill(color=WHITE, opacity=0.18)
            sheen.align_to(final_bar, UP).align_to(final_bar, LEFT).set_opacity(0)

            val_num = DecimalNumber(0, num_decimal_places=0, font_size=24, color=Theme.NEON_BLUE)
            val_num.set_z_index(60)
            self.add(val_num)

            val_pill = RoundedRectangle(corner_radius=0.12, width=1.15, height=0.46)
            val_pill.set_fill(color=BLACK, opacity=0.55).set_stroke(width=0)
            val_pill.set_z_index(55)
            self.add(val_pill)

            tracker = ValueTracker(0)
            flashed_indices = set()

            def update_single_bar(_):
                t = tracker.get_value()
                val_num.set_value(t * float(value))

                x = VALUE_ANCHOR_X - (val_num.width / 2)
                x = clamp_x(x, val_num.width, 0.70)
                val_num.move_to([x, y_pos, 0])

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

            sfx.mark("scan_tick", gain_db=-16, meta={"at": "item_fill", "i": i+1})

            self.play(tracker.animate.set_value(1.0), run_time=t_track, rate_func=rf.ease_out_cubic)

            line_group.remove_updater(update_single_bar)

            temp_straight = Line(dot_positions[0], dot_positions[-1], color=WHITE, stroke_width=4)
            self.add(temp_straight)
            self.remove(line_group, dots_group)

            final_bar.set_opacity(1)
            sheen.set_opacity(1)

            # ✅ SFX: impact at morph/flash
            sfx.mark("impact_soft", gain_db=-10, meta={"at": "item_impact", "i": i+1})

            shockwave = Circle(radius=0.08, color=WHITE, stroke_width=4).move_to(final_bar.get_right())
            self.play(
                ReplacementTransform(temp_straight, final_bar),
                FadeIn(sheen, run_time=min(0.18, t_morph * 0.35)),
                Flash(final_bar.get_right(), color=WHITE, line_length=0.9, flash_radius=0.45),
                shockwave.animate.scale(6).set_opacity(0),
                run_time=t_morph,
                rate_func=rf.ease_out_back,
            )
            self.remove(shockwave)

            settle_rt = min(0.14, TL.remaining(seg) * 0.35)
            if settle_rt > 0.02:
                _micro_settle(self, [final_bar, val_pill, val_num], settle_rt)

            TL.consume(seg, float(self.time) - item_t0)
            hold_breathing(self, TL.remaining(seg), focus=final_bar)

            bar_groups.append(
                VGroup(branch, bolt, rank_bg, rank_num, label_group, container, final_bar, sheen, val_pill, val_num)
            )

        # Ghost Padding Loop — absorbs extra item_* audio segments beyond CSV row count.
        # Cap derived from audio.order so jobs with >15 items are handled correctly.
        _ghost_cap = max(len(_item_segs_audio), num_items)
        for ghost_i in range(num_items, _ghost_cap):
            seg_key = f"item_{ghost_i+1}"
            g_t0 = float(self.time)
            TL.consume(seg_key, float(self.time) - g_t0)
            hold_breathing(self, TL.remaining(seg_key))

        # ============================================================
        # 8) WINNER REVEAL
        # ============================================================
        winner_seg = "winner"
        winner_t0 = float(self.time)
        winner_total = TL.seg_total(winner_seg, 3.2)

        banner = None
        if bar_groups:
            winner_index = int(np.argmax(values)) if values else 0
            winner_index = int(np.clip(winner_index, 0, max(0, len(bar_groups) - 1)))

            winner = bar_groups[winner_index]
            others = [g for j, g in enumerate(bar_groups) if j != winner_index]

            t_dim = clamp(winner_total * 0.12, 0.25, 0.45)
            self.play(*[g.animate.set_opacity(0.20) for g in others], run_time=t_dim)

            winner_bar = winner[6]
            winner_val = winner[9]
            winner_label = winner[4]

            t_sweep = clamp(winner_total * 0.12, 0.22, 0.40)
            _winner_sweep(self, winner_bar, t_sweep, color_core=WHITE, color_glow=Theme.NEON_BLUE)

            banner_h = 1.65
            banner = RoundedRectangle(width=sf["w"], height=banner_h, corner_radius=0.18)
            banner.set_fill(color="#000000", opacity=0.85)
            banner.set_stroke(color=Theme.NEON_PINK, width=3, opacity=0.8)
            banner.move_to([sf["cx"], sf["bottom"] + (banner_h / 2) + 0.35, 0])
            banner.set_z_index(200)

            win_name = str(names[winner_index]).upper()
            win_val = float(values[winner_index])

            t1 = Text("TOP LEADER", font="Montserrat", weight=BOLD, font_size=22, color=Theme.TEXT_SUB)
            t2 = Text(win_name, font="Montserrat", weight=BOLD, font_size=46, color=Theme.TEXT_MAIN)
            t3 = Text(f"SCORE: {int(round(win_val))}", font="Montserrat", weight=BOLD, font_size=22, color=Theme.NEON_BLUE)
            txt = VGroup(t1, t2, t3).arrange(DOWN, buff=0.12).move_to(banner)
            txt.set_z_index(201)

            dimmer = Rectangle(width=60, height=60).set_fill(color=BLACK, opacity=0.28).set_stroke(width=0)
            dimmer.set_z_index(180)
            self.add(dimmer)

            t_focus = clamp(winner_total * 0.22, 0.35, 0.60)
            self.play(
                winner.animate.set_opacity(1.0),
                winner_bar.animate.scale(1.05),
                winner_val.animate.set_color(WHITE),
                Indicate(winner_label, color=WHITE, scale_factor=1.02),
                run_time=t_focus,
                rate_func=rf.ease_out_back,
            )

            # ✅ SFX: winner rise when banner comes
            t_banner = clamp(winner_total * 0.28, 0.45, 0.85)
            sfx.mark("winner_rise", gain_db=-9, meta={"at": "winner_banner"})
            self.play(GrowFromCenter(banner), FadeIn(txt, shift=UP * 0.2),
                      run_time=t_banner, rate_func=rf.ease_out_cubic)

            t_flash = clamp(winner_total * 0.14, 0.25, 0.40)
            sfx.mark("impact_soft", gain_db=-12, meta={"at": "winner_flash"})
            self.play(
                Flash(banner.get_top(), color=WHITE, line_length=0.6, num_lines=10),
                Flash(winner_bar.get_right(), color=Theme.NEON_BLUE, line_length=0.6, num_lines=8),
                run_time=t_flash,
            )

            TL.consume(winner_seg, float(self.time) - winner_t0)
            banner_scan_hold(self, banner, TL.remaining(winner_seg), color=WHITE)

        # ============================================================
        # OUTRO
        # ============================================================
        outro_t0 = float(self.time)
        outro_total = TL.seg_total("outro", 1.2)
        outro_action = clamp(outro_total * 0.55, 0.60, 1.35)

        if bar_groups and outro_action > 0.05:
            idxs = list(range(len(values)))
            idxs_sorted = sorted(idxs, key=lambda k: float(values[k]), reverse=True)
            top3 = idxs_sorted[:3]

            tag = Text("TOP 3 LOCKED", font="Montserrat", weight=BOLD, font_size=24, color=WHITE)
            tag_bg = RoundedRectangle(corner_radius=0.18, width=tag.width + 0.70, height=0.62)
            tag_bg.set_fill(color=BLACK, opacity=0.55).set_stroke(color=Theme.NEON_BLUE, width=2, opacity=0.35)
            tag_group = VGroup(tag_bg, tag).move_to([sf["cx"], sf["top"] - 2.15, 0]).set_z_index(210)

            pulses = []
            for j, ii in enumerate(top3):
                b = bar_groups[ii][6]
                pulses.append(Indicate(b, color=WHITE, scale_factor=1.03))

            sfx.mark("ui_pop", gain_db=-12, meta={"at": "outro_tag"})
            self.play(FadeIn(tag_group, shift=DOWN * 0.15), run_time=min(0.22, outro_action * 0.35), rate_func=rf.ease_out_cubic)
            self.play(AnimationGroup(*pulses, lag_ratio=0.12), run_time=max(0.20, outro_action - min(0.22, outro_action * 0.35)), rate_func=rf.ease_out_cubic)
            self.play(FadeOut(tag_group, shift=UP * 0.10), run_time=0.18, rate_func=rf.ease_in_cubic)

        TL.consume("outro", float(self.time) - outro_t0)
        try:
            if banner is not None:
                banner_scan_hold(self, banner, TL.remaining("outro"), color=WHITE)
            else:
                hold_breathing(self, TL.remaining("outro"), focus=underline_core)
        except Exception:
            hold_breathing(self, TL.remaining("outro"), focus=underline_core)

        # ✅ MOST IMPORTANT: write marks JSON so main.py can mix SFX
        sfx.flush()
