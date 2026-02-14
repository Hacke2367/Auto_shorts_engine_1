# src/captions/pipeline.py
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, Any, Optional

from .script_loader import load_script_json
from .timeline_resolver import resolve_timeline_segments
from .translator import translate_script_map
from .ass_renderer import render_ass
from .burn_in import burn_in_ass


def run_captions_pipeline(
        job: Dict[str, Any],
        job_dir: Path,
        ffmpeg: str,
        video_in: Optional[Path] = None,
) -> Dict[str, Optional[Path]]:
    """
    Returns:
      {
        "ass_path": Path,
        "captioned_video": Path or None
      }
    """
    captions = job.get("captions") if isinstance(job.get("captions"), dict) else {}
    enabled = bool(captions.get("enabled", False))

    if not enabled:
        return {"ass_path": None, "captioned_video": None}

    render_cfg = captions.get("render") if isinstance(captions.get("render"), dict) else {}
    burn_in = bool(render_cfg.get("burn_in", True))

    # script config
    script_cfg = captions.get("script") if isinstance(captions.get("script"), dict) else {}
    script_rel = str(script_cfg.get("path", "script/script.json"))
    script_path = (job_dir / script_rel).resolve()

    # where to write ass
    out_cfg = job.get("output") if isinstance(job.get("output"), dict) else {}
    ass_rel = str(out_cfg.get("subtitles_ass", "output/subtitles.ass"))
    ass_path = (job_dir / ass_rel).resolve()
    ass_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) load script.json
    script_map = load_script_json(script_path)

    # 2) timeline segments (uses job.timeline or ffprobe fallback)
    timeline_segments = resolve_timeline_segments(job=job, job_dir=job_dir, ffmpeg_path=ffmpeg)

    # 3) (optional) translate
    source_lang = str(script_cfg.get("source_lang", "hi"))
    target_langs = script_cfg.get("target_langs", [])
    if not isinstance(target_langs, list):
        target_langs = []

    script_map = translate_script_map(
        script_map=script_map,
        source_lang=source_lang,
        target_langs=[str(x) for x in target_langs],
        enabled=False,  # keep OFF in prototype v1
    )

    # 4) render ass
    render_ass(
        out_path=ass_path,
        job=job,
        timeline_segments=timeline_segments,
        script_map=script_map,
    )

    captioned_out: Optional[Path] = None

    # 5) burn-in if requested
    if burn_in:
        if video_in is None:
            raise ValueError("burn_in=true but video_in was not provided to pipeline.")

        # output captioned mp4
        final_captioned_rel = str(out_cfg.get("final_captioned_mp4", "output/final_captioned.mp4"))
        captioned_out = (job_dir / final_captioned_rel).resolve()

        burn_in_ass(
            ffmpeg=ffmpeg,
            video_in=video_in,
            ass_path=ass_path,
            video_out=captioned_out,
        )

    return {"ass_path": ass_path, "captioned_video": captioned_out}


# Optional CLI: test captions without full render
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job_dir", required=True, help="jobs/job_0001")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--video", default="", help="optional: path to final mp4 for burn-in")
    args = ap.parse_args()

    job_dir = Path(args.job_dir).resolve()
    job_json = job_dir / "job.json"

    if not job_json.exists():
        raise FileNotFoundError(f"job.json not found: {job_json}")

    job = json.loads(job_json.read_text(encoding="utf-8"))
    video_in = Path(args.video).resolve() if args.video else None

    res = run_captions_pipeline(
        job=job,
        job_dir=job_dir,
        ffmpeg=args.ffmpeg,
        video_in=video_in,
    )
    print("[OK] captions:", res)