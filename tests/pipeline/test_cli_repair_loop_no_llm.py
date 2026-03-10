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

from unittest.mock import patch, AsyncMock

def run_tests():
    print("--- Running test_cli_repair_loop_no_llm.py ---")
    
    project_root = Path(__file__).resolve().parents[2]
    clean_sandbox(project_root)
    run_dir = create_run_dir(SANDBOX_BUCKET)
    
    # Setup state
    data_dir = run_dir / "data"
    (data_dir / "data_manifest.json").write_text('{"template_name": "vs_card", "csv_relpath": "", "dataset_relpath": "data/vs_card_dataset.json", "audit_relpath": ""}')
    (data_dir / "vs_card_dataset.json").write_text('{"dummy": "dataset"}')
    
    script_dir = run_dir / "script"
    script_data = {
        "job_id": run_dir.name,
        "template_name": "vs_card",
        "persona_id": "test",
        "voice_cps": 15,
        "segments": [
            {"tag": "HOOK", "text": "Too short.", "target_min_chars": 500, "target_max_chars": 600},
        ]
    }
    with open(script_dir / "script.json", "w") as f:
        json.dump(script_data, f)
        
    os.environ["PHASE3_OFFLINE"] = "1"
    
    # RUN REPAIR with UnderRun strictness ACTIVE
    os.environ["PHASE3_SKIP_UNDERRUN"] = "0"
    
    from src.cli.autoshorts import async_repair
    class DummyArgs:
        job = str(run_dir)
        template = "vs_card"
        persona = "test"
        max_tries = 1
        offline = True
        skip_underrun = False
        voice_id = "OFFLINE"
        model_id = "OFFLINE"
        output_format = "mp3"
        concurrency = 3
        force = False
        
    args = DummyArgs()
    
    # Patch async_phase2 to avoid LLM validation rules entirely
    with patch("src.cli.autoshorts.async_phase2", new_callable=AsyncMock) as mock_p2:
        try:
            asyncio.run(async_repair(args))
            raise AssertionError("Repair loop did not fail via UnderRun exhaustion!")
        except RuntimeError as e:
            if "Max retries hit" in str(e):
                print("✅ UnderRunError trapped and Exhausted gracefully as expected.")
                assert mock_p2.call_count >= 1, "Phase2 was not retried by repair loop!"
            else:
                raise
                
    # Now TEST WITHOUT UnderRun strictness (SKIP bounds)
    args.skip_underrun = True
    os.environ["PHASE3_SKIP_UNDERRUN"] = "1"
    
    with patch("src.cli.autoshorts.async_phase2", new_callable=AsyncMock) as mock_p2:
        asyncio.run(async_repair(args))
        print("✅ Repair Loop passed with UnderRun skipped.")
    
    clean_sandbox(project_root)
    print("✅ test_cli_repair_loop_no_llm.py PASS")
    return True

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        traceback.print_exc()
        print("❌ test_cli_repair_loop_no_llm.py FAIL")
        exit(1)
