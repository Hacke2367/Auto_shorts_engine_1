from __future__ import annotations

import os
import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    from src.config import DATA_DIR, BACKGROUND_COLOR, Theme, FONT_DISPLAY
    from src.utils import (
        Brand,
        get_safe_frame,
        clamp_x,
        clamp_y,
        make_floating_particles,
        get_branding_border_lines,
        get_cinematic_overlay,
        get_rotating_watermark,
        add_cinematic_background,
        IntroManager,
        build_result_banner,
        fmt_value,
    )
except Exception:
    def fmt_value(v, unit="", currency="", numfmt="intl", decimals=None):
        return f"{currency}{float(v):.1f}{unit}"

    class IntroManager:  # type: ignore
        @staticmethod
        def play_intro(*args, **kwargs):
            return None

    def build_result_banner(*args, **kwargs):
        return VGroup()

    DATA_DIR = "./geo_data"
    BACKGROUND_COLOR = "#050505"
    FONT_DISPLAY = "Montserrat"

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

    def add_cinematic_background(*args, **kwargs):
        return None

# --- PIPELINE HELPERS (direct imports, NO try/except) ---
from src.sync.job import load_job
from src.sync.timeline import Timeline, clamp as tclamp
from src.sync.retention import hold_breathing, banner_scan_hold
from src.sfx.engine import SFXEngine
from src.fx import cold_open, build_loop_card, slam_in


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

    GOLD = getattr(Theme, "NEON_YELLOW", "#FFC74A")  # brand gold (was harsh #FFD700)

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


# ==========================
# META + CSV helpers
# ==========================
@dataclass(frozen=True)
class RaceMeta:
    title: str = "GDP GROWTH RACE"
    subtitle: str = ""  # empty -> no subtitle line (never ship template/dev text)
    feed_text: str = "FEED_RACE // LIVE"
    footer_text: str = "CONFIDENTIAL // VERIFIED"
    topk: int = 5
    max_series: int = 10  # clean by default (user preference)
    unit_suffix: str = "T"
    kicker: str = ""  # optional small line above the title (#KICKER=...)
    source: str = ""  # #SOURCE=... -> "SOURCE: ..." in the HUD
    currency: str = ""  # #CURRENCY=₹ / $
    numfmt: str = "intl"  # #NUMFMT=indian -> lakh/crore


def _parse_meta_lines(path: str) -> Dict[str, str]:
    """
    Supports leading '#KEY=VALUE' lines until first non-# line.
    Keys: TITLE, SUB, FEED, FOOTER, TOPK, MAX_SERIES, UNIT
    """
    meta: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                if not line.startswith("#"):
                    break
                line = line[1:].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().upper()
                v = v.strip()
                if k and v:
                    meta[k] = v
    except Exception:
        pass
    return meta


def _resolve_race_meta(meta: Dict[str, str]) -> RaceMeta:
    def _int(key: str, default: int) -> int:
        try:
            return int(float(meta.get(key, default)))
        except Exception:
            return default

    title = meta.get("TITLE", RaceMeta.title)
    subtitle = meta.get("SUB", meta.get("SUBTITLE", RaceMeta.subtitle))
    feed_text = meta.get("FEED", meta.get("FEED_TEXT", RaceMeta.feed_text))
    footer_text = meta.get("FOOTER", meta.get("FOOTER_TEXT", RaceMeta.footer_text))
    topk = max(1, _int("TOPK", RaceMeta.topk))
    max_series = max(1, _int("MAX_SERIES", RaceMeta.max_series))
    unit_suffix = meta.get("UNIT", RaceMeta.unit_suffix)
    kicker = meta.get("KICKER", RaceMeta.kicker)
    source = meta.get("SOURCE", RaceMeta.source)
    currency = meta.get("CURRENCY", RaceMeta.currency)
    numfmt = meta.get("NUMFMT", RaceMeta.numfmt)
    return RaceMeta(
        title=title,
        subtitle=subtitle,
        feed_text=feed_text,
        footer_text=footer_text,
        topk=topk,
        max_series=max_series,
        unit_suffix=unit_suffix,
        kicker=kicker,
        source=source,
        currency=currency,
        numfmt=numfmt,
    )


def _find_race_csv(job: Optional[Dict[str, Any]] = None, job_dir: Optional[Path] = None) -> Optional[str]:
    candidates: List[str] = []

    if isinstance(job, dict):
        rel = str(job.get("data_csv", "")).strip()
        if rel:
            p = Path(rel)
            if not p.is_absolute():
                base = job_dir if job_dir is not None else _resolve_job_dir()
                p = (base / p).resolve()
            candidates.append(str(p))

    if job_dir is not None:
        candidates.append(str((job_dir / "data" / "race_data.csv").resolve()))

    candidates.extend(
        [
            os.path.join(DATA_DIR, "race_data.csv"),
            os.path.join(project_root, "geo_data", "race_data.csv"),
            os.path.join(current_dir, "geo_data", "race_data.csv"),
            os.path.join(current_dir, "race_data.csv"),
            os.path.join(project_root, "race_data.csv"),
            "race_data.csv",
        ]
    )
    seen = set()
    ordered = [p for p in candidates if not (p in seen or seen.add(p))]
    return next((p for p in ordered if os.path.exists(p)), None)


def _load_race_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#")
    df.columns = df.columns.str.strip()
    # year column = first column; rest numeric
    if df.shape[1] < 2:
        raise ValueError("race_data.csv must have at least 2 columns: Year + 1 series.")
    # coerce numbers safely
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df[df.columns[0]] = pd.to_numeric(df[df.columns[0]], errors="coerce").fillna(0.0)
    df = df.dropna().reset_index(drop=True)
    return df


def _resolve_job_dir() -> Path:
    job_dir_env = os.environ.get("JOB_DIR", "").strip()
    if job_dir_env:
        return Path(job_dir_env).resolve()

    job_json_path = os.environ.get("JOB_JSON_PATH", "").strip()
    if job_json_path:
        return Path(job_json_path).resolve().parent

    return Path(project_root).resolve()


def _extract_audio_order(job: Dict[str, Any]) -> List[str]:
    audio = job.get("audio")
    if not isinstance(audio, dict):
        return []
    order = audio.get("order")
    if not isinstance(order, list):
        return []
    out: List[str] = []
    for x in order:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def _default_segment_order() -> List[str]:
    return ["hook", "setup", "lap_1", "lap_2", "sprint", "finish", "outro"]


def _segment_defaults(order: List[str]) -> Dict[str, float]:
    defaults: Dict[str, float] = {}
    if not order:
        order = _default_segment_order()

    n = len(order)
    for i, seg in enumerate(order):
        if i == 0:
            defaults[seg] = 2.6
        elif i == 1:
            defaults[seg] = 2.0
        elif i == n - 1:
            defaults[seg] = 1.4
        elif i == n - 2 and n >= 5:
            defaults[seg] = 2.3
        else:
            defaults[seg] = 2.8
    return defaults


def _segment_roles(order: List[str]) -> Tuple[str, Optional[str], List[str], Optional[str], Optional[str]]:
    seq = list(order) if order else _default_segment_order()
    hook = seq[0]
    setup = seq[1] if len(seq) > 1 else None

    race: List[str] = []
    finish: Optional[str] = None
    outro: Optional[str] = None

    if len(seq) >= 5:
        race = seq[2:-2]
        finish = seq[-2]
        outro = seq[-1]
    elif len(seq) == 4:
        race = [seq[2]]
        outro = seq[3]
    elif len(seq) == 3:
        race = [seq[2]]

    return hook, setup, race, finish, outro


class SFXMarksWriter:
    def __init__(self, scene: Scene, job_dir: Path, template_id: str = "scan_race"):
        self.scene = scene
        self.template_id = template_id
        self.out_path = job_dir / "output" / "sfx_marks.json"
        self.marks: List[Dict[str, Any]] = []

    def mark(self, key: str, gain_db: float = 0.0, offset: float = 0.0, meta: Optional[Dict[str, Any]] = None):
        t = float(getattr(self.scene, "time", 0.0)) + float(offset)
        ev: Dict[str, Any] = {"t": t, "key": str(key), "gain_db": float(gain_db)}
        if isinstance(meta, dict) and meta:
            ev["meta"] = meta
        self.marks.append(ev)

    def flush(self):
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "template_id": self.template_id, "marks": self.marks}
        with self.out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


class CinematicLineRace(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR if "BACKGROUND_COLOR" in globals() else Design.BG
        add_cinematic_background(self, accent=getattr(Brand, "CYAN", "#00F0FF"))

        job = load_job(default={"template_id": "scan_race", "timeline": {}, "audio": {"order": []}})
        job_dir = _resolve_job_dir()
        timeline_dict = job.get("timeline", {}) if isinstance(job.get("timeline"), dict) else {}
        audio_order = _extract_audio_order(job)
        if not audio_order:
            audio_order = _default_segment_order()

        TL = Timeline.from_dict(timeline_dict, defaults=_segment_defaults(audio_order))
        TL.schedule(audio_order)
        scene_t0 = float(self.time)
        hook_seg, setup_seg, race_segments, finish_seg, outro_seg = _segment_roles(audio_order)
        sfx = SFXEngine(self, job_dir)

        csv_path = _find_race_csv(job=job, job_dir=job_dir)
        meta = RaceMeta()
        raw_meta: Dict[str, str] = {}
        if csv_path:
            raw_meta = _parse_meta_lines(csv_path)
            meta = _resolve_race_meta(raw_meta)

        def fmtv(v: float) -> str:
            return fmt_value(v, meta.unit_suffix, meta.currency, meta.numfmt)

        def _pad_segment(name: Optional[str], focus: Optional[Mobject] = None, text: str = "EXPLANATION IN PROGRESS"):
            if not name:
                return
            # Hold until this segment's ABSOLUTE end on the master clock. The old
            # relative remaining() hold let every overrun push all later segments late.
            rem = TL.target_elapsed(name) - (float(self.time) - scene_t0)
            if rem > 0.001:
                hold_breathing(self, rem, focus=focus, text=text)
            TL.consume(name, TL.remaining(name))

        # ==========================================
        # 1) INTRO (NO OVERLAP, NO RE-APPEAR)
        # ==========================================
        hook_total = TL.seg_total(hook_seg, 2.6)
        hook_action_target = max(0.90, hook_total * 0.82)
        hook_scale = tclamp(hook_action_target / 2.55, 0.55, 1.45)
        hook_t0 = float(self.time)

        # Standard brand intro, identical to the other six templates. The hand-rolled
        # copy that lived here had drifted (letters written on, white flashes, offset
        # positions, different border reveal). IntroManager reports its SFX through
        # scene.sfx_mark, so route that to this scene's engine.
        self.sfx_mark = lambda key, gain_db=0.0, offset=0.0, meta=None: sfx.mark(
            key, offset=offset, gain_db=gain_db, meta=meta
        )
        IntroManager.play_intro(
            self,
            brand_title="BIGDATA LEAK",
            brand_sub="SYSTEM BREACH DETECTED",
            feed_text=meta.feed_text,
            footer_text=meta.footer_text,
        )
        getattr(IntroManager, "set_source", lambda *a, **k: None)(self, meta.source)
        _cold = cold_open(self, raw_meta, 0.4, hook_total, font=FONT_DISPLAY, gold=Design.GOLD, white=Design.TEXT_MAIN)
        if _cold > 0:
            hook_scale = tclamp(max(0.5, hook_total - _cold) * 0.82 / 2.55, 0.30, 1.45)

        # ==========================================
        # 2) SAFE FRAME + DATA
        # ==========================================
        sf = get_safe_frame(margin=0.70)

        if csv_path:
            df = _load_race_df(csv_path)
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
        labels_all = list(df.columns[1:])

        # clutter control: keep clean by default, allow meta override
        max_series = int(max(1, meta.max_series))
        if len(labels_all) > max_series:
            last_row = df.iloc[-1, 1:].astype(float)
            order = list(last_row.sort_values(ascending=False).index)
            labels = order[:max_series]
        else:
            labels = labels_all

        series = {c: df[c].values.astype(float) for c in labels}

        min_year, max_year = float(np.min(years)), float(np.max(years))
        raw_max = float(df[labels].max().max()) if labels else 0.0
        raw_min = float(df[labels].min().min()) if labels else 0.0
        # ~6 gridlines at a 1/2/2.5/5 x 10^k step, whatever the scale (a fixed
        # 25 cap drew ~200 gridlines on 5,000-range data). Negative data gets a
        # negative floor instead of plotting below the axis.
        _span = max(raw_max, 0.0) - min(raw_min, 0.0) or 5.0
        _raw = _span / 6.0
        _mag = 10.0 ** np.floor(np.log10(_raw))
        y_step = next(m * _mag for m in (1, 2, 2.5, 5, 10) if _raw <= m * _mag)
        y_max = float(np.ceil(raw_max / y_step) * y_step) if raw_max > 0 else y_step
        y_min = float(np.floor(raw_min / y_step) * y_step) if raw_min < 0 else 0.0

        TOPK = int(max(1, meta.topk))
        TOPK = min(TOPK, max(1, len(labels)))  # ✅ freeze-safe

        self.tracker = ValueTracker(min_year)
        self.current_ranks = {c: 99 for c in labels}

        def interp_value(c: str, t: float) -> float:
            # ✅ freeze-safe: handle 1-row geo_data
            if len(years) < 2:
                return float(series[c][0]) if len(series[c]) else 0.0
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

        # layered ambient glow textures (subtle, non-distracting)
        glow_a = Circle(radius=max(2.8, sf["w"] * 0.36)).set_stroke(width=0)
        glow_a.set_fill(color=Design.CYAN, opacity=0.045).set_z_index(2)
        glow_a.move_to([sf["left"] + 1.0, sf["top"] - 1.4, 0])

        glow_b = Circle(radius=max(3.2, sf["w"] * 0.40)).set_stroke(width=0)
        glow_b.set_fill(color=Design.PINK, opacity=0.035).set_z_index(2)
        glow_b.move_to([sf["right"] - 0.9, sf["bottom"] + 1.8, 0])

        self.add(glow_a, glow_b)

        glow_a.add_updater(lambda m, dt: m.rotate(0.03 * dt).shift(RIGHT * (0.01 * np.sin(self.time * 0.9))))
        glow_b.add_updater(lambda m, dt: m.rotate(-0.025 * dt).shift(UP * (0.008 * np.cos(self.time * 1.1))))

        # ==========================================
        # 4) HEADER
        # ==========================================
        header_y = sf["top"] - 0.75

        # Kicker comes from the CSV (#KICKER=...). It used to be hardcoded to
        # "LIVE ECONOMIC TRACKER", which is wrong for any non-economy race.
        kicker = Text(meta.kicker or " ", font="Montserrat", weight=BOLD, font_size=16, color=Design.GOLD)
        kicker.set_opacity(0.82).set_z_index(60)
        kicker.move_to([sf["cx"], header_y + 0.44, 0])

        title = Text(meta.title, font=FONT_DISPLAY, weight=BOLD, font_size=42, color=Design.TEXT_MAIN)
        if title.width > sf["w"]:  # long titles shrink to the safe width, never off-frame
            title.scale_to_fit_width(sf["w"])
        title.move_to([sf["cx"], header_y, 0]).set_z_index(60)
        title_shadow = title.copy().set_color(BLACK).set_opacity(0.30).shift(DOWN * 0.05 + RIGHT * 0.04).set_z_index(59)

        underline = Line(LEFT * 2.8, RIGHT * 2.8)
        underline.set_stroke(width=4, color=[Design.PINK, Design.CYAN])
        underline.next_to(title, DOWN, buff=0.18).set_z_index(60)

        scan_dot = Dot(color=WHITE, radius=0.07).move_to(underline.get_left()).set_z_index(61)

        def _scan(m, dt):
            tt = (np.sin(self.time * 2.0) + 1) / 2
            m.move_to(underline.get_left() + (underline.get_right() - underline.get_left()) * tt)

        scan_dot.add_updater(_scan)

        subtitle = Text(meta.subtitle or " ", font="Montserrat", font_size=18, color=Design.TEXT_SUB)
        subtitle.next_to(underline, DOWN, buff=0.20).set_z_index(60)
        subtitle_shadow = subtitle.copy().set_color(BLACK).set_opacity(0.24).shift(DOWN * 0.04 + RIGHT * 0.03).set_z_index(59)
        self.add(title_shadow, subtitle_shadow)

        sfx.mark("charge_up", gain_db=-10, meta={"at": "header"})
        self.play(
            FadeIn(kicker, shift=UP * 0.08, run_time=0.28 * hook_scale),
            Write(title, run_time=0.55 * hook_scale),
            GrowFromCenter(underline, run_time=0.55 * hook_scale),
            FadeIn(scan_dot, run_time=0.20 * hook_scale),
            FadeIn(subtitle, shift=UP * 0.1, run_time=0.45 * hook_scale),
        )
        TL.consume(hook_seg, float(self.time) - hook_t0)
        _pad_segment(hook_seg, focus=underline, text="SCANNING LIVE FEED")

        # ==========================================
        # 5) GLASS DOCK (TOP-LEFT under header)
        # ==========================================
        setup_total = TL.seg_total(setup_seg or "setup", 2.0)
        setup_action_target = max(0.80, setup_total * 0.82)
        setup_scale = tclamp(setup_action_target / 1.45, 0.55, 1.45)
        setup_t0 = float(self.time)

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
        # next_to only: aligning the title to the strip's left edge put it on top of the
        # blinking live dot ("LIVE" read with a green blob over the L).
        dock_title.next_to(live_dot, RIGHT, buff=0.10)

        sfx.mark("ui_pop", gain_db=-12, meta={"at": "dock_in"})
        self.play(
            FadeIn(panel_glow),
            FadeIn(panel),
            FadeIn(strip),
            FadeIn(live_dot),
            FadeIn(dock_title),
            run_time=0.45 * setup_scale,
        )

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

        # slots for TOPK (dynamic)
        slot_gap = (rail_top - rail_bottom) / TOPK
        slot_ys = [rail_top - slot_gap * (i + 0.5) for i in range(TOPK)]

        color_map = {c: RACE_COLORS[i % len(RACE_COLORS)] for i, c in enumerate(labels)}

        # The dock is on screen for the whole setup segment before the race starts, so
        # seed each slot with the real first-year ranking instead of "1 COUNTRY 0.0T".
        first_ranking = sorted(labels, key=lambda c: float(series[c][0]), reverse=True)[:TOPK]

        def _fit_slot_name(nm, badge, vt):
            """Left-align a ranking name just right of its rank badge and shrink it to
            the gap before the value. Centering it at a fixed x let long names
            ("UNITED STATES", "UNITED KINGDOM") slide under the badge."""
            left = badge.get_right()[0] + 0.12
            max_w = (vt.get_left()[0] - 0.15) - left
            if nm.width > max_w > 0.2:
                nm.scale_to_fit_width(max_w)
            nm.move_to([left + nm.width / 2, badge.get_center()[1], 0])

        def make_slot_card(y, i):
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

            c0 = first_ranking[i] if i < len(first_ranking) else ""
            rank_txt = Text(str(i + 1), font="Montserrat", weight=BOLD, font_size=16, color=WHITE).move_to(badge).set_z_index(47)

            val_str = fmtv(series[c0][0]) if c0 else " "
            val_txt = Text(val_str, font="Montserrat", weight=BOLD, font_size=13, color=Design.CYAN).set_z_index(47)
            val_txt.move_to(body.get_right() + LEFT * 0.40)

            name_txt = Text(str(c0).upper() or " ", font="Montserrat", weight=BOLD, font_size=13, color=WHITE).set_z_index(47)
            _fit_slot_name(name_txt, badge, val_txt)

            if c0:
                accent.set_fill(color_map[c0], opacity=0.9)
                badge.set_stroke(color_map[c0], width=2, opacity=0.85)

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

        slot_cards = [make_slot_card(y, i) for i, y in enumerate(slot_ys)]
        sfx.mark("ui_tick", gain_db=-13, meta={"at": "slots_in"})
        self.play(
            LaggedStart(
                *[FadeIn(c["group"], shift=RIGHT * 0.08) for c in slot_cards],
                lag_ratio=0.08,
                run_time=0.55 * setup_scale,
                rate_func=rf.ease_out_cubic,
            )
        )

        # ==========================================
        # 6) FULL-WIDTH PLOT (UNDER DOCK)
        # ==========================================
        plot_top = panel.get_bottom()[1] - 0.35
        plot_bottom = sf["bottom"] + 0.70

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
            y_range=[y_min, y_max, y_step],
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
        for v in np.arange(y_min + y_step, y_max + y_step * 0.01, y_step):
            leftp = ax.c2p(min_year, v)
            rightp = ax.c2p(max_year + 2, v)
            ln = DashedLine(leftp, rightp, dash_length=0.18, dashed_ratio=0.6)
            ln.set_stroke(color=Design.CYAN, width=1.2, opacity=0.10)
            guides.add(ln)

        x_labels = VGroup()
        for yr in range(int(min_year), int(max_year) + 1, 5):
            pos = ax.c2p(yr, y_min)
            lbl = Text(str(yr), font="Montserrat", weight=BOLD, font_size=13, color=Design.TEXT_SUB)
            lbl.next_to(pos, DOWN, buff=0.20)
            x_labels.add(lbl)

        y_labels = VGroup()
        for v in np.arange(y_min, y_max + y_step * 0.01, y_step):
            pos = ax.c2p(min_year, v)
            txt = fmtv(v) if abs(v) > 1e-9 else "0"
            lbl = Text(txt, font="Montserrat", weight=BOLD, font_size=12, color=Design.TEXT_SUB)
            lbl.next_to(pos, LEFT, buff=0.12)
            y_labels.add(lbl)

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

        sfx.mark("scan_tick", gain_db=-14, meta={"at": "axes_in"})
        self.play(
            FadeIn(ax, run_time=0.35 * setup_scale),
            Create(guides, run_time=0.45 * setup_scale),
            FadeIn(x_labels, run_time=0.35 * setup_scale),
            FadeIn(y_labels, run_time=0.35 * setup_scale),
            FadeIn(wm, run_time=0.35 * setup_scale),
        )
        TL.consume(setup_seg or "setup", float(self.time) - setup_t0)
        _pad_segment(setup_seg, focus=ax, text="CALIBRATING RACE TRACK")

        plot_bounds = {"left": plot_left, "right": plot_right, "top": plot_top, "bottom": plot_bottom}

        def clamp_to_plot(x, w=0.0):
            half = float(w) / 2
            return float(np.clip(x, plot_bounds["left"] + half, plot_bounds["right"] - half))

        def clampy_to_plot(y, h=0.0):
            half = float(h) / 2
            return float(np.clip(y, plot_bounds["bottom"] + half, plot_bounds["top"] - half))

        # ==========================================
        # 7) LINE ENGINE + CHIPS + DOCK UPDATE
        # ==========================================
        # Per-frame labels: ~20 Text objects every frame, each a Pango->SVG parse,
        # made the race laps take ~10 s/frame and exhaust RAM. Names/ranks never
        # change and 1-decimal values repeat across frames, so cache and copy.
        _text_cache: Dict[Tuple[str, int, str], Text] = {}

        def ctext(s: str, size: int, color) -> Text:
            key = (s, size, str(color))
            t = _text_cache.get(key)
            if t is None:
                t = _text_cache[key] = Text(s, font="Montserrat", weight=BOLD, font_size=size, color=color)
            return t.copy()

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
                pts.append(ax.c2p(t, interp_value(c, t)))

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

            chips = []
            for (c, v) in top:
                p = ax.c2p(t, v)
                col = color_map[c]
                txt = ctext(fmtv(v), 13, WHITE)
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

                chips.append([c, p, col, box, txt, cx, cy])

            # Vertical repel top-down, then lift the whole stack if it ran past the plot
            # floor. Clamping each chip on its own stacked the lowest ones back on top
            # of each other (4.5T / 4.1T / 4.1T at the end of the race).
            chips.sort(key=lambda k: k[6], reverse=True)
            min_gap = max(0.42, max((ch[3].height for ch in chips), default=0.0) + 0.04)
            for i in range(1, len(chips)):
                prev = chips[i - 1]
                cur = chips[i]
                if prev[6] - cur[6] < min_gap:
                    cur[6] = prev[6] - min_gap
            if chips:
                floor_y = clampy_to_plot(-1e9, chips[-1][3].height) + 0.22  # clear the x-axis arrow
                lift = floor_y - chips[-1][6]
                if lift > 0:
                    for ch in chips:
                        ch[6] += lift
            for ch in chips:
                ch[6] = clampy_to_plot(ch[6], ch[3].height)

            g = VGroup()
            for (c, p, col, box, txt, cx, cy) in chips:
                box.move_to([cx, cy, 0])
                txt.move_to(box)
                end = box.get_left() + RIGHT * 0.02
                conn = Line(p, end).set_stroke(color=col, width=2, opacity=0.55)

                if pulse[c] > 0:
                    ring = Circle(radius=0.10, color=WHITE, stroke_width=3).move_to(p)
                    ring.set_opacity(min(0.9, pulse[c] * 2.2))
                    g.add(ring)

                g.add(conn, box, txt)

            g.set_z_index(25)
            return g

        self.add(always_redraw(chips_group))

        dock_driver = VMobject().set_opacity(0)

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
                    ctext(str(i + 1), 16, WHITE).move_to(badge)
                )

                nm = ctext(str(c).upper(), 13, WHITE)

                vt = ctext(fmtv(v), 13, Design.CYAN)
                vt.move_to(body.get_right() + LEFT * 0.40)

                _fit_slot_name(nm, badge, vt)

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
        # 8) LAUNCH (timeline-driven segments)
        # ==========================================
        # Live leader card in the empty space right of the ranking dock. It tracks the
        # current #1 through the race and turns into the WINNER card at the finish,
        # using the same result card as every other template. Added instantly (no
        # play) so the race segments keep their exact timing.
        room_left = panel.get_right()[0] + 0.20
        room_w = sf["right"] - room_left
        leader_state = {"name": None, "val": None, "t": -1.0}

        def _leader_card(label, name, val):
            card = build_result_banner(
                label, str(name).upper(), fmtv(val),
                width=room_w, accent=Design.GOLD, z=75,
            )
            return card.move_to([room_left + room_w / 2, panel.get_center()[1], 0])

        _first = first_ranking[0] if first_ranking else (labels[0] if labels else "")
        leader_card = _leader_card("LEADER", _first, float(series[_first][0]) if _first else 0.0)

        def _update_leader(m, dt):
            t = float(self.tracker.get_value())
            name, val = max(((c, interp_value(c, t)) for c in labels), key=lambda x: x[1])
            shown = round(float(val), 1)
            now = float(self.time)
            if name == leader_state["name"] and (shown == leader_state["val"] or now - leader_state["t"] < 0.25):
                return
            leader_state.update(name=name, val=shown, t=now)
            m.become(_leader_card("LEADER", name, val))

        if labels:
            leader_card.add_updater(_update_leader)
            self.add(leader_card)

        active_race_segments = list(race_segments)
        if not active_race_segments:
            fallback_seg = finish_seg or outro_seg
            if fallback_seg:
                active_race_segments = [fallback_seg]
                if fallback_seg == finish_seg:
                    finish_seg = None
                elif fallback_seg == outro_seg:
                    outro_seg = None

        if active_race_segments:
            year_targets = np.linspace(min_year, max_year, num=len(active_race_segments) + 1)[1:]
            for i, (seg_name, target_year) in enumerate(zip(active_race_segments, year_targets), start=1):
                seg_total = TL.seg_total(seg_name, 2.8)
                run_t = max(0.35, min(float(seg_total), max(0.65, float(seg_total) * 0.84)))
                lap_t0 = float(self.time)
                sfx.mark("scan_tick", gain_db=-14, meta={"segment": seg_name, "lap": i})
                self.play(
                    self.tracker.animate.set_value(float(target_year)),
                    run_time=run_t,
                    rate_func=linear,
                )
                TL.consume(seg_name, float(self.time) - lap_t0)
                _pad_segment(seg_name, focus=ax, text="PROCESSING TREND SHIFT")
        else:
            self.play(self.tracker.animate.set_value(max_year), run_time=4.0, rate_func=linear)

        if finish_seg:
            finish_t0 = float(self.time)
            final_scores = sorted([(c, float(series[c][-1])) for c in labels], key=lambda x: x[1], reverse=True)
            winner_name = final_scores[0][0] if final_scores else "N/A"

            winner_val = final_scores[0][1] if final_scores else 0.0

            # The live leader card becomes the WINNER card and stays up through finish +
            # outro (the old banner vanished after 0.9s, leaving ~9s with no result).
            leader_card.clear_updaters()
            winner_card = _leader_card("WINNER", winner_name, winner_val)
            sfx.mark("winner_rise", gain_db=-10, meta={"segment": finish_seg})
            self.play(FadeOut(leader_card), FadeIn(winner_card, shift=UP * 0.08), run_time=0.40)
            sfx.mark("impact_soft", gain_db=-13, meta={"segment": finish_seg, "at": "lock_flash"})
            self.play(Flash(slot_cards[0]["body"].get_right(), color=WHITE, line_length=0.45, num_lines=9), run_time=0.22)
            TL.consume(finish_seg, float(self.time) - finish_t0)
            _pad_segment(finish_seg, focus=slot_cards[0]["body"], text="LOCKING FINAL RANKS")

        if outro_seg:
            outro_t0 = float(self.time)
            outro_total = TL.seg_total(outro_seg, 1.4)
            outro_run = max(0.20, min(outro_total, 0.55))
            sfx.mark("ui_pop", gain_db=-12, meta={"segment": outro_seg})
            self.play(
                FadeOut(scan_dot, shift=UP * 0.03),
                FadeOut(kicker, shift=UP * 0.03),
                run_time=outro_run,
                rate_func=rf.ease_in_out_sine,
            )
            if raw_meta.get("OUTRO_Q"):
                # Loop card over a dimmed chart: same look as the cold open.
                loop_card = build_loop_card(raw_meta, "", 0.4, font=FONT_DISPLAY, gold=Design.GOLD, white=Design.TEXT_MAIN)
                veil = Rectangle(width=config.frame_width * 1.1, height=config.frame_height * 1.1)
                veil.set_stroke(width=0).set_fill(BLACK, 0.0).set_z_index(390)
                self.add(veil)
                self.play(veil.animate.set_fill(opacity=0.72), run_time=0.20)
                self.play(slam_in(loop_card, scale=1.6, run_time=0.34))
            TL.consume(outro_seg, float(self.time) - outro_t0)
            _pad_segment(outro_seg, text="FINALIZING OUTPUT")

        for seg_name in audio_order:
            _pad_segment(seg_name, focus=ax if seg_name in active_race_segments else None)

        sfx.flush()
