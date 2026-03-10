"""
AutoShorts Phase 2 Scripting — Runner
======================================
The orchestrator for Phase 2. Takes a completed Phase 1 JobManager,
locates the dataset, builds the deterministic segment plan, validates
idempotency, invokes the LLM writer, and persists the payload.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from src.agents.core.config import settings
from src.agents.core.job_manager import PROJECT_ROOT, JobManager
from src.agents.core.models import TemplateDataset
from src.agents.phase2_scripting.contracts import ScriptPayload
from src.agents.phase2_scripting.llm_writer import write_script
from src.agents.phase2_scripting.timing import build_segment_plan

logger = logging.getLogger(__name__)

ENGINE_VERSION = "v1.2"


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    return _hash_bytes(path.read_bytes())


def _get_dataset_path(jm: JobManager, template_name: str) -> Path:
    candidates = list(jm.job_dir.rglob(f"{template_name}_dataset.json"))
    if not candidates:
        raise FileNotFoundError(f"Could not locate {template_name}_dataset.json in {jm.job_dir}")
    return candidates[0]


def _resolve_phase1_template(jm: JobManager) -> str:
    # Try likely step names / keys
    step_names = ["phase1b_extraction", "phase1b_extract", "phase1_extraction", "phase1_extract"]
    meta: Optional[Dict[str, Any]] = None
    for s in step_names:
        m = jm.get_step_metadata(s)
        if m:
            meta = m
            break
    if not meta:
        raise RuntimeError("Phase 1 extraction metadata not found. Cannot run Phase 2.")

    # common key variants
    for k in ["template", "selected_template", "best_fit_template"]:
        if meta.get(k):
            return str(meta[k])

    raise RuntimeError(f"Phase 1 extraction metadata missing template field. Found keys: {list(meta.keys())}")


def _build_inputs_hash(
    dataset_path: Path,
    template_name: str,
    persona_id: str,
    voice_cps: float,
) -> str:
    context_dir = PROJECT_ROOT / ".agent" / "context"
    personas_dir = context_dir / "personas"
    sys_dir = personas_dir / "system_prompts"

    parts = [
        _hash_file(dataset_path),
        template_name,
        persona_id,
        str(voice_cps),
        _hash_file(context_dir / "template_segment_truth.yaml"),
        _hash_file(context_dir / "template_timing_registry.yaml"),
        _hash_file(context_dir / "template_visual_rules.md"),
        _hash_file(context_dir / "voice_profiles.yaml"),
        _hash_file(personas_dir / "shared_output_contract.md"),
        _hash_file(personas_dir / f"{persona_id}.md"),
        _hash_file(sys_dir / f"{persona_id}_system.md"),
        ENGINE_VERSION,
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_dataset(dataset_path: Path, template_name: str) -> TemplateDataset:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))

    # Support both shapes:
    # 1) raw is dict with {template_name, rows:[...]}
    # 2) raw is list of row dicts
    if isinstance(raw, dict):
        return TemplateDataset.model_validate(raw)

    if isinstance(raw, list):
        wrapped = {"template_name": template_name, "rows": raw}
        return TemplateDataset.model_validate(wrapped)

    raise ValueError(f"Unsupported dataset JSON shape in {dataset_path}: {type(raw)}")


async def run_scripting(
    job_manager: JobManager,
    persona_id: str = "savage_roast_master",
) -> ScriptPayload:
    step_name = "phase2_scripting"
    log = job_manager.get_logger()
    log.info(f"Starting Phase 2 Scripting for Job {job_manager.job_id} using persona '{persona_id}'")

    template_name = _resolve_phase1_template(job_manager)

    dataset_path = _get_dataset_path(job_manager, template_name)
    dataset = _load_dataset(dataset_path, template_name)

    plan = build_segment_plan(job_manager.job_id, template_name, persona_id, dataset)
    effective_cps = plan.voice_cps

    inputs_hash = _build_inputs_hash(dataset_path, template_name, persona_id, effective_cps)
    log.info(f"Phase 2 inputs hash: {inputs_hash}")

    script_dir = job_manager.job_dir / "script"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_json_path = script_dir / "script.json"

    if script_json_path.exists():
        try:
            cached = json.loads(script_json_path.read_text(encoding="utf-8"))
            cached_payload = ScriptPayload.model_validate(cached)
            if cached_payload.inputs_hash == inputs_hash:
                log.info("Valid cached script matches inputs hash. Skipping LLM generation.")
                job_manager.mark_step_completed(step_name, {"source": "cache"})
                return cached_payload
            log.info("Inputs hash mismatch. Invalidating stale cache.")
        except Exception as e:
            log.warning(f"Failed to load cached script: {e}. Regenerating.")

    timeout = aiohttp.ClientTimeout(total=settings.api_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        final_segments, raw_history = await write_script(plan, dataset, session, log)

    payload = ScriptPayload(
        job_id=job_manager.job_id,
        template_name=template_name,
        persona_id=persona_id,
        voice_cps=effective_cps,
        inputs_hash=inputs_hash,
        segments=final_segments,
    )

    script_json_path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    (script_dir / "llm_raw.txt").write_text(raw_history, encoding="utf-8")

    job_manager.mark_step_completed(
        step_name,
        metadata={
            "persona_id": persona_id,
            "hash": inputs_hash,
            "segments_count": len(final_segments),
            "source": "generated",
        },
    )

    log.info("Phase 2 Scripting COMPLETE. Payload persisted.")
    return payload