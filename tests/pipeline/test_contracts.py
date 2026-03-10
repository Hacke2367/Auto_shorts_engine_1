import json
import traceback
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def validate_data_manifest(payload: dict):
    """Validate data_manifest.json schema."""
    assert "template_name" in payload, "Missing template_name"
    assert "csv_relpath" in payload, "Missing csv_relpath"
    assert "dataset_relpath" in payload, "Missing dataset_relpath"
    assert "audit_relpath" in payload, "Missing audit_relpath"
    
    assert isinstance(payload["template_name"], str)
    assert isinstance(payload["csv_relpath"], str)
    assert isinstance(payload["dataset_relpath"], str)
    assert isinstance(payload["audit_relpath"], str)


def validate_internal_script(payload: dict):
    """Validate internal Phase 2 script.json requirements."""
    assert "job_id" in payload, "Missing job_id"
    assert "template_name" in payload, "Missing template_name"
    assert "segments" in payload, "Missing segments"
    assert isinstance(payload["segments"], list), "Segments must be a list"

    for seg in payload["segments"]:
        assert "tag" in seg, "Segment missing tag"
        assert "text" in seg, "Segment missing text"
        assert "target_min_chars" in seg, "Segment missing target_min_chars"
        assert "target_max_chars" in seg, "Segment missing target_max_chars"


def validate_engine_job(payload: dict):
    """Validate Phase 4 engine job.json constraints."""
    assert "template_id" in payload, "Missing template_id in engine job.json"
    assert "audio" in payload, "Missing audio block"
    assert "timeline" in payload, "Missing timeline block"
    assert "data_csv" in payload, "Missing data_csv"
    assert "output" in payload, "Missing output block"
    
    audio = payload["audio"]
    assert "order" in audio, "Audio missing order array"
    assert "segments" in audio, "Audio missing segments object"
    assert isinstance(audio["order"], list)
    assert isinstance(audio["segments"], list)


def validate_engine_script(payload: dict):
    """Validate Phase 4 engine script.json exactness."""
    assert "template_id" in payload, "Missing template_id in engine script.json"
    assert "segments" in payload, "Missing segments"
    assert isinstance(payload["segments"], list)
    
    for seg in payload["segments"]:
        assert "name" in seg, "Engine segment missing name"
        assert "text" in seg, "Engine segment missing text"
        assert "file" in seg, "Engine segment missing file"


def run_tests():
    print("--- Running test_contracts.py ---")
    
    # 1. Test data_manifest validation
    manifest_good = {
        "template_name": "vs_card",
        "csv_relpath": "data/vs_card_data.csv",
        "dataset_relpath": "data/vs_card_dataset.json",
        "audit_relpath": "data/sources_audit.json"
    }
    validate_data_manifest(manifest_good)
    
    manifest_bad = {"template_name": "foo"}
    try:
        validate_data_manifest(manifest_bad)
        raise AssertionError("Failed to catch bad data_manifest")
    except AssertionError as e:
        if "Failed to catch" in str(e): raise
        
    # 2. Test Internal Script validation
    internal_script_good = {
        "job_id": "test",
        "template_name": "vs_card",
        "segments": [{"tag": "HOOK", "text": "Hi", "target_min_chars": 10, "target_max_chars": 50}]
    }
    validate_internal_script(internal_script_good)

    # 3. Test Engine Job validation
    engine_job_good = {
        "template_id": "vs_card",
        "audio": {"order": ["hook"], "segments": [{"name": "hook", "path": "audio/hook.mp3"}]},
        "timeline": {},
        "data_csv": "data.csv",
        "output": {"final_mp4": "final.mp4"}
    }
    validate_engine_job(engine_job_good)
    
    # 4. Test Engine Script validation
    engine_script_good = {
        "template_id": "vs_card",
        "segments": [{"name": "hook", "text": "Hi", "file": "audio/hook.mp3"}]
    }
    validate_engine_script(engine_script_good)
    
    print("✅ test_contracts.py PASS")
    return True

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        traceback.print_exc()
        print("❌ test_contracts.py FAIL")
        exit(1)
