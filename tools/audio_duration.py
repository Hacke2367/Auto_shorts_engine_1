import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def ffprobe_duration(path: Path) -> float | None:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
        return float(out)
    except Exception:
        return None


def resolve_job_path(job_dir: Path, maybe_rel: str) -> Path:
    p = Path(maybe_rel)
    return p if p.is_absolute() else (job_dir / p).resolve()


def _load_job(job_dir_arg: str) -> Tuple[Path, Path, Dict]:
    repo_root = Path(__file__).resolve().parents[1]
    job_dir = (repo_root / job_dir_arg).resolve()
    job_json = job_dir / "job.json"
    if not job_json.exists():
        raise FileNotFoundError(f"job.json not found: {job_json}")
    job = json.loads(job_json.read_text(encoding="utf-8"))
    if not isinstance(job, dict):
        raise ValueError("job.json root must be an object")
    return repo_root, job_json, job


def _collect_audio(job_dir: Path, job: Dict) -> Tuple[Dict[str, Path], List[str], Dict[str, float]]:
    audio = job.get("audio")
    if not isinstance(audio, dict):
        raise ValueError("job.json missing 'audio' object")

    raw_segments = audio.get("segments")
    if not isinstance(raw_segments, list):
        raise ValueError("job.json audio.segments must be a list")

    seg_map: Dict[str, Path] = {}
    for seg in raw_segments:
        if not isinstance(seg, dict):
            continue
        name = str(seg.get("name", "")).strip()
        rel = str(seg.get("path", "")).strip()
        if not name or not rel:
            continue
        seg_map[name] = resolve_job_path(job_dir, rel)

    order = audio.get("order")
    if not isinstance(order, list) or not order:
        raise ValueError("job.json audio.order must be a non-empty list")

    timeline = job.get("timeline")
    if not isinstance(timeline, dict):
        timeline = {}

    clean_order: List[str] = []
    for name in order:
        if isinstance(name, str) and name.strip():
            clean_order.append(name.strip())

    clean_timeline: Dict[str, float] = {}
    for k, v in timeline.items():
        try:
            clean_timeline[str(k)] = float(v)
        except Exception:
            pass

    return seg_map, clean_order, clean_timeline


def _print_report(
    order: List[str],
    seg_map: Dict[str, Path],
    timeline: Dict[str, float],
    durations: Dict[str, float],
    tolerance: float,
) -> Tuple[List[str], Dict[str, float]]:
    total_audio = 0.0
    mismatches: List[str] = []
    timeline_updates: Dict[str, float] = {}

    print("\n=== AUDIO DURATIONS ===")
    for name in order:
        path = seg_map.get(name)
        if path is None:
            print(f"{name:>12} : MISSING segment path in audio.segments")
            mismatches.append(f"{name}: missing in audio.segments")
            continue
        if not path.exists():
            print(f"{name:>12} : MISSING file -> {path}")
            mismatches.append(f"{name}: audio file missing")
            continue

        dur = ffprobe_duration(path)
        if dur is None:
            print(f"{name:>12} : ??? (ffprobe failed) -> {path}")
            mismatches.append(f"{name}: ffprobe failed")
            continue

        durations[name] = float(dur)
        timeline_updates[name] = float(dur)
        total_audio += float(dur)

        t_val = timeline.get(name)
        if t_val is None:
            print(f"{name:>12} : {dur:6.2f}s -> {path.name} | timeline: MISSING")
            mismatches.append(f"{name}: timeline missing")
            continue

        delta = float(dur) - float(t_val)
        tag = "OK"
        if abs(delta) > tolerance:
            tag = "MISMATCH"
            mismatches.append(
                f"{name}: audio={dur:.2f}s timeline={float(t_val):.2f}s delta={delta:+.2f}s"
            )
        print(
            f"{name:>12} : {dur:6.2f}s -> {path.name} | timeline={float(t_val):6.2f}s "
            f"delta={delta:+6.2f}s [{tag}]"
        )

    missing_timeline = [name for name in order if name not in timeline]
    extra_timeline = [name for name in timeline.keys() if name not in order]
    if missing_timeline:
        print(f"\n[WARN] timeline missing keys: {missing_timeline}")
    if extra_timeline:
        print(f"[WARN] timeline has extra keys not in audio.order: {extra_timeline}")

    total_timeline = sum(float(timeline.get(name, 0.0)) for name in order)
    print(f"\nTOTAL audio(order): {total_audio:.2f}s")
    print(f"TOTAL timeline(order): {total_timeline:.2f}s")
    print(f"TOLERANCE: ±{tolerance:.2f}s")

    if mismatches:
        print(f"\n[FAIL] mismatches found: {len(mismatches)}")
    else:
        print("\n[OK] all ordered segments match timeline within tolerance.")
    return mismatches, timeline_updates


def _write_timeline_values_only(job_json_path: Path, updates: Dict[str, float]) -> int:
    text = job_json_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    timeline_start = None
    brace_depth = 0
    timeline_end = None
    for idx, line in enumerate(lines):
        if timeline_start is None and '"timeline"' in line:
            timeline_start = idx
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                raise ValueError("timeline block parse failed")
            continue
        if timeline_start is not None:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth == 0:
                timeline_end = idx
                break

    if timeline_start is None or timeline_end is None:
        raise ValueError("could not locate timeline object in job.json")

    changed = 0
    line_re = re.compile(r'^(\s*)"([^"]+)"\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(\s*,?\s*)$')
    for i in range(timeline_start + 1, timeline_end):
        ln = lines[i].rstrip("\n")
        m = line_re.match(ln)
        if not m:
            continue
        key = m.group(2)
        if key not in updates:
            continue
        new_val = f"{float(updates[key]):.2f}"
        old_val = m.group(3)
        if old_val == new_val:
            continue
        lines[i] = f'{m.group(1)}"{key}": {new_val}{m.group(4)}\n'
        changed += 1

    if changed > 0:
        job_json_path.write_text("".join(lines), encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="jobs/job_0001 or jobs/butterfly_job")
    ap.add_argument(
        "--tolerance",
        type=float,
        default=0.35,
        help="allowed absolute delta between audio and timeline per segment (seconds)",
    )
    ap.add_argument(
        "--write-timeline",
        action="store_true",
        help="write measured durations into job.json timeline (timeline values only)",
    )
    args = ap.parse_args()

    if shutil.which("ffprobe") is None:
        print("[FAIL] ffprobe not found in PATH. Install FFmpeg/ffprobe first.")
        return 2

    _repo_root, job_json_path, job = _load_job(args.job)
    job_dir = job_json_path.parent
    seg_map, order, timeline = _collect_audio(job_dir, job)

    durations: Dict[str, float] = {}
    mismatches, updates = _print_report(
        order=order,
        seg_map=seg_map,
        timeline=timeline,
        durations=durations,
        tolerance=float(args.tolerance),
    )

    if mismatches and not args.write_timeline:
        print("\n[STOP] strict mismatch mode active. Re-run with --write-timeline to update timeline values.")
        return 2

    if args.write_timeline:
        changed = _write_timeline_values_only(job_json_path, updates)
        print(f"[OK] UPDATED timeline only in {job_json_path} (changed keys: {changed})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
