# src/templates/pie_chart/donut_breakdown.py
# Donut Breakdown Chart Template (Full Production Rewrite)
# Segments: hook, setup, slice_1 ... slice_N, winner, outro
#
# CSV format (first line optional meta, then header):
#   # TITLE=AI MARKET SHARE, SUB=Q1 2024, TOTAL_LABEL=TOTAL
#   Category,Value,Color
#   Nvidia,35,#00F0FF

import os
import sys
import json
import math
from pathlib import Path
from typing import List, Dict

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
        def play_intro(scene, brand_title="BIGDATA LEAK", brand_sub="MARKET BREAKDOWN",
                       feed_text="FEED_DONUT // BREAKDOWN", footer_text="CONFIDENTIAL // VERIFIED"):
            t1 = Text(brand_title, font="Montserrat", weight=BOLD, font_size=42, color=WHITE).move_to(UP * 0.5)
            t2 = Text(brand_sub, font="Consolas", font_size=18, color=GREY_B).next_to(t1, DOWN, buff=0.2)
            scene.play(FadeIn(t1, shift=UP * 0.1), FadeIn(t2), run_time=0.85, rate_func=rf.ease_out_cubic)
            scene.play(FadeOut(t1), FadeOut(t2), run_time=0.40, rate_func=rf.ease_in_out_sine)

# --- SYNC HELPERS ---
from src.sync.job import load_job
from src.sync.timeline import Timeline, clamp
from src.sfx.engine import SFXEngine
try:
    from src.sync.retention import hold_breathing, register_template_accent
    from src.sync.retention_accents import retain_accent_donut
except Exception:
    def hold_breathing(scene, seconds: float, focus=None, text: str = ""):
        if seconds > 0:
            scene.wait(seconds)
    def register_template_accent(scene, fn):
        pass
    def retain_accent_donut(scene, focus, seconds, **kw):
        return lambda: None


SLICE_PALETTE = [
    "#00F0FF", "#FF0055", "#BD00FF", "#FFE14D",
    "#00FF66", "#FF9900", "#3388FF", "#FF6EC7",
]


def _parse_meta(path: str) -> dict:
    meta = {"TITLE": "MARKET BREAKDOWN", "SUB": "Share Distribution", "TOTAL_LABEL": "TOTAL"}
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


def load_donut_csv(csv_path: str):
    meta = _parse_meta(csv_path)
    if not os.path.exists(csv_path):
        categories = ["Nvidia", "Microsoft", "Google", "Apple", "Others"]
        values     = [35.0, 22.0, 18.0, 15.0, 10.0]
        colors     = SLICE_PALETTE[:5]
        return meta, categories, values, colors

    df = pd.read_csv(csv_path, comment="#")
    df.columns = [c.strip().title() for c in df.columns]
    for required in ("Category", "Value"):
        if required not in df.columns:
            raise ValueError(f"donut_breakdown CSV missing column: {required}")

    df["Category"] = df["Category"].astype(str).str.strip()
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0.0)
    df = df[df["Value"] > 0].head(8).reset_index(drop=True)

    if "Color" in df.columns:
        raw_colors = df["Color"].astype(str).str.strip().tolist()
        colors = [c if c.startswith("#") else SLICE_PALETTE[i % len(SLICE_PALETTE)]
                  for i, c in enumerate(raw_colors)]
    else:
        colors = [SLICE_PALETTE[i % len(SLICE_PALETTE)] for i in range(len(df))]

    return meta, df["Category"].tolist(), df["Value"].tolist(), colors


class DonutBreakdownFinal(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR

        # ✅ 0.0s Intro Rule
        global_start_t0 = float(self.time)

        # Job + Timeline
        job = load_job(default={"template_id": "donut_breakdown", "timeline": {}})
        job_dir_env = os.environ.get("JOB_DIR", "")
        job_json_path = os.environ.get("JOB_JSON_PATH", "")
        job_dir = job_dir_env or (os.path.dirname(job_json_path) if job_json_path else project_root)

        sfx = SFXEngine(self, job_dir)
        timeline_dict = job.get("timeline", {}) if isinstance(job.get("timeline"), dict) else {}

        csv_path = job.get("data_csv") or "data/donut_data.csv"
        if not os.path.isabs(csv_path):
            csv_path = os.path.join(job_dir, csv_path)
        meta, categories, values, colors = load_donut_csv(csv_path)

        n = len(categories)
        total = sum(values)
        slice_segs = [f"slice_{i + 1}" for i in range(n)]

        # Derive all slice_* segments from audio.order so ghost padding covers all audio slots.
        # Without this, range(n, len(slice_segs)) is always range(n, n) = empty — the bug.
        _audio_cfg = job.get("audio") if isinstance(job, dict) else {}
        _audio_order = _audio_cfg.get("order", []) if isinstance(_audio_cfg, dict) else []
        _all_slice_segs = [s for s in _audio_order if isinstance(s, str) and s.startswith("slice_")]
        if not _all_slice_segs:
            _all_slice_segs = slice_segs  # fallback: audio.order absent, no ghost padding needed

        defaults = {"hook": 2.5, "setup": 2.0, "winner": 3.0, "outro": 1.5}
        for seg in _all_slice_segs:  # cover ALL audio-order slice segments, not just CSV ones
            defaults[seg] = 2.2
        TL = Timeline.from_dict(timeline_dict, defaults=defaults)

        sf = get_safe_frame(margin=0.70)

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
        for x in np.arange(sf["left"], sf["right"] + 0.01, 0.90):
            grid.add(Line([x, sf["bottom"], 0], [x, sf["top"], 0]).set_stroke(Theme.NEON_BLUE, 1, 0.030))
        for y in np.arange(sf["bottom"], sf["top"] + 0.01, 0.90):
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
        title = Text((meta.get("TITLE") or "MARKET BREAKDOWN").upper(),
                     font="Montserrat", weight=BOLD, font_size=40, color=WHITE)
        title.to_edge(UP, buff=0.72).set_z_index(500)

        sub = Text((meta.get("SUB") or "Share Distribution").upper(),
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
        # DONUT CHART
        # ============================================================
        OUTER_R = 2.55
        INNER_R = 1.48
        donut_center = np.array([0.0, -0.50, 0.0])

        # Radial-lift accent — direction inferred from (focus.center - donut_center)
        register_template_accent(
            self,
            lambda s, f, t, dc=donut_center: retain_accent_donut(s, f, t, donut_center=dc),
        )

        proportions = [v / total for v in values]

        slices: List[AnnularSector] = []
        glow_slices: List[AnnularSector] = []
        start_a = PI / 2

        for ang_frac, col in zip(proportions, colors):
            ang = ang_frac * TAU
            sector = AnnularSector(
                inner_radius=INNER_R, outer_radius=OUTER_R,
                angle=max(0.01, ang - 0.018),
                start_angle=start_a,
                fill_color=col, fill_opacity=0.88, stroke_width=0,
            ).shift(donut_center).set_z_index(60)
            slices.append(sector)

            glow_s = AnnularSector(
                inner_radius=INNER_R - 0.10, outer_radius=OUTER_R + 0.10,
                angle=max(0.01, ang - 0.018),
                start_angle=start_a,
                fill_color=col, fill_opacity=0.18, stroke_width=0,
            ).shift(donut_center).set_z_index(55)
            glow_slices.append(glow_s)

            start_a += ang

        # Inner ring (donut hole)
        inner_ring = Circle(radius=INNER_R - 0.06).shift(donut_center)
        inner_ring.set_fill(BACKGROUND_COLOR, 1.0).set_stroke(width=0).set_z_index(65)
        inner_ring_accent = Circle(radius=INNER_R + 0.06).shift(donut_center)
        inner_ring_accent.set_fill(opacity=0).set_stroke(WHITE, 1.5, 0.08).set_z_index(64)

        total_label = Text(meta.get("TOTAL_LABEL", "TOTAL"), font="Consolas",
                           font_size=16, color=Theme.TEXT_SUB).shift(donut_center + UP * 0.28).set_z_index(70)
        total_val = Text(f"{int(round(total))}", font="Montserrat", weight=BOLD,
                         font_size=36, color=WHITE).shift(donut_center + DOWN * 0.10).set_z_index(70)
        self.add(inner_ring, inner_ring_accent, total_label, total_val)

        # Labels around donut
        LABEL_R = OUTER_R + 0.75
        label_mobs: List[VGroup] = []
        tick_lines = VGroup()
        start_a = PI / 2
        for i, (ang_frac, cat, val, col) in enumerate(zip(proportions, categories, values, colors)):
            ang = ang_frac * TAU
            mid_a = start_a + ang / 2
            lx = donut_center[0] + LABEL_R * math.cos(mid_a)
            ly = donut_center[1] + LABEL_R * math.sin(mid_a)

            pct = val / total * 100
            cat_t = Text(cat.upper(), font="Consolas", font_size=15, color=col, weight=BOLD)
            val_t = Text(f"{pct:.1f}%", font="Montserrat", font_size=19, color=WHITE, weight=BOLD)
            lbl = VGroup(cat_t, val_t).arrange(DOWN, buff=0.05)
            lbl.move_to([lx, ly, 0]).set_z_index(80)
            label_mobs.append(lbl)

            r0 = OUTER_R + 0.07
            r1 = OUTER_R + 0.44
            p0 = donut_center + np.array([r0 * math.cos(mid_a), r0 * math.sin(mid_a), 0])
            p1 = donut_center + np.array([r1 * math.cos(mid_a), r1 * math.sin(mid_a), 0])
            tick_lines.add(Line(p0, p1).set_stroke(col, 2, 0.60).set_z_index(75))
            start_a += ang

        for sl, gl in zip(slices, glow_slices):
            sl.set_opacity(0)
            gl.set_opacity(0)
            self.add(gl, sl)
        for lbl in label_mobs:
            lbl.set_opacity(0)
            self.add(lbl)
        tick_lines.set_opacity(0)
        self.add(tick_lines)

        # ============================================================
        # INTRO
        # ============================================================
        try:
            IntroManager.play_intro(
                self, brand_title="BIGDATA LEAK", brand_sub="MARKET BREAKDOWN",
                feed_text="FEED_DONUT // BREAKDOWN", footer_text="CONFIDENTIAL // VERIFIED",
            )
        except Exception:
            pass

        # ============================================================
        # HOOK — header in + donut ring appears
        # ============================================================
        hook_t0 = global_start_t0
        sfx.mark("riser", gain_db=-8, meta={"at": "hook_in"})

        self.play(
            FadeIn(title, shift=DOWN * 0.18),
            FadeIn(sub, shift=DOWN * 0.12),
            FadeIn(underline, shift=DOWN * 0.08),
            FadeIn(underline_glow, shift=DOWN * 0.08),
            run_time=0.75, rate_func=rf.ease_out_cubic,
        )

        sfx.mark("sweep", gain_db=-10, meta={"at": "donut_reveal"})
        self.play(
            *[sl.animate.set_opacity(0.88) for sl in slices],
            *[gl.animate.set_opacity(0.18) for gl in glow_slices],
            FadeIn(tick_lines),
            run_time=1.05, rate_func=rf.ease_out_cubic,
        )

        TL.consume("hook", float(self.time) - hook_t0)
        hold_breathing(self, TL.remaining("hook"), focus=inner_ring, text="ANALYZING BREAKDOWN")

        # ============================================================
        # SETUP — labels drop in
        # ============================================================
        setup_t0 = float(self.time)
        sfx.mark("scan_tick", gain_db=-14, meta={"at": "setup_labels"})

        self.play(
            *[FadeIn(lbl, shift=UP * 0.08) for lbl in label_mobs],
            run_time=0.85, rate_func=rf.ease_out_cubic,
        )

        TL.consume("setup", float(self.time) - setup_t0)
        hold_breathing(self, TL.remaining("setup"), focus=underline, text="CALIBRATING SLICE DATA")

        # ============================================================
        # SLICE SEGMENTS
        # ============================================================
        for i, seg in enumerate(slice_segs):
            slice_t0 = float(self.time)
            col = colors[i]
            sl = slices[i]
            gl = glow_slices[i]
            lbl = label_mobs[i]
            others_sl  = [s for j, s in enumerate(slices) if j != i]
            others_gl  = [g for j, g in enumerate(glow_slices) if j != i]
            others_lbl = [lb for j, lb in enumerate(label_mobs) if j != i]

            sfx.mark("ui_click", gain_db=-12, meta={"at": "slice_highlight", "i": i + 1})

            t_act = clamp(TL.seg_total(seg, 2.2) * 0.50, 0.35, 1.10)
            self.play(
                sl.animate.scale(1.06),
                gl.animate.set_opacity(0.36),
                lbl.animate.set_color(col).scale(1.06),
                *[s.animate.set_opacity(0.26) for s in others_sl],
                *[g.animate.set_opacity(0.05) for g in others_gl],
                *[lb.animate.set_opacity(0.32) for lb in others_lbl],
                run_time=t_act, rate_func=rf.ease_out_cubic,
            )

            TL.consume(seg, float(self.time) - slice_t0)
            hold_breathing(self, TL.remaining(seg), focus=sl, text=f"SLICE: {categories[i].upper()}")

            # Restore before next slice
            t_rst = min(0.28, max(0.0, TL.remaining(seg) * 0.4))
            if t_rst > 0.04:
                self.play(
                    sl.animate.scale(1 / 1.06),
                    gl.animate.set_opacity(0.18),
                    lbl.animate.set_color(WHITE).scale(1 / 1.06),
                    *[s.animate.set_opacity(0.88) for s in others_sl],
                    *[g.animate.set_opacity(0.18) for g in others_gl],
                    *[lb.animate.set_opacity(1.0) for lb in others_lbl],
                    run_time=t_rst, rate_func=rf.ease_in_out_sine,
                )

        # Ghost padding for extra audio segments beyond CSV row count.
        # _all_slice_segs is from audio.order, so range(n, len(_all_slice_segs))
        # correctly absorbs any slice_* segments the job has beyond what the CSV covers.
        for ghost_i in range(n, len(_all_slice_segs)):
            g_t0 = float(self.time)
            TL.consume(_all_slice_segs[ghost_i], float(self.time) - g_t0)
            hold_breathing(self, TL.remaining(_all_slice_segs[ghost_i]), focus=inner_ring, text="AWAITING DATA...")

        # ============================================================
        # WINNER — largest slice spotlit
        # ============================================================
        winner_t0 = float(self.time)
        wi = int(np.argmax(values))
        win_sl, win_gl, win_lbl = slices[wi], glow_slices[wi], label_mobs[wi]
        win_col = colors[wi]

        sfx.mark("winner_rise", gain_db=-9, meta={"at": "winner_reveal"})

        t_w = clamp(TL.seg_total("winner", 3.0) * 0.48, 0.55, 1.30)
        self.play(
            win_sl.animate.scale(1.10),
            win_gl.animate.set_opacity(0.52),
            win_lbl.animate.set_color(win_col).scale(1.10),
            *[s.animate.set_opacity(0.20) for s in slices if s is not win_sl],
            *[g.animate.set_opacity(0.04) for g in glow_slices if g is not win_gl],
            *[lb.animate.set_opacity(0.24) for lb in label_mobs if lb is not win_lbl],
            run_time=t_w, rate_func=rf.ease_out_back,
        )

        # Winner banner at bottom
        banner = RoundedRectangle(width=sf["w"] * 0.86, height=1.46, corner_radius=0.18)
        banner.set_fill("#000000", 0.88).set_stroke(win_col, 3, 0.90).set_z_index(200)
        banner.move_to([sf["cx"], sf["bottom"] + 1.02, 0])
        banner_glow = banner.copy().set_fill(opacity=0).set_stroke(win_col, 22, 0.22).set_z_index(199)

        pct_str = f"{values[wi] / total * 100:.1f}%"
        banner_txt = VGroup(
            Text(categories[wi].upper(), font="Montserrat", weight=BOLD, font_size=36, color=win_col),
            Text(pct_str, font="Consolas", weight=BOLD, font_size=24, color=WHITE),
            Text("DOMINANT SHARE", font="Consolas", font_size=14, color=Theme.TEXT_SUB),
        ).arrange(DOWN, buff=0.08).move_to(banner).set_z_index(201)

        sfx.mark("impact_soft", gain_db=-11, meta={"at": "winner_banner"})
        self.play(
            FadeIn(banner_glow), GrowFromCenter(banner),
            FadeIn(banner_txt, shift=UP * 0.14),
            run_time=0.68, rate_func=rf.ease_out_cubic,
        )

        TL.consume("winner", float(self.time) - winner_t0)
        hold_breathing(self, TL.remaining("winner"), focus=banner, text="LOCKING WINNER DATA")

        # ============================================================
        # OUTRO
        # ============================================================
        outro_t0 = float(self.time)
        sfx.mark("ui_pop", gain_db=-12, meta={"at": "outro"})
        hold_breathing(self, TL.seg_total("outro", 1.5), focus=banner, text="SYSTEM SHUTDOWN")
        TL.consume("outro", float(self.time) - outro_t0)

        try:
            sfx.flush()
        except Exception:
            pass
