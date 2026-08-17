"""
AutoShorts Phase 2 Scripting — Runner
======================================
The orchestrator for Phase 2. Takes a completed Phase 1 JobManager,
locates the dataset, builds the deterministic segment plan, validates
idempotency, invokes the LLM writer, and persists the payload.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import aiohttp

from src.agents.core.config import APP_CONFIG
from src.agents.core.job_manager import PROJECT_ROOT, JobManager
from src.agents.core.models import TemplateDataset
from src.agents.phase2_scripting.contracts import ScriptPayload
from src.agents.phase2_scripting.llm_writer import write_script
from src.agents.phase2_scripting.timing import build_segment_plan

logger = logging.getLogger(__name__)

ENGINE_VERSION = "v1.4"


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    return _hash_bytes(path.read_bytes())


def _get_dataset_path(jm: JobManager, template_name: str) -> Path:
    """Resolve the dataset JSON path deterministically.

    Priority:
    1. Explicit ``dataset_relpath`` in ``data_manifest.json`` — written by Phase 1B,
       always points to the correct attempt directory.
    2. Filesystem search sorted by mtime descending — most recently written file wins.
       Used only when the manifest is absent or unreadable.
    """
    manifest_path = jm.data_dir / "data_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            rel = manifest.get("dataset_relpath", "")
            if rel:
                resolved = (jm.job_dir / rel).resolve()
                if resolved.exists():
                    logger.debug("Dataset path from data_manifest.json: %s", resolved)
                    return resolved
                logger.warning(
                    "data_manifest.json dataset_relpath points to missing file: %s — falling back to search.",
                    resolved,
                )
        except Exception as exc:
            logger.warning("Failed to read data_manifest.json: %s — falling back to search.", exc)

    # Fallback: sort by mtime so the most recently extracted attempt always wins.
    candidates = sorted(
        jm.job_dir.rglob(f"{template_name}_dataset.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"Could not locate {template_name}_dataset.json anywhere under {jm.job_dir}. "
            "Ensure Phase 1B extraction completed successfully."
        )
    logger.info(
        "Dataset path resolved via filesystem search (manifest unavailable): %s", candidates[0]
    )
    return candidates[0]


def _validate_phase2_inputs(jm: JobManager, log: logging.Logger) -> None:
    """Validate Phase 1B outputs are present and readable before any Phase 2 work begins.

    Raises:
        FileNotFoundError: If required input files are missing on disk.
        ValueError: If ``data_manifest.json`` is malformed or has stale paths.
    """
    manifest_path = jm.data_dir / "data_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Phase 2 validation failed: data_manifest.json not found at {manifest_path}. "
            "Run Phase 1B extraction before Phase 2."
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(
            f"Phase 2 validation failed: data_manifest.json is not valid JSON: {exc}"
        ) from exc

    for required_key in ("template_name", "dataset_relpath"):
        if not manifest.get(required_key):
            raise ValueError(
                f"Phase 2 validation failed: data_manifest.json missing required field '{required_key}'."
            )

    dataset_path = (jm.job_dir / manifest["dataset_relpath"]).resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Phase 2 validation failed: dataset file not found at {dataset_path}. "
            "data_manifest.json may reference a stale extraction attempt."
        )

    csv_relpath = manifest.get("csv_relpath", "")
    if csv_relpath:
        csv_path = (jm.job_dir / csv_relpath).resolve()
        if not csv_path.exists():
            raise FileNotFoundError(
                f"Phase 2 validation failed: CSV file not found at {csv_path}. "
                "data_manifest.json may reference a stale extraction attempt."
            )

    log.info(
        "Phase 2 input validation passed — manifest OK, dataset and CSV present."
    )


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
    sys_dir = personas_dir / "system_prompt"   # canonical path — matches llm_writer.py SYSTEM_PROMPTS_DIR

    parts = [
        _hash_file(dataset_path),
        template_name,
        persona_id,
        str(voice_cps),
        _hash_file(context_dir / "template_segment_truth.yaml"),
        _hash_file(context_dir / "template_timing_registry.yaml"),
        _hash_file(context_dir / "template_visual_rules.md"),
        _hash_file(context_dir / "commentary_mode.md"),
        _hash_file(context_dir / "voice_profiles.yaml"),
        _hash_file(personas_dir / "shared_output_contract.md"),
        _hash_file(personas_dir / "voice_and_scriptcraft.md"),
        _hash_file(personas_dir / f"{persona_id}.md"),
        _hash_file(sys_dir / f"{persona_id}_system.md"),
        str(APP_CONFIG.script_doctor_enabled),
        ENGINE_VERSION,
        # WHO wrote the script is an input, not an implementation detail. Without
        # this, changing provider/model/effort reuses the previous model's cached
        # script.json and the change looks like it did nothing.
        _llm_route_fingerprint(),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _llm_route_fingerprint() -> str:
    """Identity of every LLM route that contributes to a script."""
    llm = APP_CONFIG.llm
    return ";".join(
        f"{name}={r.provider}:{r.model}:{r.reasoning_effort}:{r.verbosity}:"
        f"{r.temperature}:{r.thinking_budget}"
        for name, r in (
            ("draft", llm.scripting_draft),
            ("rewrite", llm.scripting_rewrite),
            ("doctor", llm.scripting_doctor),
        )
    )


def _load_dataset(dataset_path: Path, template_name: str) -> TemplateDataset:
    try:
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Corrupt dataset JSON at {dataset_path}: {exc}"
        ) from exc

    # Support both shapes:
    # 1) raw is dict with {template_name, rows:[...]}
    # 2) raw is list of row dicts (legacy shape)
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
    log.info(
        "Starting Phase 2 Scripting for Job %s using persona '%s'",
        job_manager.job_id, persona_id,
    )

    # Validate all Phase 1B outputs are present before any LLM work begins.
    _validate_phase2_inputs(job_manager, log)

    template_name = _resolve_phase1_template(job_manager)

    dataset_path = _get_dataset_path(job_manager, template_name)
    dataset = _load_dataset(dataset_path, template_name)

    plan = build_segment_plan(job_manager.job_id, template_name, persona_id, dataset)
    effective_cps = plan.voice_cps

    inputs_hash = _build_inputs_hash(dataset_path, template_name, persona_id, effective_cps)
    log.info("Phase 2 inputs hash: %s", inputs_hash)

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
            log.warning("Failed to load cached script: %s. Regenerating.", e)

    timeout = aiohttp.ClientTimeout(total=APP_CONFIG.api_timeout_seconds)
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

    # Atomic write of script.json — temp file → os.replace prevents corrupt cache on crash.
    _script_content = payload.model_dump_json(indent=2)
    _json_fd, _json_tmp = tempfile.mkstemp(dir=str(script_dir), suffix=".tmp")
    try:
        with os.fdopen(_json_fd, "w", encoding="utf-8") as _f:
            _f.write(_script_content)
        os.replace(_json_tmp, str(script_json_path))
    except BaseException:
        try:
            os.unlink(_json_tmp)
        except OSError:
            pass
        raise

    # Atomic write of llm_raw.txt audit file.
    _raw_fd, _raw_tmp = tempfile.mkstemp(dir=str(script_dir), suffix=".tmp")
    try:
        with os.fdopen(_raw_fd, "w", encoding="utf-8") as _f:
            _f.write(raw_history)
        os.replace(_raw_tmp, str(script_dir / "llm_raw.txt"))
    except BaseException:
        try:
            os.unlink(_raw_tmp)
        except OSError:
            pass
        raise

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