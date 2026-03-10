from __future__ import annotations

"""AutoShorts Phase 3 Audio Engine — Runner
============================================
Orchestrates Phase 3 Audio Synthesis explicitly mapping Phase 2 scripts
to pure binary audio. Enforces safe dead-air truncations and visual timing bounds.
"""

import asyncio
import copy
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
import aiohttp

from src.agents.phase3_audio.contracts import (
    AudioSegment,
    AudioSynthesisSettings,
    Phase3Payload,
    UnderRunError,
)
from src.agents.phase3_audio.tts_client import synthesize
from src.agents.phase3_audio.trimming import trim_silence
from src.agents.phase3_audio.duration import duration_ms, duration_sec
from src.agents.phase3_audio.packager import (
    update_script_with_audio,
    build_job_json,
    atomic_write_json,
)
from src.agents.phase3_audio.tests_offline import _fake_tts

logger = logging.getLogger(__name__)

# Project root resolution (kept local to avoid Phase1/Phase2 coupling)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TIMING_REGISTRY_PATH = _PROJECT_ROOT / ".agent" / "context" / "template_timing_registry.yaml"

_ENGINE_VERSION = "1.0"


def _get_base_tag(tag: str) -> str:
    """Extract base tag from dynamic tag: ITEM_1 -> ITEM."""
    return re.sub(r"_\d+$", "", tag)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _sha256_json(obj: Any) -> str:
    encoded = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compute_inputs_hash(
    script_payload: dict[str, Any],
    tts_settings: AudioSynthesisSettings,
    timing_registry: dict[str, Any],
    trim_pad_ms: int = 50,
) -> str:
    """Build deterministic hash for idempotency."""
    script_stable = copy.deepcopy(script_payload)
    script_stable.pop("phase3_inputs_hash", None)

    # remove Phase3-derived segment fields
    for s in script_stable.get("segments", []):
        s.pop("audio_relpath", None)
        s.pop("duration_ms", None)
        s.pop("duration_sec", None)

    state = {
        "script": script_stable,
        "tts": tts_settings.model_dump(mode="json"),
        "trim_pad_ms": trim_pad_ms,
        "timing_registry": timing_registry,
        "engine_version": _ENGINE_VERSION,
    }
    return _sha256_json(state)


async def _process_segment(
    idx: int,
    seg_dict: dict[str, Any],
    tts_settings: AudioSynthesisSettings,
    session: aiohttp.ClientSession | None,
    audio_dir: Path,
    sem: asyncio.Semaphore,
    template_name: str,
    timing_registry: dict[str, Any],
    is_offline: bool,
    skip_underrun: bool,
) -> tuple[int, AudioSegment]:
    """Lifecycle of one segment: synthesize -> trim -> duration -> persist -> underrun gate."""
    tag = seg_dict["tag"]
    text = seg_dict["text"]

    safe_tag = re.sub(r"[^A-Z0-9_]", "", tag.upper())
    audio_file_name = f"{safe_tag}.mp3"
    audio_file_path = audio_dir / audio_file_name

    async with sem:
        if is_offline:
            logger.info(f"[{tag}] Synthesizing OFFLINE tone wrapper...")
            await asyncio.sleep(0)  # yield
            raw_bytes = _fake_tts(text)
        else:
            if session is None:
                raise RuntimeError("HTTP session is required for online TTS mode.")
            logger.info(f"[{tag}] Synthesizing via ElevenLabs API...")
            raw_bytes = await synthesize(text, tts_settings, session)

    trimmed_bytes = trim_silence(raw_bytes)
    d_ms = duration_ms(trimmed_bytes)
    d_sec = duration_sec(trimmed_bytes)

    # Persist segment audio deterministically
    with open(audio_file_path, "wb") as f:
        f.write(trimmed_bytes)

    # Under-run check
    base_tag = _get_base_tag(safe_tag)
    mnd = float(timing_registry.get(template_name, {}).get(base_tag, 0.0))
    if (not skip_underrun) and d_sec < mnd:
        raise UnderRunError(
            f"Segment [{tag}] spoke {d_sec}s but visual MND requires {mnd}s. REPAIR NEEDED."
        )
    if skip_underrun and d_sec < mnd:
        logger.warning(f"[SKIP_UNDERRUN=1] {tag} under-runs MND: {d_sec}s < {mnd}s")

    rel_path = f"audio/{audio_file_name}"
    return idx, AudioSegment(
        tag=tag,
        text=text,
        audio_relpath=rel_path,
        duration_ms=d_ms,
        duration_sec=d_sec,
    )


async def run_phase3(job_dir: Path | str, tts_settings: AudioSynthesisSettings) -> Phase3Payload:
    """Main Phase 3 orchestrator."""
    job_path = Path(job_dir)
    script_path = job_path / "script" / "script.json"
    audio_dir = job_path / "audio"
    job_json_path = job_path / "job.json"

    if not script_path.exists():
        raise FileNotFoundError(f"Missing Phase 2 Script at: {script_path}")

    with open(script_path, "r", encoding="utf-8") as f:
        script_payload = json.load(f)

    job_id = script_payload["job_id"]
    template_name = script_payload["template_name"]
    persona_id = script_payload["persona_id"]
    segments_data = script_payload.get("segments", [])

    audio_dir.mkdir(parents=True, exist_ok=True)

    timing_registry = _load_yaml(_TIMING_REGISTRY_PATH)
    current_hash = _compute_inputs_hash(script_payload, tts_settings, timing_registry)

    cached_hash = script_payload.get("phase3_inputs_hash")
    if cached_hash == current_hash:
        files_intact = True
        cached_segments: list[AudioSegment] = []

        for s in segments_data:
            rel = s.get("audio_relpath")
            d_ms = s.get("duration_ms")

            if not rel or d_ms is None:
                files_intact = False
                break

            expected_path = job_path / rel
            if not expected_path.exists():
                files_intact = False
                break

            try:
                cached_segments.append(
                    AudioSegment(
                        tag=s["tag"],
                        text=s["text"],
                        audio_relpath=rel,
                        duration_ms=int(d_ms),
                        duration_sec=float(s.get("duration_sec", float(d_ms) / 1000.0)),
                    )
                )
            except Exception:
                files_intact = False
                break

        if files_intact and len(cached_segments) == len(segments_data):
            logger.info("Phase 3 cache hit. Skipping synthesis.")
            return Phase3Payload(
                job_id=job_id,
                template_name=template_name,
                persona_id=persona_id,
                segments=cached_segments,
                tts_settings=tts_settings,
                under_run_retries_used=0,
                inputs_hash=current_hash,
            )

    logger.info("Initiating Phase 3 synthesis loop.")
    is_offline = os.getenv("PHASE3_OFFLINE", "0") == "1"
    skip_underrun = os.getenv("PHASE3_SKIP_UNDERRUN", "0") == "1"

    sem = asyncio.Semaphore(tts_settings.concurrency_limit)

    tasks = []
    if is_offline:
        session = None
        for idx, s_dict in enumerate(segments_data):
            tasks.append(
                _process_segment(
                    idx,
                    s_dict,
                    tts_settings,
                    session,
                    audio_dir,
                    sem,
                    template_name,
                    timing_registry,
                    True,
                    skip_underrun,
                )
            )
        results = await asyncio.gather(*tasks)
    else:
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for idx, s_dict in enumerate(segments_data):
                tasks.append(
                    _process_segment(
                        idx,
                        s_dict,
                        tts_settings,
                        session,
                        audio_dir,
                        sem,
                        template_name,
                        timing_registry,
                        False,
                        skip_underrun,
                    )
                )
            results = await asyncio.gather(*tasks)

    results.sort(key=lambda x: x[0])
    completed_segments = [seg for _, seg in results]

    updated_script = update_script_with_audio(script_payload, completed_segments)
    updated_script["phase3_inputs_hash"] = current_hash

    job_manifest = build_job_json(
        job_id=job_id,
        template_name=template_name,
        script_relpath="script/script.json",
        audio_dir_relpath="audio",
    )

    atomic_write_json(script_path, updated_script)
    atomic_write_json(job_json_path, job_manifest)

    payload = Phase3Payload(
        job_id=job_id,
        template_name=template_name,
        persona_id=persona_id,
        segments=completed_segments,
        tts_settings=tts_settings,
        under_run_retries_used=0,
        inputs_hash=current_hash,
    )
    logger.info("Phase 3 package generation complete.")
    return payload
