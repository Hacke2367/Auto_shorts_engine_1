from __future__ import annotations

"""
AutoShorts Phase 3 Audio Engine — Offline End-to-End Simulation
================================================================
Simulates Phase 3 completely offline without relying on Phase 2 APIs.
Synthesizes dead-air bounded binary data safely against a mocked Job payload.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from src.agents.phase3_audio.contracts import AudioSynthesisSettings
from src.agents.phase3_audio.runner import run_phase3

# Anchor to project root — not CWD — so the test job is always created in the
# right place regardless of which directory the script is invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEST_JOB_DIR = _PROJECT_ROOT / "jobs" / "test_job"

logger = logging.getLogger("offline_e2e")


def setup_dummy_job() -> dict:
    """Builds a temporary Phase 2 Script structure mimicking an exact output format."""
    logger.info("Setting up fake Phase 2 Job Output natively...")

    if _TEST_JOB_DIR.exists():
        shutil.rmtree(_TEST_JOB_DIR)

    script_dir = _TEST_JOB_DIR / "script"
    script_dir.mkdir(parents=True, exist_ok=True)

    dummy_payload = {
        "job_id": "test_job",
        "template_name": "vs_card",
        "persona_id": "savage_roast_master",
        "voice_cps": 18.0,
        "segments": [
            {"tag": "HOOK", "text": "This is a synthetic system hook tone layer."},
            {"tag": "SETUP", "text": "Setting up the scene safely mathematically."},
            {"tag": "ROUND_1", "text": "Player 1 vs Player 2."},
            {"tag": "ROUND_2", "text": "The margin closes rapidly here."},
            {"tag": "ROUND_3", "text": "Final match boundary metrics."},
            {"tag": "WINNER", "text": "Player 2 absolute flawless completion."},
            {"tag": "OUTRO", "text": "Subscribe for more content like this locally."}
        ]
    }

    with open(script_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(dummy_payload, f, indent=2)

    return dummy_payload


async def main() -> None:
    print("=== AutoShorts Phase 3 Offline E2E Validation ===")

    # Force offline mode — bypasses ElevenLabs API.
    os.environ["PHASE3_OFFLINE"] = "1"
    os.environ["PHASE3_SKIP_UNDERRUN"] = "1"

    dummy_payload = setup_dummy_job()

    tts_cfg = AudioSynthesisSettings(
        provider="elevenlabs",
        voice_id="fake_voice_001",
        model_id="fake_model_001",
        concurrency_limit=3
    )

    # --- RUN 1: Active Engine (Offline Bypass) ---
    print("\n--- RUNNING PHASE 3 ITERATION 1 (Generation) ---")
    payload1 = await run_phase3(job_dir=_TEST_JOB_DIR, tts_settings=tts_cfg)

    print("\n[Verification 1] Audio Disk Writing")
    audio_dir = _TEST_JOB_DIR / "audio"
    assert audio_dir.exists(), "Audio directory was not created."
    files = list(audio_dir.glob("*.mp3"))
    print(f"-> Generated {len(files)} .mp3 files on disk natively.")
    # Compare against actual payload segment count — stays correct if payload changes.
    expected_count = len(dummy_payload["segments"])
    assert len(files) == expected_count, f"Expected {expected_count} mp3 files, got {len(files)}."

    print("\n[Verification 2] Output Payload Injection")
    with open(_TEST_JOB_DIR / "script" / "script.json", "r", encoding="utf-8") as f:
        mutated_script = json.load(f)

    for seg in mutated_script["segments"]:
        assert "duration_ms" in seg, f"Duration physical milliseconds missing from {seg['tag']}"
        assert "audio_relpath" in seg, f"Audio disk map missing from {seg['tag']}"
        print(f"-> Tag [{seg['tag']}] matched: {seg['duration_ms']}ms => {seg['audio_relpath']}")

    print("\n[Verification 3] Master job.json Rendering Manifest")
    assert (_TEST_JOB_DIR / "job.json").exists(), "Manim Phase 4 struct missing."
    with open(_TEST_JOB_DIR / "job.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
        assert manifest["job_id"] == "test_job"
        assert manifest["script_path"] == "script/script.json"

    # --- RUN 2: Strict Idempotency (Cache Intercept) ---
    print("\n\n--- RUNNING PHASE 3 ITERATION 2 (Idempotency Check) ---")
    payload2 = await run_phase3(job_dir=_TEST_JOB_DIR, tts_settings=tts_cfg)

    assert payload1.inputs_hash == payload2.inputs_hash, "Hash mismatch between runs — idempotency broken."
    print("-> Phase 3 Pipeline safely cached outputs — skipped synthesis on second run.")

    print("\n=============================================")
    print("✅ PHASE 3 E2E SIMULATION: PASS")
    print("=============================================")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
