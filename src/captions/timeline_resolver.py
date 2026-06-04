# src/captions/timeline_resolver.py
from __future__ import annotations
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.sync.audio_trim import trimmed_duration_seconds

_log = logging.getLogger(__name__)


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
    Raises RuntimeError (with ffprobe's stderr) if the probe fails or times out.
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
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        s = (r.stdout or "").strip()
        return float(s)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ffprobe timed out after 10s for {audio_path}"
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffprobe failed for {audio_path}: {e}\nstderr: {e.stderr or ''}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"ffprobe failed for {audio_path}: {e}") from e


def resolve_timeline_segments(
    job: Dict[str, Any],
    job_dir: Path,
    ffmpeg_path: str,
    trim_silence: bool = False,
) -> List[Dict[str, Any]]:
    """
    Builds a timeline list:
      [{name, start, end, dur}, ...]

    Duration source per segment:
      - trim_silence=True : the segment's silence-TRIMMED duration, measured with
        the SAME filter the voice concat uses. This makes subtitle timing match
        the final (trimmed) voice track exactly. This is authoritative and
        overrides job['timeline'] (which holds raw/untrimmed durations).
      - trim_silence=False: job['timeline'] if present, else raw ffprobe of the
        original segment file.

    If a trimmed measurement fails for a segment, falls back to the
    timeline/raw-ffprobe value so caption generation never hard-crashes.
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

        # Authoritative path: trimmed duration that matches the real voice track.
        if trim_silence:
            try:
                dur = trimmed_duration_seconds(ffmpeg_path, seg_path_map[name])
            except Exception as e:
                _log.warning(
                    "captions: trimmed-duration measurement failed for '%s' "
                    "(%s) — falling back to timeline/raw duration",
                    name, e,
                )
                dur = None

        # Otherwise (or on fallback): use job['timeline'] if present.
        if dur is None and name in timeline:
            try:
                dur = float(timeline[name])
            except Exception:
                dur = None

        # Last resort: raw ffprobe of the original (untrimmed) segment file.
        if dur is None:
            audio_path = seg_path_map[name]
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file missing for segment '{name}': {audio_path}")
            dur = ffprobe_duration_seconds(ffmpeg_path, audio_path)

        # Round to centiseconds before accumulating to prevent IEEE 754 drift
        # across many segments (raw float addition loses ~0.2 ms per operation).
        dur = round(max(0.0, float(dur)), 2)
        start = round(t, 2)
        end = round(start + dur, 2)
        out.append({"name": name, "start": start, "end": end, "dur": dur})
        t = end

    return out
