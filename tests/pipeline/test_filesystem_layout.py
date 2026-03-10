import shutil
import traceback
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cli.cli_utils import create_run_dir

SANDBOX_BUCKET = "test_sandbox"

def clean_sandbox(project_root: Path):
    sandbox_dir = project_root / "jobs" / SANDBOX_BUCKET
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir, ignore_errors=True)

def run_tests():
    print("--- Running test_filesystem_layout.py ---")
    
    project_root = Path(__file__).resolve().parents[2]
    clean_sandbox(project_root)
    
    # 1. Create temporary run folder
    run_dir = create_run_dir(SANDBOX_BUCKET)
    assert run_dir.exists(), "run_dir failed to create"
    assert run_dir.name.startswith("job_"), f"Unexpected run_dir name: {run_dir.name}"
    
    # Assert expected folder layout exists
    expected_subdirs = ["data", "script", "audio", "output", "logs"]
    for sub in expected_subdirs:
        assert (run_dir / sub).exists(), f"Missing required subdir: {sub}"
        assert (run_dir / sub).is_dir(), f"Not a directory: {sub}"
        
    # 2. Populate with dummy dataset artifacts
    data_dir = run_dir / "data"
    (data_dir / "vs_card_data.csv").write_text("dummy_csv,1\n")
    (data_dir / "vs_card_dataset.json").write_text('{"dummy": "dataset"}')
    (data_dir / "sources_audit.json").write_text('{"dummy": "audit"}')
    (data_dir / "data_manifest.json").write_text('{"template_name": "vs_card", "csv_relpath": "data/vs_card_data.csv", "dataset_relpath": "data/vs_card_dataset.json", "audit_relpath": "data/sources_audit.json"}')
    
    # 3. Assert no overwrites on repeated creation (a new ID should be drawn natively)
    run_dir_2 = create_run_dir(SANDBOX_BUCKET)
    assert run_dir_2 != run_dir, "Buckets clashing IDs somehow"
    
    # Verify dummy files survived
    assert (data_dir / "vs_card_data.csv").exists(), "Data dir wiped unexpectedly"
    
    clean_sandbox(project_root)
    print("✅ test_filesystem_layout.py PASS")
    return True

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        traceback.print_exc()
        print("❌ test_filesystem_layout.py FAIL")
        exit(1)
