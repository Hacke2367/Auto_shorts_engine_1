# src/captions/timeline_resolver.py
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional


def _guess_ffprobe_path(ffmpeg_path: str) -> str:
    """
    If user passes ffmpeg path like 'ffmpeg', we guess 'ffprobe'.
    If user passes 'C:\\...\\ffmpeg.exe', we replace to ffprobe.exe.
    """
    p = Path(ffmpeg_path)
    name = p.name.lower()
    if "ffmpeg" in name:
        return str(p.with_name(name.replace("ffmpeg", "ffprobe")))
    return "ffprobe"


def ffprobe_duration_seconds(ffmpeg_path: str, audio_path: Path) -> float:
    """
    Returns duration in seconds using ffprobe.
    """
    ffprobe = _guess_ffprobe_path(ffmpeg_path)

    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        s = (r.stdout or "").strip()
        return float(s)
    except Exception as e:
        raise RuntimeError(f"ffprobe failed for {audio_path}: {e}")


def resolve_timeline_segments(
    job: Dict[str, Any],
    job_dir: Path,
    ffmpeg_path: str,
) -> List[Dict[str, Any]]:
    """
    Builds a timeline list:
      [{name, start, end, dur}, ...]
    Uses job['timeline'] if present; else uses ffprobe on each audio segment file.
    """
    audio_cfg = job.get("audio") if isinstance(job.get("audio"), dict) else None
    if not audio_cfg:
        raise ValueError("job.json missing 'audio' block (required for captions timeline).")

    segments = audio_cfg.get("segments") if isinstance(audio_cfg.get("segments"), list) else []
    order = audio_cfg.get("order") if isinstance(audio_cfg.get("order"), list) else []
    if not segments or not order:
        raise ValueError("job.json 'audio.segments' and 'audio.order' are required.")

    # map: name -> path
    seg_path_map: Dict[str, Path] = {}
    for s in segments:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", "")).strip()
        rel = str(s.get("path", "")).strip()
        if name and rel:
            seg_path_map[name] = (job_dir / rel).resolve()

    timeline = job.get("timeline")
    if not isinstance(timeline, dict):
        timeline = {}

    out: List[Dict[str, Any]] = []
    t = 0.0

    for name in order:
        if name not in seg_path_map:
            raise ValueError(f"audio.order references missing segment: {name}")

        dur: Optional[float] = None
        if name in timeline:
            try:
                dur = float(timeline[name])
            except Exception:
                dur = None

        # fallback: ffprobe duration
        if dur is None:
            audio_path = seg_path_map[name]
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file missing for segment '{name}': {audio_path}")
            dur = ffprobe_duration_seconds(ffmpeg_path, audio_path)

        dur = max(0.0, float(dur))
        start = t
        end = t + dur
        out.append({"name": name, "start": start, "end": end, "dur": dur})
        t = end

    return out
