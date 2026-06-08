# src/templates/line_chart/scan_race.py
# Cinematic Bar Race Template (Full Production Rewrite)
# Segments: hook, setup, middle, finish, outro
#
# CSV format (first line optional meta, then header):
#   # TITLE=AI PATENT RACE, SUB=2024 FILINGS, UNIT=K
#   Entity,Start,Mid,End,Color
#   Nvidia,45,82,124,#00F0FF
#
# If only End/Value column exists, Start and Mid are auto-derived.

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from manim import *
from manim import rate_functions as rf

# --- PROJECT IMPORTS ---
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    sys.path.append(project_root)
    from src.config import DATA_DIR, BACKGROUND_COLOR, Theme
    from src.utils import IntroManager, get_safe_frame, make_floating_particles, get_branding_border
except Exception:
    project_root = os.getcwd()
    DATA_DIR = os.path.join(project_root, "data")
    BACKGROUND_COLOR = "#050505"

    class Theme:
        NEON_BLUE = "#00F0FF"
        NEON_PINK = "#FF0055"
        NEON_PURPLE = "#BD00FF"
        NEON_GREEN = "#00FF66"
        NEON_YELLOW = "#FFE14D"
        TEXT_MAIN = "#FFFFFF"
        TEXT_SUB = "#B8B8B8"

    def get_safe_frame(margin=0.70):
        hw, hh = config.frame_width / 2, config.frame_height / 2
        return {"left": -hw + margin, "right": hw - margin, "top": hh - margin,
                "bottom": -hh + margin, "w": config.frame_width - 2 * margin,
                "h": config.frame_height - 2 * margin, "cx": 0.0, "cy": 0.0}

    def make_floating_particles(*args, **kwargs):
        return VGroup()

    def get_branding_border():
        b = Rectangle(height=config.frame_height, width=config.frame_width)
        b.set_stroke(width=8, color=[Theme.NEON_BLUE, Theme.NEON_PINK], opacity=0.55).set_fill(opacity=0)
        return b

    class IntroManager:
        @staticmethod
        def play_intro(scene, brand_title="BIGDATA LEAK", brand_sub="RACE RESULTS",
                       feed_text="FEED_RACE // SCAN", footer_text="CONFIDENTIAL // VERIFIED"):
            t1 = Text(brand_title, font="Montserrat", weight=BOLD, font_size=42, color=WHITE).move_to(UP * 0.5)
            t2 = Text(brand_sub, font="Consolas", font_size=18, color=GREY_B).next_to(t1, DOWN, buff=0.2)
            scene.play(FadeIn(t1, shift=UP * 0.1), FadeIn(t2), run_time=0.85, rate_func=rf.ease_out_cubic)
            scene.play(FadeOut(t1), FadeOut(t2), run_time=0.40, rate_func=rf.ease_in_out_sine)

# --- SYNC HELPERS ---
from src.sync.job import load_job
from src.sync.timeline import Timeline, clamp
from src.sfx.engine import SFXEngine
try:
    from src.sync.retention import hold_breathing, banner_scan_hold, register_template_accent
    from src.sync.retention_accents import retain_accent_scan_race
except Exception:
    def hold_breathing(scene, seconds: float, focus=None, text: str = ""):
        if seconds > 0:
            scene.wait(seconds)
    def register_template_accent(scene, fn):
        pass
    def retain_accent_scan_race(scene, focus, seconds, **kw):
        return lambda: None
    def banner_scan_hold(scene, banner, seconds: float, color=None):
        if seconds > 0:
            scene.wait(seconds)


RACE_PALETTE = [
    "#00F0FF", "#FF0055", "#BD00FF", "#FFE14D",
    "#00FF66", "#FF9900", "#3388FF", "#FF6EC7",
]


def _parse_meta(path: str) -> dict:
    meta = {"TITLE": "THE RACE", "SUB": "Competitor Analysis",
            "UNIT": "pts", "PHASE_A": "START", "PHASE_B": "MID", "PHASE_C": "FINISH"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("#"):
            for part in first[1:].split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    meta[k.strip().upper()] = v.strip()
    except Exception:
        pass
    return meta


def load_race_csv(csv_path: str):
    meta = _parse_meta(csv_path)
    if not os.path.exists(csv_path):
        entities = ["Nvidia", "Google", "Microsoft", "Apple", "Amazon"]
        starts   = [45.0, 51.0, 38.0, 35.0, 28.0]
        mids     = [82.0, 74.0, 67.0, 55.0, 44.0]
        ends     = [124.0, 91.0, 95.0, 72.0, 65.0]
        cols     = RACE_PALETTE[:5]
        return meta, entities, starts, mids, ends, cols

    df = pd.read_csv(csv_path, comment="#")
    df.columns = [c.strip().title() for c in df.columns]

    if "Entity" not in df.columns:
        raise ValueError("scan_race CSV must have an 'Entity' column.")
    df["Entity"] = df["Entity"].astype(str).str.strip()
    df = df.head(8)

    for col in ("Start", "Mid", "End", "Value"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "End" not in df.columns:
        df["End"] = df.get("Value", pd.Series([1.0] * len(df)))
    if "Start" not in df.columns:
        df["Start"] = df["End"] * 0.45
    if "Mid" not in df.columns:
        df["Mid"] = (df["Start"] + df["End"]) / 2.0

    if "Color" in df.columns:
        raw = df["Color"].astype(str).str.strip().tolist()
        cols = [c if c.startswith("#") else RACE_PALETTE[i % len(RACE_PALETTE)]
                for i, c in enumerate(raw)]
    else:
        cols = [RACE_PALETTE[i % len(RACE_PALETTE)] for i in range(len(df))]

    return (meta, df["Entity"].tolist(), df["Start"].tolist(),
            df["Mid"].tolist(), df["End"].tolist(), cols)


def _rank_order(entities, values, colors):
    """Return entities, values, colors sorted by value descending."""
    z = sorted(zip(values, entities, colors), reverse=True)
    if not z:
        return [], [], []
    vs, es, cs = zip(*z)
    return list(es), list(vs), list(cs)


# --- Premium visual layer (Visual & Aesthetic Pass) ---
try:
    from src.utils import add_cinematic_background
except Exception:
    def add_cinematic_background(*_a, **_k):
        return None
try:
    from src.config import FONT_DISPLAY
except Exception:
    FONT_DISPLAY = "Montserrat"


class CinematicLineRace(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        add_cinematic_background(self, accent=Theme.NEON_BLUE)

        # ✅ 0.0s Intro Rule
        global_start_t0 = float(self.time)
        register_template_accent(
            self,
            lambda s, f, t: retain_accent_scan_race(s, f, t, bar_color="#00F0FF"),
        )

        job = load_job(default={"template_id": "scan_race", "timeline": {}})
        job_dir_env = os.environ.get("JOB_DIR", "")
        job_json_path = os.environ.get("JOB_JSON_PATH", "")
        job_dir = job_dir_env or (os.path.dirname(job_json_path) if job_json_path else project_root)

        sfx = SFXEngine(self, job_dir)
        timeline_dict = job.get("timeline", {}) if isinstance(job.get("timeline"), dict) else {}

        csv_path = job.get("data_csv") or "data/race_data.csv"
        if not os.path.isabs(csv_path):
            csv_path = os.path.join(job_dir, csv_path)
        meta, entities, starts, mids, ends, colors = load_race_csv(csv_path)
        n = len(entities)
        unit = meta.get("UNIT", "")
        idx = {e: i for i, e in enumerate(entities)}  # entity → original index

        defaults = {"hook": 2.5, "setup": 2.8, "middle": 3.2, "finish": 3.0, "outro": 1.8}
        TL = Timeline.from_dict(timeline_dict, defaults=defaults)

        sf = get_safe_frame(margin=0.70)
        max_val = max(ends) if ends else 1.0

        # ============================================================
        # BACKGROUND
        # ============================================================
        try:
            particles = make_floating_particles(n=20, color=Theme.NEON_BLUE,
                                                radius_range=(0.02, 0.05),
                                                opacity_range=(0.05, 0.14),
                                                drift=0.025, margin=0.70)
            particles.set_z_index(5)
            self.add(particles)
        except Exception:
            pass

        grid = VGroup()
        for x in np.arange(sf["left"], sf["right"] + 0.01, 0.85):
            grid.add(Line([x, sf["bottom"], 0], [x, sf["top"], 0]).set_stroke(Theme.NEON_BLUE, 1, 0.03))
        for y in np.arange(sf["bottom"], sf["top"] + 0.01, 0.85):
            grid.add(Line([sf["left"], y, 0], [sf["right"], y, 0]).set_stroke(Theme.NEON_BLUE, 1, 0.025))
        grid.set_z_index(2)
        self.add(grid)

        try:
            self.add(get_branding_border().set_z_index(650))
        except Exception:
            pass

        # ============================================================
        # HEADER
        # ============================================================
        title = Text((meta.get("TITLE") or "THE RACE").upper(),
                     font=FONT_DISPLAY, weight=BOLD, font_size=40, color=WHITE)
        title.to_edge(UP, buff=0.72).set_z_index(500)

        sub = Text((meta.get("SUB") or "Competitor Analysis").upper(),
                   font="Consolas", font_size=18, color=Theme.TEXT_SUB)
        sub.next_to(title, DOWN, buff=0.10).set_z_index(500)

        lw = min(sf["w"] * 0.78, 7.0)
        uL = Line(LEFT * lw / 2, ORIGIN).set_stroke(Theme.NEON_BLUE, 4, 0.95)
        uR = Line(ORIGIN, RIGHT * lw / 2).set_stroke(Theme.NEON_PINK, 4, 0.95)
        underline = VGroup(uL, uR).arrange(RIGHT, buff=0).next_to(sub, DOWN, buff=0.15).set_z_index(500)
        underline_glow = VGroup(
            uL.copy().set_stroke(Theme.NEON_BLUE, 18, 0.15),
            uR.copy().set_stroke(Theme.NEON_PINK, 18, 0.15),
        ).arrange(RIGHT, buff=0).next_to(sub, DOWN, buff=0.15).set_z_index(498)

        self.add(underline_glow, title, sub, underline)

        # ============================================================
        # RACE BAR LAYOUT
        # ============================================================
        BAR_TOP    = sf["top"] - 2.20
        BAR_BOTTOM = sf["bottom"] + 1.20
        BAR_H      = min(0.60, (BAR_TOP - BAR_BOTTOM - 0.12 * n) / max(n, 1))
        BAR_GAP    = max(0.08, (BAR_TOP - BAR_BOTTOM - BAR_H * n) / max(n - 1, 1))
        LABEL_X    = sf["left"] + 0.05
        BAR_X0     = sf["left"] + 1.70   # bar left edge
        BAR_X1     = sf["right"] - 0.50  # bar right edge at max val
        BAR_MAX_W  = BAR_X1 - BAR_X0

        def bar_y(rank: int) -> float:
            return BAR_TOP - BAR_H / 2 - rank * (BAR_H + BAR_GAP)

        def bar_w(val: float) -> float:
            return max(0.04, BAR_MAX_W * float(val) / max_val)

        # Build mobjects per entity
        groups: dict = {}
        for i, entity in enumerate(entities):
            col = colors[i]

            lbl = Text(entity.upper(), font="Consolas", font_size=17, color=col, weight=BOLD).set_z_index(60)

            bar = Rectangle(width=0.04, height=BAR_H)
            bar.set_fill(col, 0.85).set_stroke(width=0).set_z_index(58)
            bar_glow = Rectangle(width=0.04, height=BAR_H + 0.10)
            bar_glow.set_fill(col, 0.20).set_stroke(width=0).set_z_index(56)

            val_txt = Text("0", font="Montserrat", weight=BOLD, font_size=17, color=WHITE).set_z_index(65)

            rank_bg = Circle(radius=0.22).set_fill("#080808", 1.0).set_stroke(col, 2.5, 0.90).set_z_index(70)
            rank_txt = Text("1", font="Consolas", weight=BOLD, font_size=17, color=col).set_z_index(71)

            groups[entity] = {
                "lbl": lbl, "bar": bar, "bar_glow": bar_glow,
                "val_txt": val_txt, "rank_bg": rank_bg, "rank_txt": rank_txt,
                "col": col,
            }
            for mob in (bar_glow, bar, lbl, val_txt, rank_bg, rank_txt):
                mob.set_opacity(0)
                self.add(mob)

        def _snap(entity: str, rank: int, val: float, show_rank: bool = True):
            """Instantly reposition all mobjects for one entity."""
            g = groups[entity]
            y = bar_y(rank)
            bw = bar_w(val)
            bx = BAR_X0 + bw / 2

            g["bar"].stretch_to_fit_width(bw).move_to([bx, y, 0])
            g["bar_glow"].stretch_to_fit_width(bw + 0.14).move_to([BAR_X0 + (bw + 0.14) / 2, y, 0])
            g["lbl"].move_to([LABEL_X + g["lbl"].width / 2, y, 0])

            new_val = Text(f"{val:.0f}{unit}", font="Montserrat", weight=BOLD, font_size=17, color=WHITE)
            new_val.move_to([BAR_X0 + bw + new_val.width / 2 + 0.14, y, 0]).set_z_index(65)
            g["val_txt"].become(new_val)

            new_rank = Text(str(rank + 1), font="Consolas", weight=BOLD, font_size=17, color=g["col"])
            g["rank_bg"].move_to([BAR_X0 - 0.36, y, 0])
            new_rank.move_to(g["rank_bg"].get_center()).set_z_index(71)
            g["rank_txt"].become(new_rank)

            if not show_rank:
                g["rank_bg"].set_opacity(0)
                g["rank_txt"].set_opacity(0)

        def _race_anims(target_order, target_vals_map, run_time, rate):
            """Build Transform-based race animation to new positions and widths."""
            anims = []
            for rank, entity in enumerate(target_order):
                g = groups[entity]
                y = bar_y(rank)
                bw = bar_w(target_vals_map[entity])
                bx = BAR_X0 + bw / 2

                target_bar = Rectangle(width=bw, height=BAR_H)
                target_bar.set_fill(g["col"], 0.85).set_stroke(width=0).move_to([bx, y, 0]).set_z_index(58)
                anims.append(Transform(g["bar"], target_bar, run_time=run_time, rate_func=rate))

                target_glow = Rectangle(width=bw + 0.14, height=BAR_H + 0.10)
                target_glow.set_fill(g["col"], 0.20).set_stroke(width=0).move_to([BAR_X0 + (bw + 0.14) / 2, y, 0]).set_z_index(56)
                anims.append(Transform(g["bar_glow"], target_glow, run_time=run_time, rate_func=rate))

                anims.append(g["lbl"].animate(run_time=run_time, rate_func=rate).move_to([LABEL_X + g["lbl"].width / 2, y, 0]))
                anims.append(g["rank_bg"].animate(run_time=run_time, rate_func=rate).move_to([BAR_X0 - 0.36, y, 0]))

            return anims

        # ============================================================
        # INTRO
        # ============================================================
        try:
            IntroManager.play_intro(
                self, brand_title="BIGDATA LEAK", brand_sub="RACE RESULTS",
                feed_text="FEED_RACE // SCAN", footer_text="CONFIDENTIAL // VERIFIED",
            )
        except Exception:
            pass

        # ============================================================
        # HOOK — header + entity labels appear
        # ============================================================
        hook_t0 = global_start_t0
        sfx.mark("riser", gain_db=-8, meta={"at": "hook_in"})

        # Pre-position at rank 0 with 0 width
        for i, entity in enumerate(entities):
            _snap(entity, i, 0, show_rank=False)

        self.play(
            FadeIn(title, shift=DOWN * 0.18),
            FadeIn(sub, shift=DOWN * 0.12),
            FadeIn(underline, shift=DOWN * 0.08),
            FadeIn(underline_glow, shift=DOWN * 0.08),
            run_time=0.75, rate_func=rf.ease_out_cubic,
        )

        sfx.mark("sweep", gain_db=-10, meta={"at": "labels_in"})
        self.play(
            *[FadeIn(groups[e]["lbl"], shift=RIGHT * 0.22) for e in entities],
            run_time=0.65, rate_func=rf.ease_out_cubic,
        )

        TL.consume("hook", float(self.time) - hook_t0)
        hold_breathing(self, TL.remaining("hook"), focus=underline, text="LOADING RACE DATA")

        # ============================================================
        # SETUP — bars grow to start values
        # ============================================================
        setup_t0 = float(self.time)
        init_order, init_vals, _ = _rank_order(entities, starts, colors)
        start_map = {e: starts[idx[e]] for e in entities}

        sfx.mark("charge_up", gain_db=-10, meta={"at": "setup_bars"})

        # Reveal bars at 0 width
        for rank, entity in enumerate(init_order):
            _snap(entity, rank, 0, show_rank=False)
            for mob in (groups[entity]["bar"], groups[entity]["bar_glow"]):
                mob.set_opacity(0.0)

        setup_anims = []
        for rank, entity in enumerate(init_order):
            g = groups[entity]
            bw = bar_w(start_map[entity])
            y = bar_y(rank)

            target_bar = Rectangle(width=bw, height=BAR_H)
            target_bar.set_fill(g["col"], 0.85).set_stroke(width=0).move_to([BAR_X0 + bw / 2, y, 0]).set_z_index(58)
            setup_anims.append(Transform(g["bar"], target_bar))

            target_glow = Rectangle(width=bw + 0.14, height=BAR_H + 0.10)
            target_glow.set_fill(g["col"], 0.20).set_stroke(width=0).move_to([BAR_X0 + (bw + 0.14) / 2, y, 0]).set_z_index(56)
            setup_anims.append(Transform(g["bar_glow"], target_glow))

            setup_anims.append(g["bar"].animate.set_opacity(0.85))
            setup_anims.append(g["bar_glow"].animate.set_opacity(0.20))

        self.play(*setup_anims, run_time=1.0, rate_func=rf.ease_out_cubic)

        for rank, entity in enumerate(init_order):
            _snap(entity, rank, start_map[entity], show_rank=True)
            for mob in (groups[entity]["val_txt"], groups[entity]["rank_bg"], groups[entity]["rank_txt"]):
                mob.set_opacity(1.0)

        TL.consume("setup", float(self.time) - setup_t0)
        hold_breathing(self, TL.remaining("setup"), focus=underline, text="RACE STARTS NOW")

        # ============================================================
        # MIDDLE — race to mid values
        # ============================================================
        middle_t0 = float(self.time)
        mid_order, _, _ = _rank_order(entities, mids, colors)
        mid_map = {e: mids[idx[e]] for e in entities}

        sfx.mark("scan_tick", gain_db=-12, meta={"at": "middle_race"})
        t_mid = clamp(TL.seg_total("middle", 3.2) * 0.55, 0.80, 1.80)
        self.play(*_race_anims(mid_order, mid_map, t_mid, rf.ease_in_out_sine), run_time=t_mid)
        for rank, entity in enumerate(mid_order):
            _snap(entity, rank, mid_map[entity], show_rank=True)

        TL.consume("middle", float(self.time) - middle_t0)
        hold_breathing(self, TL.remaining("middle"), focus=underline, text="RACE IN PROGRESS")

        # ============================================================
        # FINISH — final sprint
        # ============================================================
        finish_t0 = float(self.time)
        end_order, _, _ = _rank_order(entities, ends, colors)
        end_map = {e: ends[idx[e]] for e in entities}

        sfx.mark("hit_soft", gain_db=-10, meta={"at": "finish_race"})
        t_fin = clamp(TL.seg_total("finish", 3.0) * 0.50, 0.70, 1.40)
        self.play(*_race_anims(end_order, end_map, t_fin, rf.ease_out_cubic), run_time=t_fin)
        for rank, entity in enumerate(end_order):
            _snap(entity, rank, end_map[entity], show_rank=True)

        # Highlight winner bar immediately
        winner = end_order[0]
        win_col = groups[winner]["col"]
        others = [e for e in entities if e != winner]

        sfx.mark("winner_rise", gain_db=-9, meta={"at": "winner_highlight"})
        self.play(
            groups[winner]["bar"].animate.set_opacity(1.0),
            groups[winner]["bar_glow"].animate.set_opacity(0.42),
            *[groups[e]["bar"].animate.set_opacity(0.40) for e in others],
            *[groups[e]["bar_glow"].animate.set_opacity(0.05) for e in others],
            *[groups[e]["lbl"].animate.set_opacity(0.45) for e in others],
            run_time=0.50, rate_func=rf.ease_out_cubic,
        )

        TL.consume("finish", float(self.time) - finish_t0)
        hold_breathing(self, TL.remaining("finish"), focus=groups[winner]["bar"], text="FINAL STANDINGS")

        # ============================================================
        # OUTRO — winner banner
        # ============================================================
        outro_t0 = float(self.time)
        sfx.mark("impact_soft", gain_db=-11, meta={"at": "winner_banner"})

        banner = RoundedRectangle(width=sf["w"] * 0.86, height=1.40, corner_radius=0.18)
        banner.set_fill("#000000", 0.88).set_stroke(win_col, 3, 0.90).set_z_index(200)
        banner.move_to([sf["cx"], sf["bottom"] + 0.95, 0])
        banner_glow = banner.copy().set_fill(opacity=0).set_stroke(win_col, 22, 0.22).set_z_index(199)

        win_val = ends[idx[winner]]
        banner_txt = VGroup(
            Text(winner.upper(), font="Montserrat", weight=BOLD, font_size=36, color=win_col),
            Text(f"{win_val:.0f}{unit}", font="Consolas", weight=BOLD, font_size=22, color=WHITE),
            Text("RACE WINNER", font="Consolas", font_size=14, color=Theme.TEXT_SUB),
        ).arrange(DOWN, buff=0.08).move_to(banner).set_z_index(201)

        self.play(
            FadeIn(banner_glow), GrowFromCenter(banner),
            FadeIn(banner_txt, shift=UP * 0.12),
            run_time=0.62, rate_func=rf.ease_out_cubic,
        )

        sfx.mark("ui_pop", gain_db=-12, meta={"at": "outro"})
        hold_breathing(self, TL.seg_total("outro", 1.8), focus=banner, text="SYSTEM SHUTDOWN")
        TL.consume("outro", float(self.time) - outro_t0)

        try:
            sfx.flush()
        except Exception:
            pass
