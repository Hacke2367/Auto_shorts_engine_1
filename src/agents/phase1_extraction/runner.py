"""
AutoShorts Phase 1B — Extraction Runner
========================================
Entry point for Phase 1B. Takes one approved topic + chosen template,
runs the extraction LangGraph, validates output quality, and persists
the strict dataset plus audit trail.

Design Principles:
  - Strongly idempotent: skips work if step already completed.
  - Manages context-scoped aiohttp.ClientSession.
  - Serialises the validated dataset into both JSON and CSV.
  - Persists the AuditTrail securely.
  - Includes dataset quality gates before marking success.
  - Orchestrates real fallback attempt if best-fit extraction fails.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
from pathlib import Path

try:
    from typing import NotRequired, TypedDict
except ImportError:
    from typing_extensions import NotRequired, TypedDict

import aiohttp

from src.agents.core.config import settings
from src.agents.core.job_manager import JobManager
from src.agents.core.logger import timed_operation
from src.agents.core.models import (
    AuditTrail,
    DataSchemaSpec,
    TemplateDataset,
    TemplateSpec,
    TEMPLATE_CAPACITIES,
    TEMPLATE_ROW_MAP,
    VALID_TEMPLATES,
)
from src.agents.phase1_extraction.graph import ExtractionState, build_extraction_graph

logger = logging.getLogger(__name__)

# Quality thresholds
MAX_NULL_RATE: float = 0.30  # Allow up to 30% null/empty fields per dataset
MIN_USABLE_ROWS: int = 2    # Minimum rows after cleaning


# Sentinel value for mnd_sec when Phase 1 does not have timing truth.
# Phase 2 (video engine) MUST hydrate real timing values before rendering.
# This sentinel is intentionally non-empty so consumers can detect that
# timing data has NOT been resolved yet.
_MND_SEC_PENDING: dict[str, float] = {"_phase2_pending": 0.0}


def _write_data_manifest(job_manager: "JobManager", manifest_data: dict) -> None:
    """Write extraction data manifest atomically to the job's data directory.

    Extraction-phase concern only — intentionally NOT on JobManager (SRP).
    Uses the same temp-file → os.replace pattern as job_manager._write_state.
    """
    data_dir = job_manager.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = data_dir / "data_manifest.json"

    fd, tmp_path = tempfile.mkstemp(dir=str(data_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        os.replace(tmp_path, str(manifest_path))
        job_manager.get_logger().info("Generated stable data_manifest.json contract.")
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _build_template_spec(template_name: str) -> TemplateSpec:
    """Build a TemplateSpec on the fly from models.py definitions.

    Note: ``mnd_sec`` is set to a documented sentinel because Phase 1
    does not own timing truth. Phase 2 MUST replace it before rendering.
    """
    row_cls = TEMPLATE_ROW_MAP[template_name]
    expected_cols = list(row_cls.model_fields.keys())

    return TemplateSpec(
        description=f"Auto-derived spec for {template_name}",
        capacity=TEMPLATE_CAPACITIES[template_name],
        data_schema=DataSchemaSpec(format="csv", expected_columns=expected_cols),
        mnd_sec=dict(_MND_SEC_PENDING),
    )


def _write_csv(dataset: TemplateDataset, path: Path, log: logging.Logger) -> None:
    """Export the TemplateDataset to CSV for the Manim engine (atomic write)."""
    if not dataset.rows:
        return

    static_tags = {
        "bar_chart": {"MAX": "100", "SORT": "DESC", "TOP_N": "10"},
        "scan_race": {"FEED": "FEED_RACE // LIVE", "FOOTER": "CONFIDENTIAL // VERIFIED", "TOPK": "5", "MAX_SERIES": "10"},
        "donut_breakdown": {"TOP": "8", "PANEL_TOP": "6", "OTHERS_MIN_PCT": "2", "MODE": "DONUT"},
        "sort_card": {"FEED": "FEED_SORT // TRIBUNAL"},
        "vs_card": {"P1_IMG": "player1.png", "P2_IMG": "player2.png"},
    }

    combined_meta = dict(dataset.meta)
    if dataset.template_name in static_tags:
        combined_meta.update(static_tags[dataset.template_name])

    headers = list(dataset.rows[0].model_dump().keys())

    # Write to temp file then atomically replace
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            # Write Meta Tags
            if dataset.template_name == "scan_race":
                for k, v in combined_meta.items():
                    f.write(f"#{k}={v}\n")
            else:
                if combined_meta:
                    meta_line = ", ".join(f"{k}={v}" for k, v in combined_meta.items())
                    f.write(f"# {meta_line}\n")
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in dataset.rows:
                writer.writerow(row.model_dump())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    log.info("Saved CSV tags and data to %s", path.name)


def _validate_dataset_quality(
    dataset: TemplateDataset, template_name: str, log: logging.Logger
) -> tuple[bool, str]:
    """Validate extracted dataset meets minimum quality gates.

    Numeric 0 is considered valid data, not null/empty.
    Returns:
        Tuple of (is_valid, reason).
    """
    if not dataset.rows:
        return False, "Dataset has 0 rows."

    if len(dataset.rows) < MIN_USABLE_ROWS:
        return False, f"Too few rows: {len(dataset.rows)} < {MIN_USABLE_ROWS}."

    # Check capacity
    cap = TEMPLATE_CAPACITIES.get(template_name)
    if cap and len(dataset.rows) > cap.max:
        return False, f"Exceeds max capacity: {len(dataset.rows)} > {cap.max}."

    # Check null / empty rate (numeric zero is explicitly VALID data)
    total_fields = 0
    null_fields = 0
    for row in dataset.rows:
        dump = row.model_dump()
        for key, val in dump.items():
            total_fields += 1
            # Explicitly exclude numeric zero and floating point zero from being flagged as null
            if val is None or val == "":
                null_fields += 1

    null_rate = null_fields / total_fields if total_fields > 0 else 1.0
    if null_rate > MAX_NULL_RATE:
        return False, f"Null rate too high: {null_rate:.1%} > {MAX_NULL_RATE:.0%}."

    log.info(
        "Dataset quality OK: %d rows, null_rate=%.1f%%.",
        len(dataset.rows), null_rate * 100,
    )
    return True, "passed"


async def run_extraction(
    job_manager: JobManager,
    topic: str,
    output_dir: Path | None = None,
) -> TemplateDataset:
    """Execute the Phase 1B extraction workflow.

    Supports best-fit followed by fallback orchestration.

    Args:
        job_manager: Bound instance managing this specific job.
        topic: Approved topic to extract data for.
        output_dir: Optional override for output directory. Defaults to job_manager.data_dir.

    Returns:
        The validated extracted dataset.

    Raises:
        RuntimeError: If all extraction attempts fail or yield invalid datasets.
    """
    log = job_manager.get_logger()
    step_name = "phase1b_extraction"

    # -- 0. Resolve the real extraction template --
    # In auto-mode, job_manager.template_name may still be 'auto' if
    # set_template() was not called. We read the operator-selected
    # template from trusted discovery metadata as the source of truth.
    if job_manager.is_auto_mode:
        discovery_meta = job_manager.get_step_metadata("phase1_discovery") or {}
        best_fit = discovery_meta.get("selected_template")
        if not best_fit or best_fit not in VALID_TEMPLATES:
            raise RuntimeError(
                f"Auto-mode extraction implies discovery was approved. "
                f"Metadata missing/invalid selected_template: '{best_fit}'."
            )
    else:
        best_fit = job_manager.template_name

    # -- 1. Early Return Idempotency Check --
    if job_manager.is_step_completed(step_name):
        log.info("Phase 1B extraction already completed. Reading metadata...")
        completed_meta = job_manager.get_step_metadata(step_name) or {}
        actual_template = completed_meta.get("template", best_fit)

        if job_manager.is_auto_mode:
            # BUG-C2 fix: read the exact attempt_num that was stored — never derive it from attempt_type
            attempt_num = int(completed_meta.get("attempt_num", 1))
            target_dir = job_manager.get_attempt_dir(actual_template, attempt_num)
        else:
            attempt_type = completed_meta.get("attempt_type", "best_fit")
            target_dir = (output_dir or job_manager.data_dir) / attempt_type

        json_path = target_dir / f"{actual_template}_dataset.json"

        if json_path.exists():
            try:
                raw = json.loads(json_path.read_text(encoding="utf-8"))
                return TemplateDataset.model_validate(raw)
            except Exception:
                log.warning("Failed to parse cached dataset. Falling back to rerun extraction.")
                
    # -- 2. Determine Fallback Plan --
    # Discovery step saves fallback_template into its metadata
    discovery_meta = job_manager.get_step_metadata("phase1_discovery") or {}
    fallback = discovery_meta.get("fallback_template")
    
    attempts = [
        {"template": best_fit, "type": "best_fit"}
    ]
    if fallback and fallback in VALID_TEMPLATES and fallback != best_fit:
        attempts.append({"template": fallback, "type": "fallback"})
        
    # Track overarching failure reason
    last_error = "Unknown error"

    with timed_operation(log, step_name, topic=topic):
        for idx, attempt in enumerate(attempts, 1):
            t_name = attempt["template"]
            t_type = attempt["type"]

            log.info("--- Starting Extraction Attempt %d/%d (%s: %s) ---", idx, len(attempts), t_type, t_name)

            # Each attempt gets its own full timeout budget
            timeout = aiohttp.ClientTimeout(total=settings.api_timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                if t_name not in VALID_TEMPLATES:
                    log.error("Attempt failed: %s is not a valid template.", t_name)
                    last_error = f"Invalid template: {t_name}"
                    continue

                if job_manager.is_auto_mode:
                    # strict isolation
                    attempt_dir = job_manager.get_attempt_dir(t_name, idx)
                else:
                    # manual mode isolation
                    base_dir = output_dir or job_manager.data_dir
                    attempt_dir = base_dir / t_type
                    
                attempt_dir.mkdir(parents=True, exist_ok=True)
                spec = _build_template_spec(t_name)
                graph = build_extraction_graph()

                initial_state: ExtractionState = {
                    "topic": topic,
                    "template_name": t_name,
                    "template_spec": spec,
                    "session": session,
                    "log": log,
                    "attempt_number": idx,
                }

                # -- 3. Execute LangGraph for this Attempt --
                log.info("Invoking extraction graph for topic='%s', template='%s'", topic, t_name)
                final_state = await graph.ainvoke(initial_state)

                if final_state.get("failure_category"):
                    fail_cat = final_state.get("failure_category")
                    fail_rsn = final_state.get("failure_reason")
                    log.error("Extraction Graph Failed [%s]: %s -> %s", t_name, fail_cat, fail_rsn)
                    last_error = f"{fail_cat} on {t_name}: {fail_rsn}"
                    
                    # Log failure artifact for debuggability
                    fail_artifact = attempt_dir / f"{t_name}_failure.log"
                    fail_artifact.write_text(f"Category: {fail_cat}\nReason: {fail_rsn}\n", encoding="utf-8")
                    
                    if t_type == "best_fit" and len(attempts) > 1:
                        log.info("Best-fit attempt failed. Proceeding to isolated fallback attempt.")
                    
                    continue

                dataset: TemplateDataset | None = final_state.get("extracted_data")
                if not dataset:
                    last_error = f"extraction_failure: Yielded no data for {t_name}"
                    log.error(last_error)
                    if t_type == "best_fit" and len(attempts) > 1:
                        log.info("Best-fit attempt yielded no data. Proceeding to isolated fallback attempt.")
                    continue

                # -- 4. Quality Gate --
                is_valid, reason = _validate_dataset_quality(dataset, t_name, log)
                if not is_valid:
                    last_error = f"quality_failure on {t_name}: {reason}"
                    log.error(last_error)
                    
                    # Log failure artifact for debuggability
                    fail_artifact = attempt_dir / f"{t_name}_failure.log"
                    fail_artifact.write_text(f"Category: quality_failure\nReason: {reason}\n", encoding="utf-8")
                    
                    if t_type == "best_fit" and len(attempts) > 1:
                        log.info("Best-fit attempt failed quality gate. Proceeding to isolated fallback attempt.")
                    continue

                # -- 5. Persist Outputs --
                log.info("Extraction %s '%s' SUCCEEDED.", t_type, t_name)
                if t_type == "fallback":
                    log.info("Fallback extraction successful. Best-fit was successfully repaired.")
                
                trail = AuditTrail(job_id=job_manager.job_id, template_name=t_name)
                for audit in final_state.get("raw_context", []):
                    trail.add_source(audit)
                trail.save_to_file(attempt_dir)

                json_path = attempt_dir / f"{t_name}_dataset.json"
                # Atomic write: temp file → os.replace to prevent partial writes on crash
                _json_content = dataset.model_dump_json(indent=2)
                _json_fd, _json_tmp = tempfile.mkstemp(dir=str(attempt_dir), suffix=".tmp")
                try:
                    with os.fdopen(_json_fd, "w", encoding="utf-8") as _f:
                        _f.write(_json_content)
                    os.replace(_json_tmp, str(json_path))
                except BaseException:
                    try:
                        os.unlink(_json_tmp)
                    except OSError:
                        pass
                    raise

                csv_path = attempt_dir / f"{t_name}_data.csv"
                _write_csv(dataset, csv_path, log)

                # -- 6. Generate Data Manifest Truth --
                try:
                    rel_dir = attempt_dir.relative_to(job_manager.job_dir).as_posix()
                except ValueError:
                    # Fallback for custom absolute output_dir outside of job root
                    rel_dir = f"data/{t_type}" if not job_manager.is_auto_mode else f"attempts/{idx:02d}_{t_name}"

                manifest = {
                    "template_name": t_name,
                    "csv_relpath": f"{rel_dir}/{t_name}_data.csv",
                    "dataset_relpath": f"{rel_dir}/{t_name}_dataset.json",
                    "audit_relpath": f"{rel_dir}/sources_audit.json"
                }
                _write_data_manifest(job_manager, manifest)

                # -- 7. Mark Job Completed --
                job_manager.mark_step_completed(
                    step_name,
                    metadata={
                        "topic": topic,
                        "template": t_name,
                        "attempt_type": t_type,
                        "attempt_num": idx,   # store exact number for idempotent restart
                        "rows_extracted": len(dataset.rows),
                        "sources_audited": len(trail.sources),
                    },
                )
                
                # If auto-mode schema supports it, lock in chosen template so downstream uses it
                if job_manager.is_auto_mode:
                    job_manager.set_template(t_name)

                return dataset

    # If we fall out of the loop, all attempts failed
    raise RuntimeError(f"All extraction attempts failed. Last error: {last_error}")
