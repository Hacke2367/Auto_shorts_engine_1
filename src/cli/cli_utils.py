import logging
import uuid
from datetime import datetime
from pathlib import Path
import yaml

from src.agents.core.job_manager import JobManager

def resolve_bucket(template_name: str) -> str:
    """Resolve standard template name to directory bucket via bucket_map.yaml."""
    # Find the .agent/context/bucket_map.yaml file relative to this script
    # This script is at src/cli/cli_utils.py -> parents[2] is PROJECT_ROOT
    project_root = Path(__file__).resolve().parents[2]
    map_yaml = project_root / ".agent" / "context" / "bucket_map.yaml"
    
    if map_yaml.exists():
        with open(map_yaml, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
            if template_name in mapping:
                return mapping[template_name]
                
    # Fallback to naive logic if file missing or entry missing
    base = template_name.split("_")[0]
    return f"{base}_job"


def create_run_dir(bucket_name: str) -> Path:
    """Create a structured job run folder matching the engine rules."""
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    run_id = f"job_{now}_{short_id}"
    
    # Needs to match main loop structure from project root
    project_root = Path(__file__).resolve().parents[2]
    run_dir = project_root / "jobs" / bucket_name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Create standard pipeline subdirs
    for sub in ["data", "script", "audio", "output", "logs"]:
        (run_dir / sub).mkdir(exist_ok=True)
        
    return run_dir


def get_cli_job_manager(run_dir: Path, template_name: str) -> JobManager:
    """Instantiate a JobManager forcibly pointed at an existing run_dir.
    
    JobManager usually builds paths via `jobs_root / template_name / job_id`.
    This bypasses that logic to map exactly to custom CLI bucket directory logic
    while remaining fully compatible with Phase 1 / Phase 2 state systems.
    """
    jm = JobManager(template_name=template_name, job_id=run_dir.name)
    
    # Override paths to map strictly to our CLI-provided run_dir
    jm._job_dir = run_dir.resolve()
    jm._state_file = jm._job_dir / ".pipeline_state.json"
    
    import json
    
    if not jm.get_step_metadata("phase1_extraction") and not jm.get_step_metadata("phase1b_extraction"):
        manifest_file = run_dir / "data" / "data_manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                
                inferred_tpl = template_name
                for k in manifest.keys():
                    if k.endswith("_dataset.json"):
                        inferred_tpl = k.replace("_dataset.json", "")
                        break
                        
                jm.mark_step_completed("phase1b_extraction", {"template": inferred_tpl})
            except Exception:
                pass
        
    return jm


def setup_cli_logger(run_dir: Path) -> logging.Logger:
    """Set up logger mirroring execution progression cleanly to the run log."""
    logger = logging.getLogger("autoshorts_cli")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    # Console output
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console)
    
    # File output
    log_file = run_dir / "logs" / "pipeline_execution.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s [%(module)s] %(message)s"))
    logger.addHandler(file_h)
    
    return logger
