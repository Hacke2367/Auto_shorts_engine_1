import json
import traceback
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cli.cli_utils import create_run_dir
from tests.pipeline.test_filesystem_layout import clean_sandbox, SANDBOX_BUCKET
from tests.pipeline.test_contracts import validate_engine_job, validate_engine_script

def run_tests():
    print("--- Running test_handoff_builder.py ---")
    
    project_root = Path(__file__).resolve().parents[2]
    clean_sandbox(project_root)
    run_dir = create_run_dir(SANDBOX_BUCKET)
    
    # 1. Fake Phase 3 updated script
    script_dir = run_dir / "script"
    audio_dir = run_dir / "audio"
    data_dir = run_dir / "data"
    
    script_data = {
        "job_id": run_dir.name,
        "template_name": "vs_card",
        "segments": [
            {"tag": "HOOK", "text": "Hook text.", "audio_relpath": "audio/HOOK.mp3", "duration_ms": 1000},
            {"tag": "ITEM_1", "text": "Item text.", "audio_relpath": "audio/ITEM_1.mp3", "duration_ms": 2000},
        ]
    }
    with open(script_dir / "script.json", "w") as f:
        json.dump(script_data, f)
        
    # 2. Fake Audio files
    (audio_dir / "HOOK.mp3").write_bytes(b"dummy")
    (audio_dir / "ITEM_1.mp3").write_bytes(b"dummy")
    
    # 3. Fake CSV and manifest
    (data_dir / "vs_card_data.csv").write_text("fake,csv\n")
    (data_dir / "data_manifest.json").write_text('{"template_name": "vs_card", "csv_relpath": "data/vs_card_data.csv", "dataset_relpath": "", "audit_relpath": ""}')

    # RUN HANDOFF
    from src.cli.autoshorts import sync_handoff
    class DummyArgs:
        job = str(run_dir)
        
    sync_handoff(DummyArgs())
    
    engine_job_path = run_dir / "job.json"
    engine_script_path = script_dir / "engine_script.json"
    
    assert engine_job_path.exists(), "engine job.json not created"
    assert engine_script_path.exists(), "engine_script.json not created"
    
    # Validate payload schemas
    with open(engine_job_path, "r") as f:
        job_data = json.load(f)
    validate_engine_job(job_data)
    
    with open(engine_script_path, "r") as f:
        eng_script = json.load(f)
    validate_engine_script(eng_script)
    
    # Validate values internally
    assert job_data["template_id"] == "vs_card"
    assert job_data["audio"]["order"] == ["hook", "item1"], "Tags not lowercased/aliased correctly"
    assert job_data["data_csv"] == str(Path("data", "vs_card_data.csv"))
    
    # Check alias copying logic in FS
    assert (audio_dir / "hook.mp3").exists(), "Alias hook.mp3 not created!"
    assert (audio_dir / "item1.mp3").exists(), "Alias item1.mp3 not created!"
    
    clean_sandbox(project_root)
    print("✅ test_handoff_builder.py PASS")
    return True

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        traceback.print_exc()
        print("❌ test_handoff_builder.py FAIL")
        exit(1)
