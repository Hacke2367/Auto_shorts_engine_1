# src/sync/audio_normalize.py
"""
Bake the silence trim into the voice segments BEFORE the scene is rendered.

Why this exists
---------------
`main.py` used to trim each voice segment at concat time, long after Manim had
already rendered the scene against the *untrimmed* `job["timeline"]`. The two
then disagreed, and the mux resolved the disagreement by cutting the video:

    jobs/sort_job   manim rendered 80.07s   voice after trim 73.79s
                    -> the last 6.3s of video (winner tail + outro) was lost

Every job was losing its tail this way (-0.76s to -6.08s measured across 10
jobs). Jobs whose last SFX cue happened to land near the end were spared,
because the SFX track propped the mixed audio back up to the video length --
so whether a video got truncated came down to luck, not design.

The fix is ordering: trim the audio first, write the real durations into
`job["timeline"]`, and only then render. The scene is then built against the
audio that will actually be heard, and `sum(timeline) == len(voice track)`
holds exactly.

Safety
------
* Originals are moved to `audio/_raw/` on first run and are never overwritten.
* Trimming always re-derives from `audio/_raw/`, so running this repeatedly is
  idempotent -- it can never trim an already-trimmed file a second time.
* `audio/_raw/` is the restore point: delete the working files and re-run to
  get back to the untouched TTS output.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.sync.audio_trim import SILENCE_TRIM_FILTER, _guess_ffprobe

RAW_DIRNAME = "_raw"

# Lossless for wav; high-quality VBR (~190 kbps) for mp3. The concat re-encodes
# to AAC 192k afterwards either way, so this generation is not the weak link.
_ENCODE_ARGS = {
    ".wav": ["-c:a", "pcm_s16le"],
    ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    ".m4a": ["-c:a", "aac", "-b:a", "192k"],
    ".aac": ["-c:a", "aac", "-b:a", "192k"],
}


def _probe_duration(ffprobe: str, path: Path) -> float:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return round(float((r.stdout or "").strip()), 3)


def _trim_one(ffmpeg: str, ffprobe: str, src: Path, dst: Path) -> float:
    """Trim `src` through SILENCE_TRIM_FILTER into `dst`. Returns dst duration."""
    enc = _ENCODE_ARGS.get(dst.suffix.lower(), ["-c:a", "aac", "-b:a", "192k"])

    fd, tmp_name = tempfile.mkstemp(suffix=dst.suffix, prefix="_norm_")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", str(src), "-af", SILENCE_TRIM_FILTER, *enc, str(tmp)],
            check=True, capture_output=True, text=True, timeout=120,
        )
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(dst))
        return _probe_duration(ffprobe, dst)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"silence trim failed for {src}: {(e.stderr or '').strip() or e}"
        ) from e
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def normalize_voice_segments(
    ffmpeg: str,
    job_dir: Path,
    job: Dict[str, Any],
    job_json_path: Path,
) -> Tuple[bool, List[str]]:
    """
    Trim every voice segment in place and rewrite `job["timeline"]` to the
    resulting durations. Mutates `job` and persists it to `job_json_path`.

    Returns (changed, report_lines). `changed` is False when the timeline
    already matched the trimmed audio (nothing to do).
    """
    audio_cfg = job.get("audio") if isinstance(job.get("audio"), dict) else {}
    order = [str(n) for n in (audio_cfg.get("order") or [])]
    segments = audio_cfg.get("segments") or []

    seg_paths: Dict[str, Path] = {}
    for s in segments:
        if isinstance(s, dict) and s.get("name") and s.get("path"):
            seg_paths[str(s["name"])] = job_dir / str(s["path"])

    if not order or not seg_paths:
        return False, ["[normalize] no audio segments -- skipped"]

    ffprobe = _guess_ffprobe(ffmpeg)
    timeline = job.get("timeline") if isinstance(job.get("timeline"), dict) else {}

    report: List[str] = []
    total_before = 0.0
    total_after = 0.0
    changed = False

    for name in order:
        work = seg_paths.get(name)
        if work is None or not work.exists():
            report.append(f"[normalize] {name}: file missing -- skipped")
            continue

        raw = work.parent / RAW_DIRNAME / work.name

        # First run: preserve the untouched original. Later runs: reuse it, so
        # the trim is always applied to pristine audio exactly once.
        if not raw.exists():
            raw.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work, raw)

        before = _probe_duration(ffprobe, raw)
        after = _trim_one(ffmpeg, ffprobe, raw, work)

        total_before += before
        total_after += after

        old_tl = float(timeline.get(name, 0.0) or 0.0)
        if abs(old_tl - after) > 0.005:
            changed = True
        timeline[name] = after

        lost = before - after
        flag = "  <-- large" if lost > 1.0 else ""
        report.append(f"[normalize] {name:<12} {before:6.2f}s -> {after:6.2f}s  (-{lost:.2f}s){flag}")

    job["timeline"] = timeline

    if changed:
        tmp = job_json_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, ensure_ascii=False)
        os.replace(tmp, job_json_path)

    report.append(
        f"[normalize] total {total_before:.2f}s -> {total_after:.2f}s "
        f"(-{total_before - total_after:.2f}s of dead air); "
        f"timeline {'updated' if changed else 'already correct'}"
    )
    return changed, report
