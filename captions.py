# captions.py
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional


def load_json(path: Path) -> Dict[str, Any]:
    """Read JSON file as dict."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_job_path(job_dir: Path, maybe_rel: str) -> Path:
    """Resolve relative path from job_dir, or return absolute path as-is."""
    p = Path(maybe_rel)
    return p if p.is_absolute() else (job_dir / p).resolve()


def build_timeline_segments(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build timeline segments list:
    [{"name":..., "start":..., "end":..., "dur":...}, ...]
    Uses:
      - job["audio"]["order"]  (segment order)
      - job["timeline"][name]  (duration seconds per segment)
    """
    audio_cfg = job.get("audio") if isinstance(job.get("audio"), dict) else {}
    order = audio_cfg.get("order") if isinstance(audio_cfg.get("order"), list) else []
    timeline = job.get("timeline") if isinstance(job.get("timeline"), dict) else {}

    if not order:
        raise ValueError("job.json: audio.order missing/empty")
    if not timeline:
        raise ValueError("job.json: timeline missing/empty (durations required)")

    t = 0.0
    out: List[Dict[str, Any]] = []
    for name in order:
        if name not in timeline:
            raise ValueError(f"job.json: timeline missing duration for segment '{name}'")
        dur = float(timeline[name])
        start = t
        end = t + dur
        out.append({"name": str(name), "start": start, "end": end, "dur": dur})
        t = end
    return out


def load_script_map(job_dir: Path, job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-practice loader:
    - script.json ko flexible formats se load karta hai (map / segments list / segments dict)
    - phir normalize karke internal standard map banata hai:
        {
          "hook":   {"text": {"hi":"..","en":"..","default":".."}, "keywords":[...]},
          "setup":  {...}
        }
    """
    from src.captions.script_loader import load_script_json  # ✅ use our robust loader

    captions = job.get("captions") if isinstance(job.get("captions"), dict) else {}
    script_cfg = captions.get("script") if isinstance(captions.get("script"), dict) else {}
    script_rel = str(script_cfg.get("path", "script/script.json")).strip()
    script_path = resolve_job_path(job_dir, script_rel)

    # This returns normalized structure:
    # { seg_name: {"text": {...}, "keywords":[...]} }
    return load_script_json(script_path)



def render_ass(job: Dict[str, Any], timeline_segments: List[Dict[str, Any]], script_map: Dict[str, Any], out_ass: Path) -> None:
    """
    Generate ASS subtitles using your existing renderer:
      src/captions/ass_renderer.py -> render_ass(...)
    """
    from src.captions.ass_renderer import render_ass as _render_ass  # local import so file runs standalone

    out_ass.parent.mkdir(parents=True, exist_ok=True)
    _render_ass(out_path=out_ass, job=job, timeline_segments=timeline_segments, script_map=script_map)


def burn_ass_to_video(ffmpeg: str, video_in: Path, ass_path: Path, video_out: Path) -> None:
    """
    Burn subtitles into a video.

    Delegates to src.captions.burn_in.burn_in_ass, which escapes the Windows
    drive colon (C:\\ -> C\\:/) for the libass `ass=` filter. The previous inline
    implementation here passed a raw `C:/...` path, which ffmpeg mis-parsed (the
    `:` was read as a filter-option separator) and the burn failed on Windows.
    """
    from src.captions.burn_in import burn_in_ass
    burn_in_ass(ffmpeg=ffmpeg, video_in=video_in, ass_path=ass_path, video_out=video_out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="jobs/job_0001")
    ap.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg binary (default: ffmpeg)")

    # Output controls
    ap.add_argument("--ass-out", default="", help="override ASS output path (default uses job.output.subtitles_ass or output/subtitles.ass)")
    ap.add_argument("--burn", action="store_true", help="also burn subtitles into a video")
    ap.add_argument("--video-in", default="", help="video input for burn (default: job.output.final_mp4 or output/final.mp4)")
    ap.add_argument("--video-out", default="", help="video output for burn (default: output/final_captioned.mp4)")

    # If captions.enabled is false in job.json, still allow generation
    ap.add_argument("--force", action="store_true", help="run even if captions.enabled=false")
    # Caption timing source. Default matches main.py: the voice track is silence-
    # trimmed, so captions are timed against the TRIMMED durations to stay in sync.
    ap.add_argument("--no-trim-silence", action="store_true",
                    help="time captions off raw job.timeline instead of the trimmed voice track")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent
    job_dir = (repo_root / args.job).resolve()
    job_json = job_dir / "job.json"
    if not job_json.exists():
        raise FileNotFoundError(f"job.json not found: {job_json}")

    job = load_json(job_json)

    captions = job.get("captions") if isinstance(job.get("captions"), dict) else {}
    enabled = bool(captions.get("enabled", False))
    if (not enabled) and (not args.force):
        raise ValueError("captions.enabled=false. Use --force OR set captions.enabled=true in job.json")

    # 1) Build timeline segments — match the trimmed voice track by default so
    # subtitles stay in sync (shared resolver, same logic as the main pipeline).
    from src.captions.timeline_resolver import resolve_timeline_segments
    timeline_segments = resolve_timeline_segments(
        job=job,
        job_dir=job_dir,
        ffmpeg_path=args.ffmpeg,
        trim_silence=(not args.no_trim_silence),
    )

    # 2) Load script map from script.json
    script_map = load_script_map(job_dir, job)

    # 3) Decide ASS output
    out_cfg = job.get("output") if isinstance(job.get("output"), dict) else {}
    default_ass_rel = str(out_cfg.get("subtitles_ass", "output/subtitles.ass"))
    ass_out = resolve_job_path(job_dir, args.ass_out) if args.ass_out else resolve_job_path(job_dir, default_ass_rel)

    # 4) Render ASS
    render_ass(job=job, timeline_segments=timeline_segments, script_map=script_map, out_ass=ass_out)
    print(f"[OK] Wrote ASS: {ass_out}")

    # 5) Optional burn-in
    if args.burn:
        # input video path
        final_mp4_rel = str(out_cfg.get("final_mp4", "output/final.mp4"))
        video_in = resolve_job_path(job_dir, args.video_in) if args.video_in else resolve_job_path(job_dir, final_mp4_rel)

        if not video_in.exists():
            raise FileNotFoundError(f"video_in not found for burn: {video_in}")

        video_out = resolve_job_path(job_dir, args.video_out) if args.video_out else resolve_job_path(job_dir, "output/final_captioned.mp4")
        burn_ass_to_video(args.ffmpeg, video_in=video_in, ass_path=ass_out, video_out=video_out)
        print(f"[OK] Burned video: {video_out}")


if __name__ == "__main__":
    main()
