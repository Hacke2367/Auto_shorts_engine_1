#!/usr/bin/env python3
"""
main.py (Step-3 Orchestrator)
----------------------------
Goal: run ONE job folder end-to-end (manual test, no agents yet)

What it does:
1) Reads jobs/<job_id>/job.json
2) Sets JOB_JSON_PATH env var (so Manim templates can read the job)
3) Ensures geo_data CSV is available at src.config.DATA_DIR as ai_stats.csv (for bar_chart)
4) Renders Manim scene
5) (Optional) If audio segments exist, concatenates + muxes into final mp4

Run:
  python main.py --job jobs/job_0001 --template bar_chart -q h

Optional requirements (for audio concat/mux):
  - ffmpeg in PATH
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

JOB_ENV = "JOB_JSON_PATH"

# template_id -> (manim file, scene name)
TEMPLATE_MAP = {
    "bar_chart": ("src/templates/Bar_chart/bar_chart.py", "BarChartTemplate"),
    # add others later:
    # "pie_chart": ("src/templates/pie_chart/donut_breakdown.py", "DonutBreakdownTemplate"),
}

def _read_json(p: Path) -> Dict:
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("job.json must be a JSON object")
    return data

def _ffmpeg_exists() -> bool:
    from shutil import which
    return which("ffmpeg") is not None

def _run(cmd: List[str], cwd: Optional[Path] = None) -> None:
    print("\n[RUN]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)

def _find_latest_mp4(root: Path) -> Path:
    mp4s = sorted(root.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        raise FileNotFoundError(f"No mp4 found under: {root}")
    return mp4s[0]

def _copy_csv_for_bar_chart(job_dir: Path, job: Dict, repo_root: Path) -> None:
    """
    Current bar_chart.py expects ai_stats.csv at src.config.DATA_DIR (usually <repo>/geo_data/ai_stats.csv).
    If your bar_chart.py already reads job.json for data_csv, you can remove this later.
    """
    try:
        sys.path.insert(0, str(repo_root))
        from src.config import DATA_DIR  # type: ignore
    except Exception as e:
        raise RuntimeError(f"Could not import src.config to locate DATA_DIR. Error: {e}")

    data_dir = Path(DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Prefer job.json data_csv if provided
    data_csv = job.get("data_csv") or job.get("jobs/data", {}).get("csv")
    if not data_csv:
        print("[WARN] job.json has no data_csv. Skipping CSV copy.")
        return

    src_csv = (repo_root / data_csv).resolve()
    if not src_csv.exists():
        raise FileNotFoundError(f"data_csv not found: {src_csv}")

    dst_csv = data_dir / "ai_stats.csv"
    shutil.copy2(src_csv, dst_csv)
    print(f"[OK] Copied CSV -> {dst_csv}")

def _concat_audio_ffmpeg(job_dir: Path, job: Dict) -> Optional[Path]:
    """
    Concatenate segment audio into one track using ffmpeg concat demuxer.
    Expects job.json:
      "audio": { "segments": [ {"name":"hook","path":"audio/hook.mp3"}, ... ] }
    Returns combined wav path or None.
    """
    audio = job.get("jobs/audio", {})
    segs = audio.get("segments", [])
    if not segs:
        return None
    if not _ffmpeg_exists():
        print("[WARN] ffmpeg not found; skipping audio concat/mux.")
        return None

    concat_list = job_dir / "audio" / "_concat_list.txt"
    concat_list.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for s in segs:
        p = s.get("path")
        if not p:
            continue
        ap = (job_dir / p).resolve()
        if not ap.exists():
            raise FileNotFoundError(f"Audio segment missing: {ap}")
        lines.append(f"file '{ap.as_posix()}'")

    if not lines:
        return None

    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_wav = job_dir / "audio" / "combined.wav"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-acodec", "pcm_s16le", str(out_wav)])
    return out_wav

def _mux_av_ffmpeg(video_mp4: Path, audio_wav: Path, out_mp4: Path) -> None:
    if not _ffmpeg_exists():
        print("[WARN] ffmpeg not found; skipping mux.")
        return
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-i", str(video_mp4),
        "-i", str(audio_wav),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(out_mp4),
    ])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="Job folder, e.g. jobs/job_0001")
    ap.add_argument("--template", default=None, help="Template id override, e.g. bar_chart")
    ap.add_argument("-q", "--quality", default="h", choices=["l","m","h","k"], help="manim quality: l/m/h/k")
    ap.add_argument("--preview", action="store_true", help="manim -p (preview)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent
    job_dir = (repo_root / args.job).resolve()
    job_json = job_dir / "job.json"
    if not job_json.exists():
        raise FileNotFoundError(f"job.json not found: {job_json}")

    job = _read_json(job_json)

    template_id = args.template or job.get("template_id")
    if not template_id:
        raise ValueError("template_id missing. Provide in job.json or --template")

    if template_id not in TEMPLATE_MAP:
        raise ValueError(f"Unknown template_id '{template_id}'. Add it to TEMPLATE_MAP in main.py.")

    manim_file_rel, scene_name = TEMPLATE_MAP[template_id]
    manim_file = (repo_root / manim_file_rel).resolve()
    if not manim_file.exists():
        raise FileNotFoundError(f"Manim file not found: {manim_file}")

    # 1) set env so template can read job.json
    os.environ[JOB_ENV] = str(job_json)
    print(f"[OK] {JOB_ENV}={job_json}")

    # 2) Ensure CSV is where bar_chart expects (safe for now)
    if template_id == "bar_chart":
        _copy_csv_for_bar_chart(job_dir=job_dir, job=job, repo_root=repo_root)

    # 3) Render Manim into job_dir/media
    media_dir = job_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    quality_flag = {"l":"-ql","m":"-qm","h":"-qh","k":"-qk"}[args.quality]
    cmd = [sys.executable, "-m", "manim", quality_flag, str(manim_file), scene_name, "--media_dir", str(media_dir)]
    if args.preview:
        cmd.insert(3, "-p")  # after quality flag

    _run(cmd, cwd=repo_root)

    # 4) Find produced mp4
    raw_mp4 = _find_latest_mp4(media_dir)
    print(f"[OK] Rendered video: {raw_mp4}")

    # 5) Optional audio concat + mux
    combined_audio = _concat_audio_ffmpeg(job_dir, job)
    if combined_audio:
        final_out = job_dir / "output" / "final.mp4"
        _mux_av_ffmpeg(raw_mp4, combined_audio, final_out)
        print(f"[OK] Final muxed video: {final_out}")
    else:
        print("[NOTE] No audio mux done. Add audio segments in job.json -> audio.segments and ensure ffmpeg is installed.")

    print("\nDONE ✅")

if __name__ == "__main__":
    main()
