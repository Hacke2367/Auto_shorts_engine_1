"""AutoShorts Final Handoff — Phase 3 → Phase 4 Bridge
=====================================================
Converts Phase 3 internal artifacts (script.json + audio/) into
the exact rich schema that main.py (Phase 4 video engine) expects.

This module does NOT modify Phase 1, 2, 3, or 4 logic. It is a
pure read-transform-write adapter layer.

Usage:
    python -m src.agents.final_handoff.handoff --job jobs/test_job
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tag → Engine Name mapping
# ---------------------------------------------------------------------------

def tag_to_engine_name(tag: str) -> str:
    """Convert Phase 2/3 UPPERCASE tag to Phase 4 lowercase engine name.

    Rules:
      - Ends in _<digits>:
          - Base in {ITEM, SLICE, CARD, NODE, REGION} => collapse underscore (ITEM_1 -> item1)
          - Base in {ROUND, MIDDLE, LAP} => keep underscore (ROUND_1 -> round_1)
      - Non-number tags: simple lowercase (HOOK->hook, SETUP->setup)
    """
    m = re.match(r"^([A-Z]+)_(\d+)$", tag)
    if m:
        base = m.group(1)
        num = m.group(2)
        if base in {"ITEM", "SLICE", "CARD", "NODE", "REGION"}:
            return f"{base.lower()}{num}"
        elif base in {"ROUND", "MIDDLE", "LAP"}:
            return f"{base.lower()}_{num}"
    
    return tag.lower()


def _engine_audio_filename(engine_name: str) -> str:
    """Build the lowercase mp3 filename from an engine name."""
    return f"{engine_name}.mp3"


# ---------------------------------------------------------------------------
# CSV Discovery
# ---------------------------------------------------------------------------

def discover_data_csv(job_dir: Path) -> str:
    """Find the data CSV relative path inside a job directory.

    Resolution order:
        1. job_dir/data/*.csv  (single match preferred)
        2. job_dir/**/*_data.csv  (pick most recent by mtime)

    Returns:
        Relative path string like 'data/butterfly_data.csv'

    Raises:
        FileNotFoundError if no CSV can be located.
    """
    data_dir = job_dir / "data"
    if data_dir.is_dir():
        csvs = sorted(data_dir.glob("*.csv"))
        if len(csvs) == 1:
            return str(csvs[0].relative_to(job_dir))
        if len(csvs) > 1:
            data_csvs = [c for c in csvs if c.stem.endswith("_data")]
            if data_csvs:
                return str(data_csvs[0].relative_to(job_dir))
            return str(csvs[0].relative_to(job_dir))

    candidates = sorted(job_dir.rglob("*_data.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return str(candidates[0].relative_to(job_dir))

    all_csvs = sorted(job_dir.rglob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if all_csvs:
        return str(all_csvs[0].relative_to(job_dir))

    raise FileNotFoundError(
        "data_csv missing; place *_data.csv under job/data/ or job/attempts/..."
    )


# ---------------------------------------------------------------------------
# Audio alias creation
# ---------------------------------------------------------------------------

def ensure_audio_aliases(job_dir: Path, tag_to_name: dict[str, str]) -> None:
    """Create lowercase audio file aliases alongside the UPPERCASE Phase 3 originals."""
    audio_dir = job_dir / "audio"
    if not audio_dir.is_dir():
        raise FileNotFoundError(f"Audio directory missing: {audio_dir}")

    for tag, engine_name in tag_to_name.items():
        upper_name = re.sub(r"[^A-Z0-9_]", "", tag.upper()) + ".mp3"
        upper_path = audio_dir / upper_name
        lower_name = _engine_audio_filename(engine_name)
        lower_path = audio_dir / lower_name

        if not upper_path.exists():
            if lower_path.exists():
                logger.debug(f"Alias already exists: {lower_name}")
                continue
            found = False
            for f in audio_dir.iterdir():
                if f.name.lower() == upper_name.lower():
                    upper_path = f
                    found = True
                    break
            if not found:
                logger.warning(f"Source audio missing for tag {tag}: expected {upper_path}")
                continue

        if upper_path.resolve() == lower_path.resolve():
            logger.debug(f"Same file on case-insensitive FS: {upper_name}")
            continue

        if lower_path.exists():
            if lower_path.stat().st_ino == upper_path.stat().st_ino:
                logger.debug(f"Alias already linked: {lower_name}")
                continue
            lower_path.unlink()

        os.link(upper_path, lower_path)
        logger.info(f"Created audio hardlink: {upper_name} → {lower_name}")


# ---------------------------------------------------------------------------
# Engine script.json builder
# ---------------------------------------------------------------------------

def build_engine_script(
    internal_script: dict[str, Any],
    tag_to_name: dict[str, str],
) -> dict[str, Any]:
    """Build the Phase 4-compatible engine_script.json."""
    template_name = internal_script.get("template_name", "unknown")
    segments = internal_script.get("segments", [])

    engine_segments = []
    for seg in segments:
        tag = seg.get("tag", "")
        engine_name = tag_to_name.get(tag, tag.lower())
        engine_segments.append({
            "name": engine_name,
            "text": seg.get("text", ""),
            "file": f"audio/{_engine_audio_filename(engine_name)}",
        })

    return {
        "template_id": template_name,
        "data_source": internal_script.get("data_source", "auto-generated"),
        "segments": engine_segments,
    }


# ---------------------------------------------------------------------------
# Engine job.json builder
# ---------------------------------------------------------------------------

_DEFAULT_VIDEO = {"w": 1080, "h": 1920}
_DEFAULT_GAINS = {"gain_voice": 1.0, "gain_sfx": 1.0, "gain_bgm_db": -20.0}
_DEFAULT_SFX = {"enabled": True, "gain": 1.0}
_DEFAULT_BGM = {
    "enabled": False,
    "mode": "per_segment",
    "library_dir": "audio/bgm",
    "default": {"path": "bgm_default.mp3", "gain_db": 0.0, "duck": True, "duck_amount": "strong"},
    "segments": {},
    "crossfade": 0.25,
}
_DEFAULT_MIX = {"preset": "punchy", "duck_sfx": False}
_DEFAULT_OUTPUT = {
    "final_mp4": "output/final.mp4",
    "subtitles_ass": "output/subtitles.ass",
    "captioned_mp4": "output/final_captioned.mp4",
}


def build_engine_job_json(
    job_id: str,
    template_name: str,
    data_csv_relpath: str,
    ordered_engine_names: list[str],
    timeline: dict[str, float],
) -> dict[str, Any]:
    """Build the complete Phase 4-compatible job.json."""
    audio_segments = [
        {"name": name, "path": f"audio/{_engine_audio_filename(name)}"}
        for name in ordered_engine_names
    ]
    
    captions_block = {
        "enabled": True,
        "script": {
            "path": "script/engine_script.json",
            "source_lang": "hi",
            "target_langs": ["en"],
        },
        "render": {
            "format": "ass",
            "burn_in": False,
            "style": {"preset": "modern_clean", "safe_margin_px": 80, "max_lines": 2},
            "tracks": [
                {"lang": "hi", "mode": "reveal_words", "position": "bottom"},
                {"lang": "en", "mode": "plain", "position": "above_bottom"},
            ],
            "highlight": {"enabled": False, "mode": "word_reveal"},
        },
    }

    job: dict[str, Any] = {
        "job_id": job_id,
        "template_id": template_name,
        "data_csv": data_csv_relpath,
        "video": _DEFAULT_VIDEO,
        "audio": {
            "segments": audio_segments,
            "order": list(ordered_engine_names),
        },
        "timeline": timeline,
        "gains": _DEFAULT_GAINS,
        "sfx": _DEFAULT_SFX,
        "bgm": _DEFAULT_BGM,
        "mix": _DEFAULT_MIX,
        "captions": captions_block,
        "output": _DEFAULT_OUTPUT,
    }

    return job


# ---------------------------------------------------------------------------
# Main handoff orchestrator
# ---------------------------------------------------------------------------

def run_handoff(job_dir: Path) -> dict[str, str]:
    """Execute full handoff mapping internals to Phase 4 compat files."""
    job_path = Path(job_dir).resolve()

    internal_script_path = job_path / "script" / "script.json"
    if not internal_script_path.exists():
        raise FileNotFoundError(f"Phase 3 script not found: {internal_script_path}")

    with open(internal_script_path, "r", encoding="utf-8") as f:
        internal_script = json.load(f)

    job_id = internal_script.get("job_id", job_path.name)
    template_name = internal_script.get("template_name", "unknown")
    segments = internal_script.get("segments", [])

    if not segments:
        raise ValueError("Internal script.json has no segments.")

    tag_to_name: dict[str, str] = {}
    ordered_engine_names: list[str] = []
    for seg in segments:
        tag = seg["tag"]
        engine_name = tag_to_engine_name(tag)
        tag_to_name[tag] = engine_name
        ordered_engine_names.append(engine_name)

    timeline: dict[str, float] = {}
    for seg in segments:
        tag = seg["tag"]
        engine_name = tag_to_name[tag]
        duration = seg.get("duration_sec")
        if duration is None:
            logger.warning(f"Segment {tag} missing duration_sec; using 2.0s fallback.")
            duration = 2.0
        timeline[engine_name] = round(float(duration), 2)

    ensure_audio_aliases(job_path, tag_to_name)
    data_csv = discover_data_csv(job_path)
    engine_script = build_engine_script(internal_script, tag_to_name)

    engine_job = build_engine_job_json(
        job_id=job_id,
        template_name=template_name,
        data_csv_relpath=data_csv,
        ordered_engine_names=ordered_engine_names,
        timeline=timeline,
    )

    engine_script_path = job_path / "script" / "engine_script.json"
    with open(engine_script_path, "w", encoding="utf-8") as f:
        json.dump(engine_script, f, indent=2, ensure_ascii=False)

    job_json_path = job_path / "job.json"
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(engine_job, f, indent=2, ensure_ascii=False)

    return {
        "job.json": str(job_json_path),
        "engine_script.json": str(engine_script_path),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="AutoShorts Final Handoff: convert Phase 3 outputs → Phase 4 engine inputs."
    )
    ap.add_argument("--job", required=True, help="Path to job directory (e.g. jobs/test_job)")
    args = ap.parse_args()

    job_dir = Path(args.job)
    if not job_dir.is_dir():
        print(f"ERROR: Job directory not found: {job_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"=== AutoShorts Final Handoff ===")
    print(f"Job directory: {job_dir.resolve()}\n")

    try:
        written = run_handoff(job_dir)
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n--- Files Written ---")
    for label, path in written.items():
        print(f"  {label:30s} → {path}")

    print("\n✅ Ready for: python main.py --job", str(job_dir.as_posix()), "--template <template>")
    print("   (Note: main.py can also be updated to auto-detect the template from job.json.)")


if __name__ == "__main__":
    main()
