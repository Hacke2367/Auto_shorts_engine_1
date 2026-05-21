# main.py
from __future__ import annotations

import os
import json
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Captions pipeline entrypoint
from src.captions import run_captions_pipeline


# Built-in fallback registry — used when templates.json is absent or unreadable.
_BUILTIN_TEMPLATE_MAP: Dict[str, Dict[str, str]] = {
    "bar_chart":       {"file": "src/templates/Bar_chart/bar_chart.py",        "scene": "BarChartTemplate"},
    "butterfly_chart": {"file": "src/templates/chart_folder/butterfly_chart.py","scene": "ButterflyChart"},
    "geo_universal":   {"file": "src/templates/map_chart/geo_universal.py",     "scene": "GeoUniversalMap"},
    "scan_race":       {"file": "src/templates/line_chart/scan_race.py",        "scene": "CinematicLineRace"},
    "sort_card":       {"file": "src/templates/Sort_card/sort_card.py",         "scene": "SortCardTribunalFinal"},
    "vs_card":         {"file": "src/templates/Vs_card/vs_card.py",             "scene": "VsCardFinal"},
    "donut_breakdown": {"file": "src/templates/pie_chart/donut_breakdown.py",   "scene": "DonutBreakdownFinal"},
}


def _load_template_map(repo_root: Path) -> Dict[str, Dict[str, str]]:
    """Load template registry from templates.json (project root), merged over built-ins.
    Add new templates to templates.json without editing this file."""
    tpl_file = repo_root / "templates.json"
    if tpl_file.exists():
        try:
            with tpl_file.open("r", encoding="utf-8") as f:
                loaded: Dict[str, Any] = json.load(f)
            # Strip meta keys (e.g. _comment), then merge over built-ins
            entries = {k: v for k, v in loaded.items()
                       if not k.startswith("_") and isinstance(v, dict)
                       and "file" in v and "scene" in v}
            if entries:
                merged = dict(_BUILTIN_TEMPLATE_MAP)
                merged.update(entries)
                print(f"[OK] Loaded template registry from templates.json ({len(merged)} templates)")
                return merged
        except Exception as e:
            print(f"[WARN] Could not read templates.json: {e} — falling back to built-in registry")
    return dict(_BUILTIN_TEMPLATE_MAP)



def _run_ffmpeg(cmd: list) -> None:
    """Run an FFmpeg command. On failure, raise with the captured stderr output."""
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        cmd_str = " ".join(str(c) for c in cmd)
        raise RuntimeError(
            f"FFmpeg failed (exit {result.returncode}).\n"
            f"CMD: {cmd_str}\n"
            f"STDERR:\n{result.stderr[-3000:]}"
        )


def load_json(path: Path) -> Dict[str, Any]:
    """
    Load a JSON file and return as Python dict.
    Used for reading job.json and other config files.
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_job_path(job_dir: Path, maybe_rel: str) -> Path:
    """
    Convert a path string to absolute Path.
    - If already absolute -> return as is
    - If relative -> resolve relative to job_dir
    """
    p = Path(maybe_rel)
    if p.is_absolute():
        return p
    return (job_dir / p).resolve()


def find_rendered_video(media_dir: Path, scene_name: str, quality: str = "") -> Optional[Path]:
    """
    Find the most recently created rendered mp4 for the given Manim scene name.
    Manim writes files under: media_dir/videos/**/<scene_name>.mp4

    Excludes Manim's partial_movie_files/ fragment cache so animation chunks
    are never mistaken for the final render.  If `quality` is provided, emits
    a warning when the resolved file lives in a different quality folder.
    """
    videos = media_dir / "videos"
    if not videos.exists():
        return None

    # Manim quality flag → expected folder name substring
    _QUALITY_MAP = {
        "l": ("480p",),
        "m": ("720p",),
        "h": ("1080p", "1920p"),
        "p": ("2160p", "4K"),
    }

    best: Optional[Path] = None
    best_mtime = -1.0

    for p in videos.rglob(f"{scene_name}.mp4"):
        # Skip animation fragment cache — Manim stores chunks here, not final renders
        if "partial_movie_files" in p.parts:
            continue
        mt = p.stat().st_mtime
        if mt > best_mtime:
            best_mtime = mt
            best = p

    if best is not None and quality:
        expected = _QUALITY_MAP.get(quality, ())
        path_str = str(best)
        if expected and not any(q in path_str for q in expected):
            print(
                f"[WARN] Resolved render quality may not match --quality={quality!r}: {best}. "
                "If this is a stale render from a previous run, delete media/ and re-run."
            )

    return best


def concat_audio_ffmpeg(
    ffmpeg: str,
    audio_paths: List[Path],
    out_path: Path,
    trim_silence: bool = True,
) -> None:
    """
    Concatenate multiple audio segment files in order into one AAC file.
    Output: out_path (AAC)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg, "-y"]
    for p in audio_paths:
        cmd += ["-i", str(p)]

    n = len(audio_paths)
    if trim_silence:
        # Strip leading/trailing silence from each segment before concat.
        # Threshold -50dB, min silence duration 0.02s — removes dead-air gaps
        # between TTS clips without cutting into actual speech.
        _SR = "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB:stop_periods=-1:stop_duration=0.02:stop_threshold=-50dB"
        trim_parts = ";".join([f"[{i}:a]{_SR}[tr{i}]" for i in range(n)])
        concat_inputs = "".join([f"[tr{i}]" for i in range(n)])
        filter_complex = f"{trim_parts};{concat_inputs}concat=n={n}:v=0:a=1[a]"
    else:
        filter_complex = "".join([f"[{i}:a]" for i in range(n)]) + f"concat=n={n}:v=0:a=1[a]"

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[a]",
        "-c:a", "aac",
        "-b:a", "192k",
        str(out_path),
    ]

    _run_ffmpeg(cmd)


def build_sfx_mix_ffmpeg(
    ffmpeg: str,
    repo_root,
    sfx_marks,   # Path OR dict OR list
    out_path,
    global_gain: float = 1.0,
) -> None:
    """
    Build a single SFX track (AAC) using sfx_marks.json.
    Each mark has:
      - key (to resolve sfx file path from registry)
      - t/time (seconds)
      - optional gain_db, offset

    Output: out_path (.aac)
    """
    import json
    from pathlib import Path

    repo_root = Path(repo_root)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    AUDIO_EXTS = {".wav", ".mp3", ".aac", ".m4a", ".ogg", ".flac"}

    # --- Load marks ---
    raw = None
    if isinstance(sfx_marks, (str, Path)):
        p = Path(sfx_marks)
        if not p.exists():
            # No marks -> write short silence to avoid crashes
            cmd = [
                ffmpeg, "-y",
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", "0.10",
                "-c:a", "aac", "-b:a", "192k",
                str(out_path),
            ]
            _run_ffmpeg(cmd)
            print(f"[NOTE] No sfx_marks.json -> wrote silence: {out_path}")
            return

        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = sfx_marks

    if isinstance(raw, dict):
        marks = raw.get("marks", [])
    elif isinstance(raw, list):
        marks = raw
    else:
        marks = []

    if not isinstance(marks, list) or not marks:
        # Empty marks -> safe silence
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "0.10",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ]
        _run_ffmpeg(cmd)
        print(f"[NOTE] sfx_marks.json empty/invalid -> wrote silence: {out_path}")
        return

    # --- Load registry from src.sfx.registry ---
    reg: Dict[str, Any] = {}
    resolver_fn = None
    try:
        from src.sfx import registry as regmod  # type: ignore

        # pick first dict-like registry
        for name in ("SFX_REGISTRY", "REGISTRY", "SFX_MAP", "SFX"):
            if hasattr(regmod, name):
                cand = getattr(regmod, name)
                if isinstance(cand, dict):
                    reg = cand
                    break

        for fn_name in ("resolve", "resolve_sfx", "get_path", "resolve_key"):
            if hasattr(regmod, fn_name) and callable(getattr(regmod, fn_name)):
                resolver_fn = getattr(regmod, fn_name)
                break
    except Exception:
        resolver_fn = None

    def _resolve_path(key: str):
        """Resolve SFX key -> file path + optional base gain_db."""
        base_gain_db = 0.0

        # Function resolver takes priority
        if resolver_fn is not None:
            out = resolver_fn(key)
            if isinstance(out, str):
                rel = out.strip()
                if not rel:
                    return None, base_gain_db
                p = Path(rel)
                if not p.is_absolute():
                    p = (repo_root / p).resolve()
                return p, base_gain_db

            if isinstance(out, dict):
                rel = str(out.get("rel_path", out.get("path", ""))).strip()
                if not rel:
                    return None, base_gain_db
                p = Path(rel)
                if not p.is_absolute():
                    p = (repo_root / p).resolve()
                try:
                    base_gain_db = float(out.get("gain_db", 0.0))
                except Exception:
                    base_gain_db = 0.0
                return p, base_gain_db

        # Dict registry fallback
        if key in reg:
            entry = reg[key]
            if isinstance(entry, str):
                rel = entry.strip()
                if not rel:
                    return None, base_gain_db
                p = Path(rel)
                if not p.is_absolute():
                    p = (repo_root / p).resolve()
                return p, base_gain_db

            if isinstance(entry, dict):
                rel = str(entry.get("rel_path", entry.get("path", ""))).strip()
                if not rel:
                    return None, base_gain_db
                p = Path(rel)
                if not p.is_absolute():
                    p = (repo_root / p).resolve()
                try:
                    base_gain_db = float(entry.get("gain_db", 0.0))
                except Exception:
                    base_gain_db = 0.0
                return p, base_gain_db

        return None, 0.0

    def db_to_lin(db: float) -> float:
        """Convert decibel to linear amplitude multiplier."""
        return 10 ** (db / 20.0)

    # global_gain: treat <=0 as dB, >0 as linear multiplier
    global_lin = db_to_lin(float(global_gain)) if global_gain <= 0 else float(global_gain)

    events = []
    missing = []

    for m in marks:
        if not isinstance(m, dict):
            continue

        key = str(m.get("key", "")).strip()
        if not key:
            continue

        t = m.get("t", m.get("time", None))
        if t is None:
            continue
        try:
            t = float(t)
        except Exception:
            continue

        try:
            offset = float(m.get("offset", 0.0))
        except Exception:
            offset = 0.0

        try:
            gain_db = float(m.get("gain_db", 0.0))
        except Exception:
            gain_db = 0.0

        p, base_gain_db = _resolve_path(key)
        if p is None:
            missing.append(key)
            continue

        # Reject invalid paths / directories / non-audio files
        try:
            p = p.resolve()
        except Exception:
            pass

        if (not p.exists()) or (not p.is_file()) or (p.suffix.lower() not in AUDIO_EXTS):
            missing.append(key)
            continue

        t = max(0.0, t + offset)
        vol = global_lin * db_to_lin(gain_db + base_gain_db)

        events.append({"t": t, "path": p, "vol": float(vol)})

    if not events:
        # No SFX resolved -> silence
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "0.10",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ]
        _run_ffmpeg(cmd)
        uniq = sorted(set(missing))
        if uniq:
            print(f"[WARN] No SFX resolved. Missing keys/path: {uniq}")
        print(f"[NOTE] Wrote silence SFX track: {out_path}")
        return

    events.sort(key=lambda x: x["t"])

    # --- FFmpeg mix: adelay + volume each event + amix ---
    cmd = [ffmpeg, "-y"]
    for ev in events:
        cmd += ["-i", str(ev["path"])]

    parts = []
    mix_inputs = []

    for i, ev in enumerate(events):
        delay_ms = int(round(ev["t"] * 1000.0))
        vol = ev["vol"]
        parts.append(f"[{i}:a]adelay={delay_ms}:all=1,volume={vol:.6f}[s{i}]")
        mix_inputs.append(f"[s{i}]")

    filter_complex = ";".join(parts + [
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=0,"
          f"alimiter=limit=0.98[sfx]"
    ])

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[sfx]",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]

    _run_ffmpeg(cmd)

    uniq = sorted(set(missing))
    if uniq:
        print(f"[WARN] Some SFX keys missing (skipped): {uniq}")

    print(f"[OK] Built SFX mix: {out_path} (events={len(events)})")


def build_bgm_track_ffmpeg(
    ffmpeg: str,
    job_dir: Path,
    audio_order: List[str],
    timeline: Dict[str, float],
    bgm_cfg: Dict[str, Any],
    out_path: Path,
    global_gain_db: float = -20.0,
) -> None:
    """
    Build a single BGM AAC track based on per-segment mapping.
    Uses timeline durations to place each bgm chunk on the full timeline.

    Output: out_path (.aac)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not bool(bgm_cfg.get("enabled", False)):
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "0.10",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ]
        _run_ffmpeg(cmd)
        print(f"[NOTE] BGM disabled -> wrote silence: {out_path}")
        return

    mode = str(bgm_cfg.get("mode", "per_segment")).strip()
    if mode != "per_segment":
        raise ValueError(f"bgm.mode must be 'per_segment' (got: {mode})")

    lib_dir = str(bgm_cfg.get("library_dir", "audio/bgm")).strip()
    lib_root = (job_dir / lib_dir).resolve()

    crossfade = float(bgm_cfg.get("crossfade", 0.25) or 0.0)
    crossfade = max(0.0, crossfade)

    default_cfg = bgm_cfg.get("default") if isinstance(bgm_cfg.get("default"), dict) else {}
    seg_cfgs = bgm_cfg.get("segments") if isinstance(bgm_cfg.get("segments"), dict) else {}

    def _resolve_bgm_path(rel_or_abs: str) -> Path:
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p
        return (lib_root / p).resolve()

    # Build segment start times from timeline
    starts = []
    t = 0.0
    for name in audio_order:
        if name not in timeline:
            raise ValueError(f"timeline missing duration for segment: {name}")
        dur = float(timeline[name])
        starts.append({"name": name, "start": t, "dur": dur})
        t += dur

    total_duration = t

    # Create events
    events = []
    for seg in starts:
        name = seg["name"]
        seg_dur = float(seg["dur"])
        seg_start = float(seg["start"])

        cfg = seg_cfgs.get(name) if isinstance(seg_cfgs.get(name), dict) else None
        if cfg is None:
            cfg = default_cfg if isinstance(default_cfg, dict) else {}

        path_str = str(cfg.get("path", "")).strip()
        if not path_str:
            continue

        bgm_path = _resolve_bgm_path(path_str)
        if not bgm_path.exists() or not bgm_path.is_file():
            print(f"[WARN] BGM file missing -> skipping segment '{name}': {bgm_path}")
            continue

        seg_gain_db = float(cfg.get("gain_db", 0.0) or 0.0)
        gain_db = global_gain_db + seg_gain_db

        events.append({
            "name": name,
            "path": bgm_path,
            "start": seg_start,
            "dur": seg_dur,
            "gain_db": gain_db,
        })

    if not events:
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "0.10",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ]
        _run_ffmpeg(cmd)
        print(f"[WARN] No BGM events resolved -> wrote silence: {out_path}")
        return

    # Loop each bgm input so short mp3 can cover the segment duration
    cmd = [ffmpeg, "-y"]
    for ev in events:
        cmd += ["-stream_loop", "-1", "-i", str(ev["path"])]

    parts = []
    mix_inputs = []

    for i, ev in enumerate(events):
        start_ms = int(round(ev["start"] * 1000.0))
        dur = float(ev["dur"])
        gain_db = float(ev["gain_db"])

        # clamp fade to segment duration
        fi = min(crossfade, max(0.0, dur * 0.35))
        fo = min(crossfade, max(0.0, dur * 0.35))
        fo_st = max(0.0, dur - fo)

        parts.append(
            f"[{i}:a]"
            f"aformat=channel_layouts=stereo,aresample=44100,"
            f"atrim=0:{dur:.6f},asetpts=PTS-STARTPTS,"
            f"volume={gain_db:.3f}dB,"
            f"afade=t=in:st=0:d={fi:.6f},"
            f"afade=t=out:st={fo_st:.6f}:d={fo:.6f},"
            f"adelay={start_ms}:all=1"
            f"[b{i}]"
        )
        mix_inputs.append(f"[b{i}]")

    parts.append(
        "".join(mix_inputs) +
        f"amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=0,"
        f"atrim=0:{total_duration:.6f},"
        f"alimiter=limit=0.98[bgm]"
    )

    filter_complex = ";".join(parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[bgm]",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]

    _run_ffmpeg(cmd)
    print(f"[OK] Built BGM track: {out_path} (events={len(events)}, dur={total_duration:.2f}s)")


def mix_voice_sfx_bgm_ffmpeg(
    ffmpeg: str,
    voice_path: Path,
    sfx_path: Optional[Path],
    bgm_path: Optional[Path],
    out_path: Path,
    voice_gain: float = 1.0,
    sfx_gain: float = 1.0,
    preset: str = "punchy",
    duck_sfx: bool = False,
    duck_bgm: bool = True,
    duck_amount: str = "strong",
    debug: bool = False,
) -> None:
    """
    Final audio mix:
      voice + optional sfx + optional bgm
    Applies:
      - voice compression
      - sfx EQ (optional duck by voice)
      - bgm EQ (optional duck by voice)
      - limiter

    Output: out_path (.aac)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def db_to_lin(db: float) -> float:
        return 10 ** (db / 20.0)

    if preset == "balanced":
        VOICE_BASE_DB = -1.0
        SFX_BASE_DB = +10.0
        SFX_DUCK_TH, SFX_DUCK_RT, SFX_DUCK_ATK, SFX_DUCK_REL = 0.12, 6.0, 8.0, 220.0
    else:
        VOICE_BASE_DB = -2.0
        SFX_BASE_DB = +14.0
        SFX_DUCK_TH, SFX_DUCK_RT, SFX_DUCK_ATK, SFX_DUCK_REL = 0.10, 8.0, 5.0, 180.0

    da = (duck_amount or "strong").lower().strip()
    if da == "light":
        BGM_DUCK_TH, BGM_DUCK_RT, BGM_DUCK_ATK, BGM_DUCK_REL = 0.14, 4.0, 12.0, 320.0
    elif da == "medium":
        BGM_DUCK_TH, BGM_DUCK_RT, BGM_DUCK_ATK, BGM_DUCK_REL = 0.12, 6.0, 8.0, 260.0
    else:
        BGM_DUCK_TH, BGM_DUCK_RT, BGM_DUCK_ATK, BGM_DUCK_REL = 0.10, 10.0, 5.0, 220.0

    voice_lin = float(voice_gain) * db_to_lin(VOICE_BASE_DB)
    sfx_lin = float(sfx_gain) * db_to_lin(SFX_BASE_DB)

    # Inputs: voice always present, sfx/bgm optional
    cmd = [ffmpeg, "-y", "-i", str(voice_path)]
    if sfx_path is not None:
        cmd += ["-i", str(sfx_path)]
    if bgm_path is not None:
        cmd += ["-i", str(bgm_path)]

    sfx_i = 1 if (sfx_path is not None) else None
    bgm_i = (2 if (sfx_path is not None and bgm_path is not None) else (1 if bgm_path is not None else None))

    filters: List[str] = []

    # Voice processing + split for sidechain
    filters.append(
        f"[0:a]"
        f"aformat=channel_layouts=stereo,aresample=44100,"
        f"pan=stereo|c0=c0|c1=c0,"
        f"volume={voice_lin:.6f},"
        f"acompressor=threshold=-18dB:ratio=3:attack=5:release=120:makeup=1"
        f"[v0]"
    )
    # Voice processing + split for sidechain (only if needed)
    need_sc = (duck_sfx and (sfx_i is not None)) or (duck_bgm and (bgm_i is not None))

    if need_sc:
        filters.append("[v0]asplit=2[v_mix][v_sc]")
    else:
        # no ducking needed -> no sidechain branch
        filters.append("[v0]anull[v_mix]")

    mix_inputs = ["[v_mix]"]

    # SFX processing
    if sfx_i is not None:
        filters.append(
            f"[{sfx_i}:a]"
            f"aformat=channel_layouts=stereo,aresample=44100,"
            f"highpass=f=80,lowpass=f=14000,"
            f"volume={sfx_lin:.6f}"
            f"[s0]"
        )
        if duck_sfx:
            filters.append(
                f"[s0][v_sc]"
                f"sidechaincompress=threshold={SFX_DUCK_TH}:ratio={SFX_DUCK_RT}:attack={SFX_DUCK_ATK}:release={SFX_DUCK_REL}:makeup=1"
                f"[s]"
            )
        else:
            filters.append("[s0]anull[s]")

        mix_inputs.append("[s]")

    # BGM processing
    if bgm_i is not None:
        filters.append(
            f"[{bgm_i}:a]"
            f"aformat=channel_layouts=stereo,aresample=44100,"
            f"highpass=f=40,lowpass=f=15000"
            f"[b0]"
        )
        if duck_bgm:
            filters.append(
                f"[b0][v_sc]"
                f"sidechaincompress=threshold={BGM_DUCK_TH}:ratio={BGM_DUCK_RT}:attack={BGM_DUCK_ATK}:release={BGM_DUCK_REL}:makeup=1"
                f"[b]"
            )
        else:
            filters.append("[b0]anull[b]")

        mix_inputs.append("[b]")

    # Final mix + limiter
    filters.append(
        "".join(mix_inputs) +
        f"amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=0:normalize=0,"
        f"alimiter=limit=0.97[m]"
    )

    filter_complex = ";".join(filters)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[m]",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ac", "2",
        str(out_path),
    ]

    if debug:
        print("[DEBUG] filter_complex =", filter_complex)
        print("[DEBUG] cmd =", cmd)

    _run_ffmpeg(cmd)


def mux_av_ffmpeg(ffmpeg: str, video_path: Path, audio_path: Path, out_path: Path) -> None:
    """
    Mux video + audio into final MP4.
    - Video copied (no re-encode)
    - Audio encoded to AAC
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    _run_ffmpeg(cmd)


def main():
    """
    Main pipeline:
      1) Render Manim video
      2) Concat voice segments
      3) Build optional SFX track
      4) Build optional BGM track
      5) Mix voice+sfx+bgm -> one AAC
      6) Mux video+audio -> final.mp4
      7) Optional captions burn-in -> captioned video
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="jobs/job_0001")
    ap.add_argument("--template", required=False,
                    help="Template key (see templates.json or RUNBOOK.md). "
                         "Overrides job.json template_id.")
    ap.add_argument("-q", "--quality", default="h", help="manim quality: l/m/h/p (like manim -qh)")
    ap.add_argument("--open", action="store_true", help="open final video after render")
    ap.add_argument("--no_sfx", action="store_true", help="disable sfx mixing even if marks exist")
    ap.add_argument("--no-trim-silence", action="store_true", help="disable silence trim on voice segments before concat")
    ap.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg binary (default: ffmpeg)")
    ap.add_argument("--keep-intermediates", action="store_true",
                    help="keep Manim media/ renders and audio intermediate files after mux")
    args = ap.parse_args()

    # --- Resolve repo root + load dynamic template registry ---
    repo_root = Path(__file__).resolve().parent
    TEMPLATE_MAP = _load_template_map(repo_root)

    # --- Resolve job paths ---
    job_dir = (repo_root / args.job).resolve()
    job_json = job_dir / "job.json"

    if not job_json.exists():
        raise FileNotFoundError(f"job.json not found: {job_json}")

    job = load_json(job_json)

    # --- Validate job.json schema (Pydantic) ---
    try:
        from src.sync.job_config import JobConfig
        cfg = JobConfig.model_validate(job)
        print(f"[OK] job.json valid — template_id={cfg.template_id}, "
              f"segments={len(cfg.audio.segments)}, timeline_keys={len(cfg.timeline)}")
    except Exception as _val_err:
        raise ValueError(
            f"job.json failed schema validation:\n{_val_err}\n"
            f"Check {job_json} against the schema in RUNBOOK.md"
        ) from _val_err

    # --- Extract validated path overrides (backwards-compatible defaults) ---
    _paths = cfg.paths
    media_dir  = (job_dir / _paths.media_dir).resolve()
    out_dir    = (job_dir / _paths.output_dir).resolve()
    sfx_marks  = (job_dir / _paths.sfx_marks).resolve()
    print(f"[OK] JOB_JSON_PATH={job_json}")

    # --- Resolve template ---
    template_name = args.template or job.get("template_id")
    if not template_name:
        raise ValueError("--template flag not provided and template_id missing from job.json")
    if template_name not in TEMPLATE_MAP:
        raise ValueError(
            f"Unknown template: {template_name!r}. "
            f"Available: {sorted(TEMPLATE_MAP.keys())} "
            f"(add new entries to templates.json)"
        )

    # --- Pick template scene ---
    tpl = TEMPLATE_MAP[template_name]
    scene_file = (repo_root / tpl["file"]).resolve()
    scene_name = tpl["scene"]

    if not scene_file.exists():
        raise FileNotFoundError(f"Template file not found: {scene_file}")

    # --- Media dir for manim output ---
    media_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------
    # 1) Run Manim render
    # -----------------------------
    # Keep the active interpreter path as-is; resolving symlinks can break venv module discovery.
    py_exec = str(os.sys.executable)
    manim_cmd = [
        py_exec,
        "-m", "manim",
        f"-q{args.quality}",
        "--disable_caching",
        str(scene_file),
        scene_name,
        "--media_dir",
        str(media_dir),
    ]

    env = os.environ.copy()
    env["JOB_JSON_PATH"] = str(job_json)
    env["JOB_DIR"] = str(job_dir)

    print("[RUN]", " ".join(manim_cmd))
    subprocess.run(manim_cmd, check=True, env=env)

    video_path = find_rendered_video(media_dir, scene_name, quality=args.quality)
    if not video_path:
        raise FileNotFoundError("Rendered video not found under job/media/videos")
    print(f"[OK] Rendered video: {video_path}")

    # Stage the raw Manim render to a flat, predictable path so the rest of
    # the pipeline is insulated from Manim's deep videos/{module}/{quality}/
    # directory nesting.  The staged file is the single source of truth for mux.
    staged_video = media_dir / "_staged_render.mp4"
    shutil.copy2(video_path, staged_video)
    video_path = staged_video
    print(f"[OK] Staged render: {staged_video}")

    # -----------------------------
    # 2) Voice concat
    # -----------------------------
    audio_cfg = job.get("audio") if isinstance(job.get("audio"), dict) else None
    if not audio_cfg:
        print("[NOTE] No audio block in job.json -> skipping mux.")
        return

    segments = audio_cfg.get("segments") if isinstance(audio_cfg.get("segments"), list) else []
    order = audio_cfg.get("order") if isinstance(audio_cfg.get("order"), list) else []
    if not segments or not order:
        print("[NOTE] No audio segments/order -> skipping mux.")
        return

    # map segment name -> file path
    seg_map: Dict[str, Path] = {}
    for s in segments:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", "")).strip()
        path = str(s.get("path", "")).strip()
        if name and path:
            seg_map[name] = resolve_job_path(job_dir, path)

    # build ordered list of audio files
    audio_paths: List[Path] = []
    missing = []
    for name in order:
        if name not in seg_map:
            missing.append(name)
        else:
            audio_paths.append(seg_map[name])

    if missing:
        raise ValueError(f"Audio order references missing segments: {missing}")

    for p in audio_paths:
        if not p.exists():
            raise FileNotFoundError(f"Audio file missing: {p}")

    ffmpeg = args.ffmpeg
    # out_dir and sfx_marks already resolved from job["paths"] above
    out_dir.mkdir(parents=True, exist_ok=True)

    voice_aac = out_dir / "_voice.aac"
    concat_audio_ffmpeg(ffmpeg, audio_paths, voice_aac, trim_silence=(not args.no_trim_silence))
    print(f"[OK] Voice concat: {voice_aac}")

    # -----------------------------
    # 3) Read configs
    # -----------------------------
    gains_cfg = job.get("gains") if isinstance(job.get("gains"), dict) else {}
    gain_voice = float(gains_cfg.get("gain_voice", 1.0) or 1.0)
    gain_sfx = float(gains_cfg.get("gain_sfx", 1.0) or 1.0)
    gain_bgm_db = float(gains_cfg.get("gain_bgm_db", -20.0) or -20.0)

    mix_cfg = job.get("mix") if isinstance(job.get("mix"), dict) else {}
    preset = str(mix_cfg.get("preset", "punchy"))
    duck_sfx = bool(mix_cfg.get("duck_sfx", False))

    timeline = job.get("timeline")
    if not isinstance(timeline, dict):
        timeline = {}

    # -----------------------------
    # 4) Build SFX (optional)
    # -----------------------------
    sfx_cfg = job.get("sfx") if isinstance(job.get("sfx"), dict) else {}
    sfx_enabled = bool(sfx_cfg.get("enabled", True)) and (not args.no_sfx)

    sfx_aac: Optional[Path] = None
    # sfx_marks path is already resolved from job["paths"]["sfx_marks"] above

    if sfx_enabled and sfx_marks.exists():
        print(f"[OK] SFX marks found: {sfx_marks}")
        sfx_build_gain = float(sfx_cfg.get("gain", 1.0) or 1.0)

        sfx_aac = out_dir / "_sfx_mix.aac"
        build_sfx_mix_ffmpeg(
            ffmpeg=ffmpeg,
            repo_root=repo_root,
            sfx_marks=sfx_marks,
            out_path=sfx_aac,
            global_gain=sfx_build_gain,
        )
        print(f"[OK] SFX mix: {sfx_aac}")
    else:
        if args.no_sfx:
            print("[NOTE] --no_sfx enabled -> skipping SFX.")
        else:
            print("[NOTE] No sfx_marks.json or sfx disabled -> skipping SFX.")

    # -----------------------------
    # 5) Build BGM (optional)
    # -----------------------------
    bgm_cfg = job.get("bgm") if isinstance(job.get("bgm"), dict) else {}
    bgm_enabled = bool(bgm_cfg.get("enabled", False))

    bgm_aac: Optional[Path] = None
    if bgm_enabled:
        # timeline must cover all segments if using per-segment mode
        for name in order:
            if name not in timeline:
                raise ValueError(f"timeline missing duration for segment: {name}")

        bgm_aac = out_dir / "_bgm.aac"
        build_bgm_track_ffmpeg(
            ffmpeg=ffmpeg,
            job_dir=job_dir,
            audio_order=order,
            timeline=timeline,   # durations per segment
            bgm_cfg=bgm_cfg,
            out_path=bgm_aac,
            global_gain_db=gain_bgm_db,
        )
        print(f"[OK] BGM track: {bgm_aac}")
    else:
        print("[NOTE] BGM disabled -> skipping BGM build.")

    # -----------------------------
    # 6) Final mix (voice + sfx + bgm)
    # -----------------------------
    # read default bgm ducking settings (only applies when bgm exists)
    duck_bgm = True
    duck_amount = "strong"
    if isinstance(bgm_cfg.get("default"), dict):
        duck_bgm = bool(bgm_cfg["default"].get("duck", True))
        duck_amount = str(bgm_cfg["default"].get("duck_amount", "strong"))

    mixed_aac = out_dir / "_mix.aac"
    mix_voice_sfx_bgm_ffmpeg(
        ffmpeg=ffmpeg,
        voice_path=voice_aac,
        sfx_path=sfx_aac,
        bgm_path=bgm_aac,
        out_path=mixed_aac,
        voice_gain=gain_voice,
        sfx_gain=gain_sfx,
        preset=preset,
        duck_sfx=duck_sfx,
        duck_bgm=duck_bgm,
        duck_amount=duck_amount,
        debug=False,
    )
    print(f"[OK] Final mixed audio: {mixed_aac}")

    # -----------------------------
    # 7) Final mux -> final.mp4 (ONLY ONCE)
    # -----------------------------
    out_cfg = job.get("output") if isinstance(job.get("output"), dict) else {}
    out_rel = str(out_cfg.get("final_mp4", "output/final.mp4"))
    out_path = resolve_job_path(job_dir, out_rel)

    mux_av_ffmpeg(ffmpeg, video_path, mixed_aac, out_path)
    print(f"[OK] Final muxed video: {out_path}")

    # -----------------------------
    # 7b) Versioned archive copy (non-destructive)
    # -----------------------------
    # Canonical path (output/final.mp4) is always overwritten — required by the
    # Phase 3 → 4 handoff contract.  We also write a timestamped copy so every
    # run is individually preserved without breaking any downstream pipeline.
    _run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _archive_dir = out_dir / "renders"
    _archive_dir.mkdir(exist_ok=True)
    _archive_path = _archive_dir / f"final_{_run_stamp}.mp4"
    shutil.copy2(out_path, _archive_path)
    print(f"[OK] Archived render: {_archive_path}")

    # -----------------------------
    # 7c) Intermediate cleanup (opt-out with --keep-intermediates)
    # -----------------------------
    if not args.keep_intermediates:
        _intermediates = [voice_aac, mixed_aac]
        if sfx_aac:
            _intermediates.append(sfx_aac)
        if bgm_aac:
            _intermediates.append(bgm_aac)
        for _f in _intermediates:
            try:
                if _f and Path(_f).exists():
                    Path(_f).unlink()
            except Exception:
                pass
        # Remove Manim's nested videos/ tree (staged render already copied)
        _videos_dir = media_dir / "videos"
        if _videos_dir.exists():
            try:
                shutil.rmtree(_videos_dir)
            except Exception:
                pass
        print("[OK] Intermediates cleaned up (use --keep-intermediates to retain them).")

    # -----------------------------
    # 8) Captions (optional) -> captioned video
    # -----------------------------
    captioned_video: Optional[str] = None
    cap_cfg = job.get("captions") if isinstance(job.get("captions"), dict) else {}
    if isinstance(cap_cfg, dict) and bool(cap_cfg.get("enabled", False)):
        try:
            cap_res = run_captions_pipeline(
                job=job,
                job_dir=job_dir,
                ffmpeg=ffmpeg,
                video_in=out_path,  # burn-in needs final muxed video
            )
            if isinstance(cap_res, dict):
                if cap_res.get("ass_path"):
                    print(f"[OK] Subtitles ASS: {cap_res['ass_path']}")
                if cap_res.get("captioned_video"):
                    captioned_video = str(cap_res["captioned_video"])
                    print(f"[OK] Captioned video: {captioned_video}")
                    # Archive the captioned version alongside the raw render archive
                    try:
                        _cap_archive = _archive_dir / f"final_captioned_{_run_stamp}.mp4"
                        shutil.copy2(captioned_video, _cap_archive)
                        print(f"[OK] Archived captioned: {_cap_archive}")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[WARN] Captions failed (ignored): {e}")
    else:
        print("[NOTE] Captions disabled -> skipping captions.")

    # -----------------------------
    # 9) Open output (optional)
    # -----------------------------
    if args.open:
        # If captioned video exists, open that; else open final mux
        to_open = captioned_video if captioned_video else str(out_path)
        try:
            os.startfile(to_open)  # Windows
        except Exception as e:
            print(f"[WARN] Could not auto-open video: {e}")


if __name__ == "__main__":
    main()
