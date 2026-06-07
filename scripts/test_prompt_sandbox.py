#!/usr/bin/env python3
"""AutoShorts — Phase 2 Prompt Sandbox
=======================================
Fast, standalone harness to test the EXACT production scripting context through ONE model call
(default gemini-2.5-flash), with NO rewrite loop and NO doctor — so you can see and tune raw Flash
quality cheaply.

Tuning loop: edit the prompt files (.agent/context/personas/*.md) and the budgets
(.agent/context/template_timing_registry.yaml), then re-run — this reads them fresh every time.
Logic: get Flash to a "decent" script here, and Pro (the doctor) will give an outstanding one in
the main pipeline.

Examples:
  python scripts/test_prompt_sandbox.py --persona hyper_analyst
  python scripts/test_prompt_sandbox.py --template vs_card --persona witty_strategist --rows 3
  python scripts/test_prompt_sandbox.py --persona savage_roast_master --data my_topic.json --with-doctor
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Allow running from the repo root: `python scripts/test_prompt_sandbox.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Roman-Hinglish scripts use em-dashes etc.; keep them readable on a Windows cp1252 console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import aiohttp

from src.agents.core.config import APP_CONFIG, PhaseModel
from src.agents.core.models import TemplateDataset
from src.agents.phase2_scripting.timing import build_segment_plan
from src.agents.phase2_scripting.xml_parser import parse_monologue
from src.agents.phase2_scripting.contracts import ScriptParsingError
from src.agents.phase2_scripting.llm_writer import (
    _build_system_prompt,
    _build_user_prompt,
    _call_gemini,
    _get_failing_segments,
    _run_script_doctor,
    _ends_dangling,
    _order_segments,
)
from tests.phase2_scripting.dummy_phase1_outputs import get_dummy_dataset

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sandbox")


def _est_tokens(s: str) -> int:
    return len(s) // 4


def _load_dataset(args) -> TemplateDataset:
    if args.data:
        raw = json.loads(Path(args.data).read_text(encoding="utf-8"))
        return TemplateDataset.model_validate(raw)
    try:
        return get_dummy_dataset(num_rows=args.rows, template=args.template)
    except ValueError:
        raise SystemExit(
            f"No built-in dummy data for template '{args.template}'. "
            f"Use --data <file.json> (a TemplateDataset), or pick bar_chart / vs_card."
        )


def _print_segment_table(ordered_segments, plan) -> None:
    seg_map = {s.tag: s for s in ordered_segments}
    fail_tags = set()
    try:
        fail_tags = {s.tag for s, _ in _get_failing_segments(seg_map, plan)}
    except ScriptParsingError as e:
        print(f"  [STRUCTURE] {e}")

    print(f"  {'TAG':<10} {'chars':>6}  {'window':>9}  {'status':<6} flags")
    print("  " + "-" * 48)
    dangling = 0
    for spec in plan.segments:
        seg = seg_map.get(spec.tag)
        window = f"{spec.min_chars}-{spec.max_chars}"
        if seg is None:
            print(f"  {spec.tag:<10} {'--':>6}  {window:>9}  MISSING")
            continue
        flags = ""
        if _ends_dangling(seg.text):
            flags += "DANGLING"
            dangling += 1
        status = "PASS" if spec.tag not in fail_tags else "FAIL"
        print(f"  {seg.tag:<10} {seg.char_count:>6}  {window:>9}  {status:<6} {flags}")
    print("  " + "-" * 48)
    n = len(plan.segments)
    print(f"  in-budget: {n - len(fail_tags)}/{n}   dangling endings: {dangling}")


async def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 2 prompt sandbox (single-shot, no loop/doctor).")
    ap.add_argument("--template", default="bar_chart")
    ap.add_argument("--persona", default="hyper_analyst")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--thinking-budget", type=int, default=0)
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--data", help="Path to a TemplateDataset JSON (custom topic/data).")
    ap.add_argument("--with-doctor", action="store_true",
                    help="Also run the Pro doctor on the draft (to inspect/debug the polish).")
    args = ap.parse_args()

    dataset = _load_dataset(args)
    template = dataset.template_name if args.data else args.template
    plan = build_segment_plan("sandbox", template, args.persona, dataset)

    system_prompt = _build_system_prompt(args.persona)
    user_prompt = _build_user_prompt(dataset, plan)

    print("=" * 60)
    print(" PHASE 2 PROMPT SANDBOX")
    print("=" * 60)
    print(f"  template={template}  persona={args.persona}  model={args.model}")
    print(f"  thinking_budget={args.thinking_budget}  temp={args.temperature}  "
          f"rows={len(dataset.rows)}  segments={len(plan.segments)}")
    print(f"  system prompt: {len(system_prompt):,} chars (~{_est_tokens(system_prompt):,} tok)")
    print(f"  user prompt  : {len(user_prompt):,} chars (~{_est_tokens(user_prompt):,} tok)")
    print()

    draft_model = PhaseModel(
        model=args.model, temperature=args.temperature, thinking_budget=args.thinking_budget,
    )

    timeout = aiohttp.ClientTimeout(total=APP_CONFIG.api_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        raw = await _call_gemini(system_prompt, user_prompt, session, log, draft_model, "sandbox_draft")

        print("--- RAW MODEL OUTPUT (verbatim — watch for fences / 'Here is' yapping) ---")
        print(raw.strip())
        print()

        try:
            parsed = parse_monologue(raw, plan)
        except ScriptParsingError as e:
            print(f"[STRUCTURAL PARSE FAILURE] {e}")
            return

        print("--- SEGMENT CHECK (draft) ---")
        _print_segment_table(parsed, plan)

        if args.with_doctor:
            print("\n--- SCRIPT DOCTOR (Pro) ---")
            seg_map = {s.tag: s for s in parsed}
            polished, note = await _run_script_doctor(
                seg_map, plan, dataset, system_prompt, session, log
            )
            verdict = note.strip().splitlines()[-1] if note.strip() else "(none)"
            print(f"  verdict: {verdict}\n")
            ordered = _order_segments(polished, plan)
            for seg in ordered:
                print(f"  <{seg.tag}> {seg.text}")
            print()
            _print_segment_table(ordered, plan)


if __name__ == "__main__":
    asyncio.run(main())
