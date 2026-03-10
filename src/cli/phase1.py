"""
AutoShorts Phase 1 CLI
======================
The final operator-facing command line interface for Phase 1 (Discovery & Extraction).

Provides complete manual and auto-mode control over the data pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import aiohttp

# Ensure src is in python path if ran directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agents.core.config import settings
from src.agents.core.job_manager import JobManager
from src.agents.phase1_discovery.archive_manager import ArchiveManager
from src.agents.phase1_discovery.discovery_runner import run_discovery
from src.agents.phase1_extraction.runner import run_extraction
from src.agents.core.models import VALID_TEMPLATES, QueuedTopic, TEMPLATE_FALLBACKS

# Configure a basic terminal logger for the CLI itself
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
cli_logger = logging.getLogger("phase1_cli")


# ---------------------------------------------------------------------------
# CLI Helpers
# ---------------------------------------------------------------------------


def _print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}\n")


def _print_candidate(idx: int, c: Any) -> None:
    """Print a candidate dict/model beautifully."""
    # Handle both dicts (from json) and Pydantic models
    if hasattr(c, "model_dump"):
        c = c.model_dump()

    score = c.get("final_score", 0.0)
    topic = c.get("topic", "Unknown")
    best_fit = c.get("best_fit_template", "None")
    fallback = c.get("fallback_template") or "None"
    reason = c.get("fit_reason", "")
    matters = c.get("why_it_matters", "")
    sources = c.get("candidate_sources", [])
    
    print(f"[{idx}] {topic}")
    print(f"    Score:    {score:.2f} / 10.0")
    print(f"    Template: {best_fit} (Fallback: {fallback})")
    print(f"    Why:      {matters}")
    if reason:
        print(f"    Fit:      {reason}")
    if sources:
        print(f"    Sources:  {len(sources)} unique URLs found")
    print("-" * 60)


def _load_candidates(jm: JobManager) -> list[dict[str, Any]]:
    path = jm.discovery_dir / "candidates.json"
    if not path.exists():
        cli_logger.error(f"Cannot find candidates.json at {path}")
        sys.exit(1)
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("candidates", [])


def _record_decision(
    jm: JobManager, 
    candidate: dict[str, Any], 
    decision: str, 
    chosen_template: str | None = None
) -> None:
    """Record the operator's decision in decisions.json and update Archive."""
    path = jm.discovery_dir / "decisions.json"
    decisions = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            decisions = json.load(f)
            
    # Check if already decided
    if any(d.get("topic") == candidate["topic"] for d in decisions):
        return

    record = {
        "topic": candidate["topic"],
        "normalized_topic": candidate["normalized_topic"],
        "decision": decision,
        "chosen_template": chosen_template,
        "reason": "CLI Operator decision"
    }
    decisions.append(record)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2)
        
    # Update Archive using the correct ArchiveManager API
    archive = ArchiveManager()
    if decision == "rejected":
        archive.mark_rejected(candidate["topic"], reason="CLI Rejected")
    elif decision == "queued":
        norm = ArchiveManager.normalize_topic(candidate["topic"])
        queued_topic = QueuedTopic(
            topic=candidate["topic"],
            normalized_topic=norm,
            best_fit_template=candidate.get("best_fit_template", ""),
            fallback_template=candidate.get("fallback_template"),
            final_score=candidate.get("final_score", 0.0),
            fit_reason=candidate.get("fit_reason", ""),
            source_hint=candidate.get("source_hint"),
        )
        archive.add_to_queue(queued_topic)

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_discover(args: argparse.Namespace) -> None:
    """Run Phase 1A Discovery."""
    _print_header("PHASE 1: DISCOVER")
    jm = JobManager(template_name="auto")
    jm.initialize()
    
    print(f"Job ID:  {jm.job_id}")
    print(f"Job Dir: {jm.job_dir}")
    print("Running discovery engines... This may take a minute.\n")
    
    timeout = aiohttp.ClientTimeout(total=settings.api_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        batch = await run_discovery(
            session=session,
            log=jm.get_logger(),
            output_dir=jm.discovery_dir,
            niche_hint=args.niche,
            top_n=args.top_n
        )
        
    _print_header("TOP CANDIDATES")
    for i, c in enumerate(batch.candidates, 1):
        _print_candidate(i, c)
        
    print(f"-> Candidates saved to: {jm.discovery_dir / 'candidates.json'}")
    print(f"-> To approve one, run: python -m src.cli.phase1 approve --job-id {jm.job_id} --index <N>")


async def cmd_auto(args: argparse.Namespace) -> None:
    """Run End-to-End Operator Flow."""
    _print_header("PHASE 1: AUTO-MODE (E2E)")
    jm = JobManager(template_name="auto")
    jm.initialize()
    
    print(f"Job ID:  {jm.job_id}")
    print("Running discovery engines... (fetching from web + AI scoring)\n")
    
    timeout = aiohttp.ClientTimeout(total=settings.api_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        batch = await run_discovery(
            session=session,
            log=jm.get_logger(),
            output_dir=jm.discovery_dir,
            niche_hint=args.niche,
            top_n=args.top_n
        )
        
    _print_header("TOP CANDIDATES")
    candidates = batch.candidates
    if not candidates:
        print("No candidates found. Exiting.")
        sys.exit(0)
        
    for i, c in enumerate(candidates, 1):
        _print_candidate(i, c)
        
    _print_header("OPERATOR DECISION")
    sel_input = input(f"Enter the index (1-{len(candidates)}) to SELECT (or 'q' to quit): ").strip()
    if not sel_input or sel_input.lower() == 'q':
        print("Aborting.")
        sys.exit(0)
        
    try:
        sel_idx = int(sel_input) - 1
        if sel_idx < 0 or sel_idx >= len(candidates):
            raise ValueError()
        selected = candidates[sel_idx].model_dump()
    except ValueError:
        print("Invalid index. Aborting.")
        sys.exit(1)
        
    # Optional Reject/Queue
    rej_input = input("Enter indices to REJECT (comma-separated, or leave blank): ").strip()
    que_input = input("Enter indices to QUEUE for later (comma-separated, or leave blank): ").strip()
    
    # Process decisions
    chosen_template = selected["best_fit_template"]
    _record_decision(jm, selected, "selected", chosen_template)
    jm.mark_step_completed("phase1_discovery", {
        "selected_topic": selected["topic"],
        "selected_template": chosen_template,
        "fallback_template": selected.get("fallback_template"),
    })
    # Lock the real template into auto-mode JobManager so runner.py sees it
    jm.set_template(chosen_template)
    
    for r in rej_input.split(","):
        r = r.strip()
        if r.isdigit() and 1 <= int(r) <= len(candidates) and int(r)-1 != sel_idx:
            _record_decision(jm, candidates[int(r)-1].model_dump(), "rejected")
            
    for q in que_input.split(","):
        q = q.strip()
        if q.isdigit() and 1 <= int(q) <= len(candidates) and int(q)-1 != sel_idx:
            _record_decision(jm, candidates[int(q)-1].model_dump(), "queued")
            
    _print_header("PHASE 1: EXTRACTION")
    print(f"Extracting dataset for: '{selected['topic']}'")
    print(f"Target Template: {selected['best_fit_template']}")
    print("Extracting... (this will use AI to structure the data)")
    
    # We must construct a new JobManager locked to the selected template? 
    # Actually, auto-mode JobManager stays "auto" but uses get_attempt_dir.
    try:
        dataset = await run_extraction(
            job_manager=jm,
            topic=selected["topic"]
        )
        print("\n[SUCCESS] Extraction completed.")
        ArchiveManager().mark_produced(selected["topic"], reason="CLI Auto Extract Success")
        actual = jm.get_step_metadata("phase1b_extraction").get("template", selected["best_fit_template"])
        attempt_dir = jm.get_attempt_dir(actual, 1) # Note: simplify to show final resting place
        
        # Determine actual dir by inspecting job manager or finding the json
        # In reality it is in attempt_dir, but fallback might be in attempt 2
        # Let's just run cmd_inspect directly to show the paths.
    except Exception as e:
        print(f"\n[ERROR] Extraction failed: {e}")
        
    print("\nFinal Job Paths:")
    await cmd_inspect(argparse.Namespace(job_id=jm.job_id, template=None))


async def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a candidate from a previous discovery job."""
    _print_header("PHASE 1: APPROVE & EXTRACT")
    jm = JobManager(template_name="auto", job_id=args.job_id)
    candidates = _load_candidates(jm)
    
    if args.index < 1 or args.index > len(candidates):
        print("Invalid index.")
        sys.exit(1)
        
    selected = candidates[args.index - 1]
    template = args.template or selected.get("best_fit_template")
    if template not in VALID_TEMPLATES:
        print(f"Invalid template '{template}'")
        sys.exit(1)
        
    if template == selected.get("best_fit_template"):
        final_fallback = selected.get("fallback_template")
    else:
        fallbacks = TEMPLATE_FALLBACKS.get(template, [])
        final_fallback = fallbacks[0] if fallbacks else None

    print(f"Approving: {selected['topic']}")
    print(f"Template:  {template}")
    
    jm.mark_step_completed("phase1_discovery", {
        "selected_topic": selected["topic"],
        "selected_template": template,
        "fallback_template": final_fallback,
    })
    _record_decision(jm, selected, "selected", template)
    # Lock the real template into auto-mode JobManager so runner.py sees it
    jm.set_template(template)
    
    print("Running extraction...")
    try:
        await run_extraction(job_manager=jm, topic=selected["topic"])
        print("\n[SUCCESS] Extraction completed.")
        ArchiveManager().mark_produced(selected["topic"], reason="CLI Approve Extract Success")
    except Exception as e:
        print(f"\n[ERROR] Extraction failed: {e}")
        
    await cmd_inspect(argparse.Namespace(job_id=jm.job_id, template=None))


async def cmd_reject(args: argparse.Namespace) -> None:
    """Reject one or more candidates."""
    jm = JobManager(template_name="auto", job_id=args.job_id)
    candidates = _load_candidates(jm)
    
    for idx_str in args.indices.split(","):
        idx = int(idx_str.strip()) - 1
        if 0 <= idx < len(candidates):
            c = candidates[idx]
            _record_decision(jm, c, "rejected")
            print(f"Rejected: {c.get('topic')}")


async def cmd_queue(args: argparse.Namespace) -> None:
    """Queue one or more candidates."""
    jm = JobManager(template_name="auto", job_id=args.job_id)
    candidates = _load_candidates(jm)
    
    for idx_str in args.indices.split(","):
        idx = int(idx_str.strip()) - 1
        if 0 <= idx < len(candidates):
            c = candidates[idx]
            _record_decision(jm, c, "queued")
            print(f"Queued: {c.get('topic')}")


async def cmd_extract(args: argparse.Namespace) -> None:
    """Run Phase 1B Extraction manually (direct topic + template)."""
    _print_header("PHASE 1: MANUAL EXTRACT")
    if args.template not in VALID_TEMPLATES:
        print(f"Invalid template {args.template}")
        sys.exit(1)
        
    jm = JobManager(template_name=args.template)
    jm.initialize()
    
    print(f"Job ID:   {jm.job_id}")
    print(f"Topic:    {args.topic}")
    print(f"Template: {args.template}")
    print("Extracting...")
    
    try:
        await run_extraction(job_manager=jm, topic=args.topic)
        print("\n[SUCCESS] Extraction completed.")
        ArchiveManager().mark_produced(args.topic, reason="CLI Manual Extract Success")
    except Exception as e:
        print(f"\n[ERROR] Extraction failed: {e}")

    await cmd_inspect(argparse.Namespace(job_id=jm.job_id, template=args.template))


async def cmd_inspect(args: argparse.Namespace) -> None:
    """Inspect output paths of a job."""
    template = args.template or "auto"
    jm = JobManager(template_name=template, job_id=args.job_id)
    
    print(f"\n--- Inspector: {jm.job_id} ---")
    print(f"Job Root: {jm.job_dir}")
    
    def check_print(name: str, path: Path):
        if path.exists():
            print(f"  [EXISTS] {name:<12} -> {path.relative_to(jm.job_dir.parent.parent)}")
        else:
            print(f"  [ MISS ] {name:<12} -> (not found)")

    if jm.is_auto_mode:
        check_print("Candidates", jm.discovery_dir / "candidates.json")
        check_print("Raw Cands", jm.discovery_dir / "raw_candidates.json")
        check_print("Decisions", jm.discovery_dir / "decisions.json")
        print("\n  Attempts:")
        if jm.attempts_dir.exists():
            for folder in jm.attempts_dir.iterdir():
                if folder.is_dir():
                    print(f"  - {folder.name}/")
                    for file in folder.iterdir():
                        print(f"      {file.name}")
        else:
            print("  (No attempts found)")
    else:
        print("\n  Attempts:")
        found_any = False
        if jm.data_dir.exists():
            for folder in jm.data_dir.iterdir():
                if folder.is_dir() and folder.name in ("best_fit", "fallback"):
                    found_any = True
                    print(f"  - {folder.name}/")
                    for file in folder.iterdir():
                        print(f"      {file.name}")
        if not found_any:
            print("  (No attempts found)")


async def cmd_queue_show(args: argparse.Namespace) -> None:
    """Show the current saved queue."""
    _print_header("SAVED QUEUE")
    archive = ArchiveManager()
    queue = archive.get_queue()
    if not queue:
        print("Queue is empty.")
        return
        
    for i, q in enumerate(queue, 1):
        print(f"[{i}] {q.topic}")
        print(f"    Template: {q.best_fit_template} (Fallback: {q.fallback_template or 'None'})")
        print(f"    Score:    {q.final_score}")
        print(f"    Reason:   {q.fit_reason}")
        print("-" * 60)


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AutoShorts Phase 1 Operator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # discover
    p_disc = subparsers.add_parser("discover", help="Run topic discovery only")
    p_disc.add_argument("--niche", help="Optional domain/niche to focus on")
    p_disc.add_argument("--top-n", type=int, default=5, help="Number of candidates to return")
    
    # auto
    p_auto = subparsers.add_parser("auto", help="Run full interactive operator flow")
    p_auto.add_argument("--niche", help="Optional domain/niche to focus on")
    p_auto.add_argument("--top-n", type=int, default=5, help="Number of candidates to return")
    
    # approve
    p_appr = subparsers.add_parser("approve", help="Approve and extract a candidate from a previous discovery job")
    p_appr.add_argument("--job-id", required=True, help="Job ID of the discovery run")
    p_appr.add_argument("--index", type=int, required=True, help="Index of the candidate to approve (1-based)")
    p_appr.add_argument("--template", help="Optional explicit template override")
    
    # reject
    p_rej = subparsers.add_parser("reject", help="Reject one or more candidates")
    p_rej.add_argument("--job-id", required=True)
    p_rej.add_argument("--indices", required=True, help="Comma-separated 1-based indices")
    
    # queue
    p_que = subparsers.add_parser("queue", help="Queue one or more candidates")
    p_que.add_argument("--job-id", required=True)
    p_que.add_argument("--indices", required=True, help="Comma-separated 1-based indices")
    
    # extract
    p_ext = subparsers.add_parser("extract", help="Run manual extraction directly")
    p_ext.add_argument("--topic", required=True, help="The exact topic to extract")
    p_ext.add_argument("--template", required=True, help="The exact template to target")
    
    # inspect
    p_insp = subparsers.add_parser("inspect", help="Inspect output paths of a job")
    p_insp.add_argument("--job-id", required=True)
    p_insp.add_argument("--template", help="Specify template if manual mode, omit if auto mode")
    
    # queue-show
    subparsers.add_parser("queue-show", help="Show saved topic queue")

    args = parser.parse_args()
    
    # Route to handlers
    handlers = {
        "discover": cmd_discover,
        "auto": cmd_auto,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "queue": cmd_queue,
        "extract": cmd_extract,
        "inspect": cmd_inspect,
        "queue-show": cmd_queue_show,
    }
    
    coro = handlers[args.command](args)
    
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(1)

if __name__ == "__main__":
    main()
