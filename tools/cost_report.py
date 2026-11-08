"""
AutoShorts — Cost Report Tool
==============================
Reads all jobs/*/logs/cost.jsonl files and prints a historical
usage + cost dashboard across every run.

Usage:
    python tools/cost_report.py              # all jobs
    python tools/cost_report.py --job auto_1 # single job

Pricing is NOT duplicated here — it is imported from
``src.agents.core.cost_tracker`` so the live pipeline and this report can never
drift apart. (They previously disagreed by 4x on Flash input pricing.)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_ROOT = PROJECT_ROOT / "jobs"

sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.core.cost_tracker import _PRICING, _cost_usd  # noqa: E402


def _normalize(rec: dict) -> dict | None:
    """Map any historical cost.jsonl record shape onto the current one.

    Returns ``None`` for records that are not API calls at all — ``log_cost()``
    in ``src/cli/autoshorts.py`` writes phase/step markers into the same file
    with no token fields, and counting those as calls inflated every total.

    Handled shapes:
      * current   -> input_tokens / cached_input_tokens / output_tokens / reasoning_tokens
      * legacy    -> prompt_tokens / output_tokens / thinking_tokens
      * markers   -> no token fields at all (skipped)
    """
    has_new = "input_tokens" in rec
    has_old = "prompt_tokens" in rec
    if not (has_new or has_old):
        return None

    if has_new:
        input_tokens = rec.get("input_tokens", 0)
        cached_input = rec.get("cached_input_tokens", 0)
        # Already-billed output — reasoning is a breakdown of it, not an addition.
        output_tokens = rec.get("output_tokens", 0)
        reasoning = rec.get("reasoning_tokens", 0)
    else:
        # Legacy Gemini records stored thinking SEPARATELY from output, and
        # Gemini bills thoughts at the output rate, so fold them in here.
        input_tokens = rec.get("prompt_tokens", 0)
        cached_input = 0
        reasoning = rec.get("thinking_tokens", 0)
        output_tokens = rec.get("output_tokens", 0) + reasoning

    model = rec.get("model") or "unknown"
    provider = rec.get("provider") or ("gemini" if model.startswith("gemini") else "unknown")

    cost = rec.get("cost_usd")
    if cost is None:
        cost = _cost_usd(model, input_tokens, output_tokens, cached_input)

    return {
        "job_id": rec.get("job_id", "unknown"),
        "phase": rec.get("phase", "unknown"),
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "cost_usd": cost,
    }


def _load_all_records(job_filter: str | None) -> tuple[list[dict], int]:
    """Return (api_call_records, skipped_marker_count)."""
    records: list[dict] = []
    skipped = 0
    pattern = f"**/{job_filter}/logs/cost.jsonl" if job_filter else "**/logs/cost.jsonl"
    for cost_file in sorted(JOBS_ROOT.glob(pattern)):
        job_dir = cost_file.parent.parent
        job_id = job_dir.name
        try:
            for line in cost_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rec.setdefault("job_id", job_id)
                norm = _normalize(rec)
                if norm is None:
                    skipped += 1
                    continue
                records.append(norm)
        except Exception as e:
            print(f"  [WARN] Could not read {cost_file}: {e}", file=sys.stderr)
    return records, skipped


def _print_report(records: list[dict], skipped: int) -> None:
    if not records:
        print("\nNo LLM cost records found.")
        if skipped:
            print(f"({skipped} pipeline step markers found, but none carry token counts.)")
        print("Records are written automatically after each LLM API call.")
        print(f"Expected location: {JOBS_ROOT}/<job_id>/logs/cost.jsonl")
        return

    by_job: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "input": 0, "output": 0, "cost": 0.0, "phases": set()
    })
    by_phase: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "input": 0, "output": 0, "cost": 0.0
    })
    total_calls = total_input = total_output = total_cached = total_reasoning = 0
    total_cost = 0.0
    models_seen: set[str] = set()

    for r in records:
        job, phase = r["job_id"], r["phase"]
        inp, out, cost = r["input_tokens"], r["output_tokens"], r["cost_usd"]

        by_job[job]["calls"] += 1
        by_job[job]["input"] += inp
        by_job[job]["output"] += out
        by_job[job]["cost"] += cost
        by_job[job]["phases"].add(phase)

        by_phase[phase]["calls"] += 1
        by_phase[phase]["input"] += inp
        by_phase[phase]["output"] += out
        by_phase[phase]["cost"] += cost

        total_calls += 1
        total_input += inp
        total_output += out
        total_cached += r["cached_input_tokens"]
        total_reasoning += r["reasoning_tokens"]
        total_cost += cost
        models_seen.add(f"{r['provider']}:{r['model']}")

    W = 58
    print("\n" + "=" * W)
    print(" AUTOSHORTS — HISTORICAL LLM COST REPORT")
    print("=" * W)

    print(f"\n  {'Job':<22} {'Calls':>5}  {'Tokens':>9}  {'Cost (USD)':>12}")
    print("  " + "-" * 52)
    for job, v in sorted(by_job.items()):
        tok = v["input"] + v["output"]
        print(f"  {job:<22} {v['calls']:>5}  {tok:>9,}  ${v['cost']:>11.6f}")

    print(f"\n  {'Phase':<22} {'Calls':>5}  {'Tokens':>9}  {'Cost (USD)':>12}")
    print("  " + "-" * 52)
    for ph, v in sorted(by_phase.items()):
        tok = v["input"] + v["output"]
        print(f"  {ph:<22} {v['calls']:>5}  {tok:>9,}  ${v['cost']:>11.6f}")

    print("\n" + "-" * W)
    print(f"  Total API calls  : {total_calls:,}")
    if skipped:
        print(f"  Step markers     : {skipped:,}  (no tokens — excluded from totals)")
    print(f"  Total tokens     : {(total_input + total_output):,}")
    print(f"    Input          : {total_input:,}")
    if total_cached:
        pct = 100.0 * total_cached / max(1, total_input)
        print(f"      cached       : {total_cached:,} ({pct:.0f}%)")
    print(f"    Output         : {total_output:,}")
    if total_reasoning:
        print(f"      reasoning    : {total_reasoning:,}  (billed at output rate)")
    print(f"  Total cost (USD) : ${total_cost:.6f}")
    print(f"  Total cost (INR) : ~Rs {total_cost * 83.5:.4f}  (approx @ 83.5 Rs/USD)")

    print(f"\n  Models seen      : {', '.join(sorted(models_seen))}")
    print("\n  Pricing used (per 1M tokens, from core/cost_tracker.py):")
    for model in sorted(models_seen):
        name = model.split(":", 1)[-1]
        p = _PRICING.get(name)
        if p:
            print(
                f"    {name}: input=${p['input']}  cached=${p['cached_input']}  "
                f"output=${p['output']}"
            )
        else:
            print(f"    {name}: NO PRICING ENTRY — costs above are an over-estimate")
    print("=" * W + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoShorts historical cost report")
    parser.add_argument("--job", help="Filter to a specific job ID (e.g. auto_1)")
    args = parser.parse_args()

    records, skipped = _load_all_records(args.job)
    _print_report(records, skipped)


if __name__ == "__main__":
    main()
