"""
AutoShorts — Cost Report Tool
==============================
Reads all jobs/*/logs/cost.jsonl files and prints a historical
usage + cost dashboard across every run.

Usage:
    python tools/cost_report.py              # all jobs
    python tools/cost_report.py --job auto_1 # single job
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_ROOT = PROJECT_ROOT / "jobs"

# Pricing reference (USD per 1M tokens) — verify at: ai.google.dev/pricing
_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro":   {"input": 1.25,  "output": 10.00},
}
_FALLBACK_PRICING = {"input": 0.075, "output": 0.30}


def _calc_cost(model: str, prompt: int, output: int) -> float:
    p = _PRICING.get(model, _FALLBACK_PRICING)
    return (prompt * p["input"] + output * p["output"]) / 1_000_000


def _load_all_records(job_filter: str | None) -> list[dict]:
    records = []
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
                # Re-calculate cost if missing (old records pre-dashboard)
                if "cost_usd" not in rec and "prompt_tokens" in rec:
                    rec["cost_usd"] = _calc_cost(
                        rec.get("model", "gemini-2.5-flash"),
                        rec.get("prompt_tokens", 0),
                        rec.get("output_tokens", 0),
                    )
                records.append(rec)
        except Exception as e:
            print(f"  [WARN] Could not read {cost_file}: {e}", file=sys.stderr)
    return records


def _print_report(records: list[dict]) -> None:
    if not records:
        print("\nNo cost records found.")
        print("Records are written automatically after each Gemini API call.")
        print(f"Expected location: {JOBS_ROOT}/<job_id>/logs/cost.jsonl")
        return

    # Aggregate
    by_job: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "prompt": 0, "output": 0, "cost": 0.0, "phases": set()
    })
    by_phase: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "prompt": 0, "output": 0, "cost": 0.0
    })
    total_calls = total_prompt = total_output = 0
    total_cost = 0.0

    for r in records:
        job = r.get("job_id", "unknown")
        phase = r.get("phase", "unknown")
        prompt = r.get("prompt_tokens", 0)
        output = r.get("output_tokens", 0)
        cost = r.get("cost_usd", 0.0)

        by_job[job]["calls"] += 1
        by_job[job]["prompt"] += prompt
        by_job[job]["output"] += output
        by_job[job]["cost"] += cost
        by_job[job]["phases"].add(phase)

        by_phase[phase]["calls"] += 1
        by_phase[phase]["prompt"] += prompt
        by_phase[phase]["output"] += output
        by_phase[phase]["cost"] += cost

        total_calls += 1
        total_prompt += prompt
        total_output += output
        total_cost += cost

    W = 58
    print("\n" + "=" * W)
    print(" AUTOSHORTS — HISTORICAL GEMINI COST REPORT")
    print("=" * W)

    # Per-job table
    print(f"\n  {'Job':<22} {'Calls':>5}  {'Tokens':>9}  {'Cost (USD)':>12}")
    print("  " + "-" * 52)
    for job, v in sorted(by_job.items()):
        tok = v["prompt"] + v["output"]
        print(f"  {job:<22} {v['calls']:>5}  {tok:>9,}  ${v['cost']:>11.6f}")

    # Per-phase breakdown
    print(f"\n  {'Phase':<22} {'Calls':>5}  {'Tokens':>9}  {'Cost (USD)':>12}")
    print("  " + "-" * 52)
    for ph, v in sorted(by_phase.items()):
        tok = v["prompt"] + v["output"]
        print(f"  {ph:<22} {v['calls']:>5}  {tok:>9,}  ${v['cost']:>11.6f}")

    # Totals
    print("\n" + "-" * W)
    print(f"  Total API calls  : {total_calls:,}")
    print(f"  Total tokens     : {(total_prompt + total_output):,}")
    print(f"    Prompt         : {total_prompt:,}")
    print(f"    Output         : {total_output:,}")
    print(f"  Total cost (USD) : ${total_cost:.6f}")
    print(f"  Total cost (INR) : ~Rs {total_cost * 83.5:.4f}  (approx @ 83.5 Rs/USD)")
    print("\n  Pricing used (verify at ai.google.dev/pricing):")
    for model, p in _PRICING.items():
        print(f"    {model}: input=${p['input']}/1M  output=${p['output']}/1M")
    print("  Account balance / Google quota: check console.cloud.google.com")
    print("=" * W + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoShorts historical cost report")
    parser.add_argument("--job", help="Filter to a specific job ID (e.g. auto_1)")
    args = parser.parse_args()

    records = _load_all_records(args.job)
    _print_report(records)


if __name__ == "__main__":
    main()
