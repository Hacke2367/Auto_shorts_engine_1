"""
AutoShorts — validation report reader
=====================================
Turns the JSON dropped by ``scripts/replay_harness.py`` into the two tables the
validation actually needs to answer:

1. **Right-sizing.** For each route, at each reasoning effort: quality, reasoning
   tokens spent, and cost. The verdict column is the whole point —

   * ``waste``  — a higher effort produced a BYTE-IDENTICAL output (same hash)
     while burning more reasoning tokens. That is a big model doing a small job.
   * ``knee``   — the cheapest effort that reaches the route's best quality.
     This is the one to ship.
   * ``under``  — quality below the best seen; the task needs more than this.
   * ``unstable`` — two reps at the same effort disagreed, so a single number
     would be misleading.

2. **Spend.** Cached input is broken out separately, because prompt-cache hits
   can make a repeated sweep look cheaper than the first real run would be.

Usage:
    python scripts/compare_report.py
    python scripts/compare_report.py --dir validation
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = PROJECT_ROOT / "validation"


def _load(report_dir: Path) -> list[dict]:
    if not report_dir.exists():
        raise SystemExit(f"No reports in {report_dir}. Run scripts/replay_harness.py first.")
    out = []
    for path in sorted(report_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_file"] = path.name
            out.append(data)
        except Exception as exc:
            print(f"  [WARN] skipping {path.name}: {exc}")
    return out


def _verdict_rows(cells: list[dict]) -> list[dict]:
    """Collapse reps into one row per effort and assign a verdict."""
    by_effort: dict[str, list[dict]] = defaultdict(list)
    for c in cells:
        by_effort[c.get("effort") or "default"].append(c)

    rows = []
    for effort, reps in by_effort.items():
        hashes = {r.get("output_hash") for r in reps}
        scores = [r.get("score", 0.0) for r in reps]
        # "Stable" means the QUALITY held up across reps, not that the wording was
        # identical. A generative route produces different text every time; judging
        # stability on the text hash would mark every cell unstable and hide the
        # real signal. Identical text is tracked separately below as the strongest
        # possible waste evidence.
        rows.append({
            "effort": effort,
            "score": round(sum(scores) / len(scores), 2),
            "spread": round(max(scores) - min(scores), 2),
            "stable": (max(scores) - min(scores)) <= 2.0,
            "hash": next(iter(hashes)) if len(hashes) == 1 else "varies",
            "reasoning": round(sum(r["spend"]["reasoning_tokens"] for r in reps) / len(reps)),
            "cached_in": round(sum(r["spend"]["cached_input_tokens"] for r in reps) / len(reps)),
            "cost": sum(r["spend"]["cost_usd"] for r in reps) / len(reps),
        })

    # Cheapest first — reasoning tokens are the honest proxy for "how hard it worked".
    rows.sort(key=lambda r: r["reasoning"])

    best = max((r["score"] for r in rows), default=0.0)
    # Scores this close are rep-to-rep noise, not a real quality difference.
    NOISE = 2.0
    knee_taken = False
    for row in rows:
        if not row["stable"]:
            row["verdict"] = f"noisy (spread {row['spread']})"
        elif row["score"] < best - NOISE:
            row["verdict"] = "under"
        elif not knee_taken:
            row["verdict"] = "knee  <-- cheapest at top quality"
            knee_taken = True
        else:
            # Only claim "identical output" when there really is one hash to
            # compare. Two cells that both vary internally are both "varies", and
            # treating that as a match would assert something plainly false.
            same_output = row["hash"] != "varies" and any(
                r["hash"] == row["hash"] and r["reasoning"] < row["reasoning"] for r in rows
            )
            row["verdict"] = "waste (identical output)" if same_output else "waste (no quality gain)"
    return rows


def _print_sweep(report: dict) -> None:
    route = report.get("route", "?")
    rows = _verdict_rows(report.get("cells", []))
    if not rows:
        return

    print(f"\n  ROUTE: {route}   (model: {report['cells'][0].get('model', '?')})")
    print(f"  {'effort':<9}{'quality':>8}{'reasoning':>11}{'cached_in':>11}{'$/call':>10}   verdict")
    print("  " + "-" * 74)
    for r in rows:
        print(f"  {r['effort']:<9}{r['score']:>7.1f}{r['reasoning']:>11,}"
              f"{r['cached_in']:>11,}{r['cost']:>10.5f}   {r['verdict']}")

    knee = next((r for r in rows if r["verdict"].startswith("knee")), None)
    top = max(rows, key=lambda r: r["reasoning"])
    if knee and top["reasoning"] > knee["reasoning"]:
        saved = top["cost"] - knee["cost"]
        pct = 100 * saved / top["cost"] if top["cost"] else 0
        print(f"    -> shipping '{knee['effort']}' instead of '{top['effort']}' "
              f"saves ${saved:.5f}/call ({pct:.0f}%) at equal quality")


def _print_single(report: dict) -> None:
    for cell in report.get("cells", []):
        print(f"\n  ROUTE: {report.get('route','?')}   effort={cell.get('effort')}"
              f"   score={cell.get('score')}")
        for k, v in (cell.get("quality") or {}).items():
            print(f"    {k:<24} {v}")
        s = cell.get("spend", {})
        print(f"    {'cost_usd':<24} {s.get('cost_usd')}   "
              f"(in={s.get('input_tokens'):,} cached={s.get('cached_input_tokens'):,} "
              f"out={s.get('output_tokens'):,} reasoning={s.get('reasoning_tokens'):,})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Read AutoShorts validation reports.")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = ap.parse_args()

    reports = _load(args.dir)
    sweeps = [r for r in reports if r["_file"].startswith("sweep_")]
    singles = [r for r in reports if r["_file"].startswith("replay_")]

    print("=" * 78)
    print(" ROUTE RIGHT-SIZING  (is each route's effort matched to its task?)")
    print("=" * 78)
    if sweeps:
        for r in sweeps:
            _print_sweep(r)
    else:
        print("\n  (no sweep_*.json yet — run: replay_harness.py sweep --route <name>)")

    print("\n" + "=" * 78)
    print(" SINGLE-SHOT REPLAYS")
    print("=" * 78)
    if singles:
        for r in singles:
            _print_single(r)
    else:
        print("\n  (no replay_*.json yet)")

    total = sum(
        c.get("spend", {}).get("cost_usd", 0.0)
        for r in reports for c in r.get("cells", [])
    )
    print("\n" + "-" * 78)
    print(f"  Total spent across all reports in {args.dir.name}/: ${total:.4f}")
    print("-" * 78 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
