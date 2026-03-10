import os
import json
import asyncio
import traceback
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cli.cli_utils import create_run_dir
from tests.pipeline.test_filesystem_layout import clean_sandbox, SANDBOX_BUCKET

def run_tests():
    print("--- Running test_phase3_offline_idempotency.py ---")
    
    project_root = Path(__file__).resolve().parents[2]
    clean_sandbox(project_root)
    run_dir = create_run_dir(SANDBOX_BUCKET)
    
    # 1. Provide dummy internal script/script.json
    script_dir = run_dir / "script"
    script_data = {
        "job_id": run_dir.name,
        "template_name": "vs_card",
        "persona_id": "test_persona",
        "voice_cps": 15,
        "segments": [
            {"tag": "ITEM_1", "text": "Testing one.", "target_min_chars": 1, "target_max_chars": 100},
            {"tag": "ITEM_2", "text": "Testing two.", "target_min_chars": 1, "target_max_chars": 100},
            {"tag": "ITEM_3", "text": "Testing three.", "target_min_chars": 1, "target_max_chars": 100},
        ]
    }
    script_file = script_dir / "script.json"
    with open(script_file, "w") as f:
        json.dump(script_data, f)
        
    # Set env
    os.environ["PHASE3_OFFLINE"] = "1"
    os.environ["PHASE3_SKIP_UNDERRUN"] = "1"
    
    # Run Phase3 (Run 1)
    from src.cli.autoshorts import async_phase3
    class DummyArgs:
        job = str(run_dir)
        offline = True
        skip_underrun = True
        voice_id = "OFFLINE"
        model_id = "OFFLINE"
        output_format = "mp3_44100_128"
        concurrency = 3
        
    asyncio.run(async_phase3(DummyArgs()))
    
    # Validate audio outputs
    audio_dir = run_dir / "audio"
    for tag in ["ITEM_1", "ITEM_2", "ITEM_3"]:
        assert (audio_dir / f"{tag}.mp3").exists(), f"Missing audio for {tag}"
        
    # Validate written script contains updated duration keys
    with open(script_file, "r") as f:
        updated = json.load(f)
        
    assert "phase3_inputs_hash" in updated, "Missing inputs hash"
    hash_run_1 = updated["phase3_inputs_hash"]
    
    for seg in updated["segments"]:
        assert "duration_ms" in seg, f"Missing duration_ms in {seg['tag']}"
        assert "audio_relpath" in seg, f"Missing audio_relpath in {seg['tag']}"
        
    # Store mp3 mod times
    mod_times = {p: p.stat().st_mtime for p in audio_dir.glob("*.mp3")}
    
    # Run Phase3 (Run 2) - should cache hit
    print("Executing RUN 2 (Cache check)...")
    asyncio.run(async_phase3(DummyArgs()))
    
    with open(script_file, "r") as f:
        updated_2 = json.load(f)
        
    assert updated_2["phase3_inputs_hash"] == hash_run_1, "Hash unstable"
    
    for p in audio_dir.glob("*.mp3"):
        assert p.stat().st_mtime == mod_times[p], f"{p.name} was regenerated instead of cached!"
        
    clean_sandbox(project_root)
    print("✅ test_phase3_offline_idempotency.py PASS")
    return True

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        traceback.print_exc()
        print("❌ test_phase3_offline_idempotency.py FAIL")
        exit(1)
