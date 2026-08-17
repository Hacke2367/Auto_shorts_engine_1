#!/usr/bin/env python3
"""AutoShorts Master CLI
=====================
Orchestrates Phase 2, Phase 3, Handoff, and Phase 4 Video Render
into structured run buckets while enforcing strict JSONL cost tracking.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

# Fix python path for local execution from root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Windows consoles default stdout/stderr to cp1252, which can't encode the
# emoji used in CLI status messages (✅/❌) — force UTF-8 so prints don't crash.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from src.cli.cli_utils import resolve_bucket, create_run_dir, get_cli_job_manager, setup_cli_logger
from src.agents.core.cost_tracker import record_cost, get_session_summary
from src.agents.phase2_scripting.runner import run_scripting
from src.agents.phase3_audio.runner import run_phase3
from src.agents.phase3_audio.contracts import AudioSynthesisSettings
from src.agents.final_handoff.handoff import run_handoff
from src.agents.core.config import APP_CONFIG


def get_bucket_name(template_name: str) -> str:
    from src.cli.cli_utils import resolve_bucket
    return resolve_bucket(template_name)


def log_cost(run_dir: Path, phase: str, step: str, status: str, notes: str = ""):
    """Helper to consistently format and record cost events."""
    record = {
        "timestamp": time.time(),
        "phase": phase,
        "step": step,
        "provider": "unknown",  # Extensible for LLM usage stats
        "model": "unknown",
        "status": status,
        "notes": notes,
    }
    record_cost(run_dir, record)


def cmd_new(args):
    """Create a new job run folder for a given template."""
    bucket = get_bucket_name(args.template)
    run_dir = create_run_dir(bucket, template_name=args.template)
    print(f"✅ Created new job bucket: {run_dir.resolve()}")
    print(f"To run phase 2, ensure dataset is located at '{run_dir.resolve()}/data/{args.template}_dataset.json'")
    print(f"and '{run_dir.resolve()}/data/data_manifest.json' exists (or just run phase1-extract).")
    print(f"Then execute: python -m src.cli.autoshorts run --job {run_dir} --template {args.template} --persona savage_roast_master")


async def async_phase1_discover(args):
    """Execute Phase 1 Discovery using auto runner."""
    from src.agents.core.job_manager import JobManager
    from src.agents.phase1_discovery.discovery_runner import run_discovery
    import aiohttp
    import shutil

    jm = JobManager(template_name="auto")
    jm.initialize()
    out_dir = jm.discovery_dir
    logger = setup_cli_logger(out_dir)
    
    log_cost(out_dir, "phase1", "discovery", "start")
    
    try:
        timeout = aiohttp.ClientTimeout(total=APP_CONFIG.api_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await run_discovery(session, logger, out_dir, niche_hint=args.template)
            
        cands_file = out_dir / "raw_candidates.json"
        
        if getattr(args, "job", None) and cands_file.exists():
            run_dir = Path(args.job).resolve()
            run_disc_dir = run_dir / "discovery"
            run_disc_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cands_file, run_disc_dir / "raw_candidates.json")
            logger.info(f"Copied raw_candidates.json to {run_disc_dir}")
            print(f"✅ Copied Phase 1 candidates to {run_disc_dir}")
        else:
            print(f"✅ Phase 1 Discovery complete. Candidates saved to {cands_file}")
            
        log_cost(out_dir, "phase1", "discovery", "success")
    except Exception as e:
        log_cost(out_dir, "phase1", "discovery", "fail", str(e))
        logger.error(f"❌ Phase 1 Discovery Failed: {e}")
        raise


def cmd_phase1_discover(args):
    try:
        asyncio.run(async_phase1_discover(args))
    except Exception:
        sys.exit(1)


def cmd_phase1_approve(args):
    """Approve a discovery candidate by index so extract doesn't need --topic."""
    import json
    
    run_dir = Path(args.job).resolve()
    logger = setup_cli_logger(run_dir)
    
    cands_file = run_dir / "discovery" / "raw_candidates.json"
    if not cands_file.exists():
        logger.error(f"❌ Cannot approve: No raw_candidates.json in {cands_file.parent}")
        sys.exit(1)
        
    try:
        with open(cands_file, "r", encoding="utf-8") as f:
            cands = json.load(f)
            
        topics = cands.get("candidates", [])
        if args.index < 0 or args.index >= len(topics):
            logger.error(f"❌ Index {args.index} out of bounds (0 to {len(topics)-1})")
            sys.exit(1)
            
        approved_out = {
            "topic": topics[args.index].get("topic"),
            "template_name": args.template
        }
        
        approved_file = run_dir / "discovery" / "approved.json"
        
        with open(approved_file, "w", encoding="utf-8") as f:
            json.dump(approved_out, f, indent=2)
            
        logger.info(f"✅ Approved topic [{args.index}]: {approved_out['topic']}")
        print(f"✅ Approved topic saved to {approved_file}")
    except Exception as e:
        logger.error(f"❌ Approval failed: {e}")
        sys.exit(1)



async def async_phase1_extract(args):
    """Execute Phase 1 Extraction using auto runner."""
    from src.agents.core.job_manager import JobManager
    from src.agents.phase1_extraction.runner import run_extraction
    import shutil
    import json
    
    run_dir = Path(args.job).resolve()
    logger = setup_cli_logger(run_dir)
    log_cost(run_dir, "phase1", "extraction", "start")
    
    try:
        jm = JobManager(template_name="auto")
        jm.initialize()

        topic = getattr(args, "topic", None)
        if not topic:
            # Fallback to checking for approved.json
            approved_file = run_dir / "discovery" / "approved.json"
            if approved_file.exists():
                logger.info(f"No --topic supplied. Reading from {approved_file}")
                with open(approved_file, "r", encoding="utf-8") as f:
                    appr = json.load(f)
                    topic = appr.get("topic")

        if not topic:
            logger.error("❌ No --topic provided and no discovery/approved.json found.")
            raise ValueError("No --topic provided and no discovery/approved.json found.")

        # run_extraction()'s auto-mode branch reads the target template from
        # phase1_discovery step metadata (selected_template), NOT from
        # set_template() alone — set_template() only updates state["template"],
        # a different field. Mirrors the working pattern in src/cli/phase1.py's
        # cmd_auto/cmd_approve (mark_step_completed BEFORE set_template).
        jm.mark_step_completed("phase1_discovery", {
            "selected_topic": topic,
            "selected_template": args.template,
            "fallback_template": None,
        })
        jm.set_template(args.template)

        logger.info(f"Extracting topic: {topic}")
        await run_extraction(jm, topic=topic)
        
        # Locate extraction directories
        attempt_dirs = sorted(jm.attempts_dir.glob(f"*_{args.template}"))
        if not attempt_dirs:
            raise RuntimeError("Extraction finished but no artifact directory found.")
        best_dir = attempt_dirs[-1]
        
        data_dir = run_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        manifest = {
            "template_name": args.template,
            "csv_relpath": "",
            "dataset_relpath": "",
            "audit_relpath": ""
        }
        
        missing = []
        for fname, key in [
            (f"{args.template}_data.csv", "csv_relpath"),
            (f"{args.template}_dataset.json", "dataset_relpath"),
            ("sources_audit.json", "audit_relpath")
        ]:
            src = best_dir / fname
            if src.exists():
                shutil.copy2(src, data_dir / fname)
                manifest[key] = f"data/{fname}"
            else:
                missing.append(fname)
                
        if missing:
            raise FileNotFoundError(f"Missing required artifacts after extraction: {missing}")
                
        with open(data_dir / "data_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            
        log_cost(run_dir, "phase1", "extraction", "success")
        logger.info(f"✅ Phase 1 Extraction Complete. Manifest written to {data_dir / 'data_manifest.json'}")
        print(f"✅ Extracted dataset successfully deployed to {data_dir}")
    except Exception as e:
        log_cost(run_dir, "phase1", "extraction", "fail", str(e))
        logger.error(f"❌ Phase 1 Extraction Failed: {e}")
        raise


def cmd_phase1_extract(args):
    try:
        asyncio.run(async_phase1_extract(args))
    except Exception:
        sys.exit(1)


async def async_phase2(args):
    """Execute Phase 2 Script Generation."""
    run_dir = Path(args.job).resolve()
    logger = setup_cli_logger(run_dir)
    log_cost(run_dir, "phase2", "script_generation", "start")

    script_file = run_dir / "script" / "script.json"
    if getattr(args, "force", False) and script_file.exists():
        logger.info(f"Forcing Phase 2: Removed cached script.json")
        script_file.unlink()
        
    try:
        import json
        man_path = run_dir / "data" / "data_manifest.json"
        tpl = "auto"
        if man_path.exists():
            with open(man_path, "r") as f:
                tpl = json.load(f).get("template_name", "auto")
                
        jm = get_cli_job_manager(run_dir, template_name=tpl)
        await run_scripting(jm, persona_id=args.persona)
        log_cost(run_dir, "phase2", "script_generation", "success")
        logger.info("✅ Phase 2 Completed Successfully")
        print(get_session_summary(configured_rpm=APP_CONFIG.llm.rpm_limit))
    except Exception as e:
        log_cost(run_dir, "phase2", "script_generation", "fail", str(e))
        logger.error(f"❌ Phase 2 Failed: {e}")
        raise


def cmd_phase2(args):
    try:
        asyncio.run(async_phase2(args))
    except Exception:
        sys.exit(1)


async def async_phase3(args):
    """Execute Phase 3 Audio Synthesis."""
    run_dir = Path(args.job).resolve()
    logger = setup_cli_logger(run_dir)
    log_cost(run_dir, "phase3", "audio_synthesis", "start")
    
    if args.offline:
        os.environ["PHASE3_OFFLINE"] = "1"
        logger.info("Phase 3 OFFLINE mode activated")
        
    if args.skip_underrun:
        os.environ["PHASE3_SKIP_UNDERRUN"] = "1"
        logger.info("Phase 3 UNDERRUN bypass activated")
        
        
    if not args.offline and (not args.voice_id or not args.model_id):
        logger.error("❌ Phase 3 (online) requires --voice-id and --model-id.")
        log_cost(run_dir, "phase3", "audio_synthesis", "fail", "missing_tts_config")
        raise ValueError("Missing TTS Config")
        
    v_id = "OFFLINE" if args.offline else args.voice_id
    m_id = "OFFLINE" if args.offline else args.model_id
        
    # Extensible TTS Settings.
    # Voice delivery params come from config.py (APP_CONFIG.tts) — previously they
    # were omitted entirely, so ElevenLabs used the voice's saved defaults and the
    # delivery was uncontrolled (flat/slow with long pauses). Offline mode leaves
    # them None so the synthetic tone wrapper is unaffected.
    _tts = APP_CONFIG.tts
    tts_settings = AudioSynthesisSettings(
        provider="elevenlabs",
        voice_id=v_id,
        model_id=m_id,
        output_format=args.output_format,
        concurrency_limit=args.concurrency,
        stability=None if args.offline else _tts.stability,
        similarity_boost=None if args.offline else _tts.similarity_boost,
        style=None if args.offline else _tts.style,
        speaker_boost=None if args.offline else _tts.speaker_boost,
        speed=None if args.offline else _tts.speed,
    )
    
    try:
        await run_phase3(run_dir, tts_settings)
        log_cost(run_dir, "phase3", "audio_synthesis", "success")
        logger.info("✅ Phase 3 Completed Successfully")
    except Exception as e:
        log_cost(run_dir, "phase3", "audio_synthesis", "fail", str(e))
        logger.error(f"❌ Phase 3 Failed: {e}")
        raise


def cmd_phase3(args):
    try:
        asyncio.run(async_phase3(args))
    except Exception:
        sys.exit(1)


async def async_repair(args):
    """Repair loop: run Phase3 -> catch UnderRunError -> force Phase2 -> retry."""
    from src.agents.phase3_audio.contracts import UnderRunError
    import json
    
    run_dir = Path(args.job).resolve()
    logger = setup_cli_logger(run_dir)
    
    # 1. Ensure dataset exists via manifest
    manifest_file = run_dir / "data" / "data_manifest.json"
    if not manifest_file.exists():
        logger.error(f"❌ Missing dataset manifest in {manifest_file.parent}. Extraction must run first.")
        raise FileNotFoundError("Missing manifest")
        
    try:
        with open(manifest_file, "r") as f:
            man = json.load(f)
        if not (run_dir / man.get("dataset_relpath", "")).exists():
             raise FileNotFoundError
    except Exception:
        logger.error("❌ Dataset missing or manifest invalid. Run phase1-extract first.")
        raise ValueError("Invalid dataset state")
    
    max_tries = args.max_tries
    current_try = 1
    
    while current_try <= max_tries:
        logger.info(f"=== Repair Loop Attempt {current_try}/{max_tries} ===")
        
        try:
            # 2. Run Phase 2
            await async_phase2(args)
                
            # 3. Run Phase 3
            await async_phase3(args)
            
            logger.info("✅ Phase 3 succeeded in Repair Loop without UnderRun!")
            return
            
        except UnderRunError as e:
            logger.warning(f"⚠️ UnderRun detected on try {current_try}: {e}")
            if current_try >= max_tries:
                logger.error(f"❌ Repair Loop Exhausted Max Retries ({max_tries}).")
                logger.error(f"Failing Tags Info: {e}")
                raise RuntimeError("Max retries hit for UnderRunError")
                
            logger.info(f"⚠️ Forcing Phase 2 rewrite to fix Underrun (Try {current_try + 1})...")
            args.force = True
            current_try += 1


def cmd_repair(args):
    try:
        asyncio.run(async_repair(args))
    except Exception:
        sys.exit(1)


def sync_handoff(args):
    """Execute Final Bridge."""
    run_dir = Path(args.job).resolve()
    logger = setup_cli_logger(run_dir)
    log_cost(run_dir, "handoff", "payload_assembly", "start")
    
    func = None
    try:
        from src.agents.final_handoff.handoff import run_handoff
        func = run_handoff
    except ImportError:
        try:
            from src.agents.phase4_engine.handoff import build_engine_payload
            func = build_engine_payload
        except ImportError:
            try:
                from src.agents.final_handoff.handoff import build_engine_handoff
                func = build_engine_handoff
            except ImportError:
                pass
            
    if not func:
        logger.error("❌ Could not resolve handoff entrypoint (tried run_handoff, build_engine_payload, build_engine_handoff).")
        log_cost(run_dir, "handoff", "payload_assembly", "fail", "missing_entrypoint")
        raise ImportError("Missing handoff entrypoint")
    
    try:
        written = func(run_dir)
        log_cost(run_dir, "handoff", "payload_assembly", "success")
        logger.info("✅ Final Handoff Completed Successfully")
        for key, path in written.items():
            logger.info(f"  → {key}: {path}")
    except Exception as e:
        log_cost(run_dir, "handoff", "payload_assembly", "fail", str(e))
        logger.error(f"❌ Handoff Failed: {e}")
        raise


def cmd_handoff(args):
    try:
        sync_handoff(args)
    except Exception:
        sys.exit(1)


def sync_render(args):
    """Execute Phase 4 Video Render (main.py)."""
    run_dir = Path(args.job).resolve()
    logger = setup_cli_logger(run_dir)
    log_cost(run_dir, "phase4", "video_engine", "start")
    
    # Use the SAME interpreter that is running this CLI (sys.executable), NOT a
    # bare "python" — under an activated .venv on Windows, bare "python" can still
    # resolve to the global interpreter (which lacks manim), silently bypassing the
    # venv. main.py then inherits that wrong interpreter via its own sys.executable.
    cmd = [
        sys.executable, "main.py",
        "--job", str(run_dir),
        "-q", args.quality
    ]
    if getattr(args, "template", None):
        cmd.extend(["--template", args.template])
        
    logger.info(f"Invoking Video Engine: {' '.join(cmd)}")
    
    try:
        # autoshorts.py lives at src/cli/, so the project root (where main.py is)
        # is parents[2] — NOT parents[3], which resolves to the drive root (C:\).
        proc = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parents[2]))
        if proc.returncode != 0:
            raise RuntimeError(f"Engine crashed with code {proc.returncode}")
            
        log_cost(run_dir, "phase4", "video_engine", "success")
        logger.info("✅ Video Render Completed Successfully")
    except Exception as e:
        log_cost(run_dir, "phase4", "video_engine", "fail", str(e))
        logger.error(f"❌ Render Failed: {e}")
        raise


def cmd_render(args):
    try:
        sync_render(args)
    except Exception:
        sys.exit(1)


def cmd_run(args):
    """Sequentially execute Phase 2 -> Phase 3 -> Handoff -> Render."""
    run_dir = Path(args.job).resolve()
    manifest_file = run_dir / "data" / "data_manifest.json"
    
    try:
        if not manifest_file.exists():
            print("❌ Dataset manifest not found. Please run phase1-extract first.", file=sys.stderr)
            raise FileNotFoundError("Missing data_manifest.json")
            
        asyncio.run(async_phase2(args))
        asyncio.run(async_phase3(args))
        sync_handoff(args)
        sync_render(args)
        print("✅ Full Pipeline Completed Successfully")
    except Exception as e:
        print(f"❌ Pipeline Failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AutoShorts Master Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # NEW
    p_new = subparsers.add_parser("new", help="Create a brand new job environment.")
    p_new.add_argument("--template", required=True, help="Base template (e.g. vs_card)")
    p_new.set_defaults(func=cmd_new)

    # PHASE 1 (Discover)
    p_p1d = subparsers.add_parser("phase1-discover", help="Discover topic candidates.")
    p_p1d.add_argument("--template", required=True, help="Base template (niche hint).")
    p_p1d.add_argument("--job", help="Optional job run dir to copy raw_candidates.json into.")
    p_p1d.set_defaults(func=cmd_phase1_discover)

    # PHASE 1 (Approve)
    p_p1a = subparsers.add_parser("phase1-approve", help="Approve a topic by index.")
    p_p1a.add_argument("--job", required=True, help="Job run directory.")
    p_p1a.add_argument("--index", type=int, required=True, help="Candidate array index from raw_candidates.json.")
    p_p1a.add_argument("--template", required=True, help="Template matching the bucket map.")
    p_p1a.set_defaults(func=cmd_phase1_approve)

    # PHASE 1 (Extract)
    p_p1e = subparsers.add_parser("phase1-extract", help="Extract given topic to dataset.")
    p_p1e.add_argument("--job", required=True, help="Job run directory.")
    p_p1e.add_argument("--template", required=True, help="Template to extract for.")
    p_p1e.add_argument("--topic", help="Topic string to search & extract. (Optional if approved.json exists)")
    p_p1e.set_defaults(func=cmd_phase1_extract)

    # PHASE 2
    p_p2 = subparsers.add_parser("phase2", help="Run Phase 2 Screenplay Agent.")
    p_p2.add_argument("--job", required=True, help="Absolute or relative path to job directory.")
    p_p2.add_argument("--persona", required=True, help="Persona file ID (e.g. savage_roast_master)")
    p_p2.add_argument("--force", action="store_true", help="Invalidate script cache and force regeneration.")
    p_p2.set_defaults(func=cmd_phase2)

    # REPAIR LOOP
    p_rep = subparsers.add_parser("repair", help="Auto-repair Phase 3 under-runs via Phase 2 retries.")
    p_rep.add_argument("--job", required=True, help="Job run directory.")
    p_rep.add_argument("--persona", required=True, help="Persona file ID for script regeneration.")
    p_rep.add_argument("--template", required=True, help="Template context.")
    p_rep.add_argument("--max-tries", type=int, default=2, help="Max script rewrite attempts.")
    p_rep.add_argument("--offline", action="store_true", help="Synthesize dummy local audio.")
    p_rep.add_argument("--skip-underrun", action="store_true", help="Bypass Underrun limits.")
    p_rep.set_defaults(func=cmd_repair)

    # PHASE 3
    p_p3 = subparsers.add_parser("phase3", help="Run Phase 3 Audio Synthesis Engine.")
    p_p3.add_argument("--job", required=True, help="Absolute or relative path to job directory.")
    p_p3.add_argument("--voice-id", help="TTS Voice ID.")
    p_p3.add_argument("--model-id", help="TTS Model ID.")
    p_p3.add_argument("--output-format", default="mp3_44100_128", help="TTS Output format.")
    p_p3.add_argument("--concurrency", type=int, default=3, help="TTS Concurrent requests limit.")
    p_p3.add_argument("--offline", action="store_true", help="Synthesize dummy local audio instead of HTTP external TTS.")
    p_p3.add_argument("--skip-underrun", action="store_true", help="Log but bypass absolute visual time bounds protections.")
    p_p3.set_defaults(func=cmd_phase3)

    # HANDOFF
    p_ho = subparsers.add_parser("handoff", help="Execute Phase 3 → Phase 4 Adapter.")
    p_ho.add_argument("--job", required=True, help="Absolute or relative path to job directory.")
    p_ho.set_defaults(func=cmd_handoff)

    # RENDER (Phase 4)
    p_render = subparsers.add_parser("render", help="Execute Phase 4 Video Render.")
    p_render.add_argument("--job", required=True, help="Absolute or relative path to job directory.")
    p_render.add_argument("--template", help="Template to render (optional, overrrides job.json id).")
    p_render.add_argument("-q", "--quality", default="h", choices=["l", "m", "h", "p", "k"], help="Manim render quality format (default: h).")
    p_render.set_defaults(func=cmd_render)

    # FULL RUN
    p_run = subparsers.add_parser("run", help="Run Pipeline (Phase 1 -> 4).")
    p_run.add_argument("--job", required=True, help="Path to job directory.")
    p_run.add_argument("--template", required=True, help="Base template (e.g. vs_card)")
    p_run.add_argument("--persona", required=True, help="Persona file ID.")
    p_run.add_argument("--topic", help="Topic to extract (if dataset missing).")
    p_run.add_argument("--offline", action="store_true", help="Run Phase 3 offline.")
    p_run.add_argument("--skip-underrun", action="store_true", help="Skip Phase 3 bounds.")
    p_run.add_argument("--voice-id", default=APP_CONFIG.tts.voice_id or None,
                       help="TTS Voice ID (default: config.py APP_CONFIG.tts.voice_id).")
    p_run.add_argument("--model-id", default=APP_CONFIG.tts.model_id or None,
                       help="TTS Model ID (default: config.py APP_CONFIG.tts.model_id).")
    p_run.add_argument("--output-format", default=APP_CONFIG.tts.output_format,
                       help="TTS Output format (default: config.py APP_CONFIG.tts.output_format).")
    p_run.add_argument("--concurrency", type=int, default=APP_CONFIG.tts.concurrency_limit,
                       help="TTS Concurrent requests limit (default: config.py APP_CONFIG.tts.concurrency_limit).")
    p_run.add_argument("-q", "--quality", default="h", help="Manim render quality format (default: h).")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
