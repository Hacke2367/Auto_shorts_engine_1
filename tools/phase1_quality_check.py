"""
Phase 1 Discovery — Quality / Bias / Scoring Auditor
====================================================
Reads a discovery run's ``candidates.json`` and prints a structured audit so you
can eyeball, at a glance, whether the Summary-First overhaul is working:

  - Template DISTRIBUTION (is any one template dominating? = bias smell)
  - data_summary presence (the routing bridge must be populated for every pick)
  - Output WORD-CAP compliance (data_summary<=15, template_reasoning<=10, rationale<=20)
  - SCORING sanity (scores in range; the "feasibility<5 => confidence low" rule held)

This tool makes NO API calls — it only reads a file already produced by a
discovery run. Run a real discovery first (that step costs money and is yours
to trigger), then point this at its output:

    python tools/phase1_quality_check.py --job jobs/auto/auto_3

You can also import ``audit_candidates(list_of_dicts)`` directly (used by tests).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Word caps enforced by the scoring prompt (kept in sync with candidate_score.py).
WORD_CAPS = {
    "data_summary": 15,
    "fit_reason": 10,   # holds template_reasoning ("shape -> template")
    "rationale": 20,
}
# Above this share, a single template is "dominating" — a bias warning, not an error.
DOMINANCE_THRESHOLD = 0.60


def _wc(text: str | None) -> int:
    return len((text or "").split())


def audit_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute a quality/bias/scoring report from a list of candidate dicts.

    Pure function (no I/O) so tests can feed synthetic candidates.
    """
    total = len(candidates)
    dist = Counter(c.get("best_fit_template", "?") for c in candidates)

    dominant_template, dominant_count = (dist.most_common(1)[0] if dist else ("-", 0))
    dominant_share = (dominant_count / total) if total else 0.0

    missing_summary = [
        c.get("topic", "?") for c in candidates if not (c.get("data_summary") or "").strip()
    ]

    word_violations: list[str] = []
    for c in candidates:
        for field, cap in WORD_CAPS.items():
            n = _wc(c.get(field))
            if n > cap:
                word_violations.append(
                    f"{field}={n}w (>{cap}) on '{c.get('topic', '?')[:48]}'"
                )

    score_violations: list[str] = []
    finals: list[float] = []
    for c in candidates:
        topic = c.get("topic", "?")[:48]
        finals.append(float(c.get("final_score", 0.0)))
        for f in (
            "hook_potential_score", "novelty_score", "visual_fit_score",
            "data_feasibility_score", "freshness_score",
        ):
            v = c.get(f)
            if v is not None and not (1.0 <= float(v) <= 10.0):
                score_violations.append(f"{f}={v} out of [1,10] on '{topic}'")
        # Prompt rule: data_feasibility < 5 => validation_confidence MUST be low.
        feas = float(c.get("data_feasibility_score", 10.0))
        conf = str(c.get("validation_confidence", "")).lower()
        if feas < 5.0 and conf != "low":
            score_violations.append(
                f"feasibility={feas} but confidence='{conf}' (rule: must be 'low') on '{topic}'"
            )

    return {
        "total": total,
        "distribution": dict(dist),
        "distinct_templates": len(dist),
        "dominant_template": dominant_template,
        "dominant_share": dominant_share,
        "bias_warning": dominant_share > DOMINANCE_THRESHOLD,
        "missing_summary": missing_summary,
        "word_violations": word_violations,
        "score_violations": score_violations,
        "final_score_min": min(finals) if finals else 0.0,
        "final_score_max": max(finals) if finals else 0.0,
        "final_score_avg": (sum(finals) / len(finals)) if finals else 0.0,
    }


def print_report(report: dict[str, Any]) -> None:
    line = "=" * 60
    print(line)
    print(" PHASE 1 DISCOVERY - QUALITY / BIAS / SCORING AUDIT")
    print(line)
    print(f"Candidates: {report['total']}   Distinct templates: {report['distinct_templates']}")
    print()
    print("Template distribution:")
    for t, n in sorted(report["distribution"].items(), key=lambda kv: -kv[1]):
        bar = "#" * n
        print(f"  {t:16s} {n:2d}  {bar}")
    print()

    share_pct = report["dominant_share"] * 100
    if report["bias_warning"]:
        print(f"[WARN] BIAS: '{report['dominant_template']}' is {share_pct:.0f}% of picks "
              f"(> {DOMINANCE_THRESHOLD*100:.0f}%). Topics may be skewing to one shape.")
    else:
        print(f"[OK]   Spread fine: most common is '{report['dominant_template']}' at {share_pct:.0f}%.")

    if report["missing_summary"]:
        print(f"[WARN] data_summary MISSING on {len(report['missing_summary'])} candidate(s) "
              f"- routing bridge not populated.")
    else:
        print("[OK]   data_summary present on every candidate (routing bridge alive).")

    if report["word_violations"]:
        print(f"[WARN] WORD-CAP overruns ({len(report['word_violations'])}):")
        for v in report["word_violations"]:
            print(f"     - {v}")
    else:
        print("[OK]   Output word-caps respected (no essays).")

    if report["score_violations"]:
        print(f"[WARN] SCORING issues ({len(report['score_violations'])}):")
        for v in report["score_violations"]:
            print(f"     - {v}")
    else:
        print("[OK]   Scoring sane (in-range; feasibility<5 => confidence low held).")

    print()
    print(f"final_score: min={report['final_score_min']:.2f}  "
          f"avg={report['final_score_avg']:.2f}  max={report['final_score_max']:.2f}")
    print(line)


def _load_candidates(job_dir: Path) -> list[dict[str, Any]]:
    path = job_dir / "discovery" / "candidates.json"
    if not path.exists():
        # tolerate being given the discovery dir or the file itself
        for alt in (job_dir / "candidates.json", job_dir):
            if alt.is_file() and alt.suffix == ".json":
                path = alt
                break
    if not path.exists():
        print(f"ERROR: candidates.json not found under {job_dir}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("candidates", []) if isinstance(data, dict) else data


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit a Phase 1 discovery run for quality/bias/scoring.")
    ap.add_argument("--job", required=True,
                    help="Job dir (e.g. jobs/auto/auto_3) or a candidates.json path.")
    args = ap.parse_args()

    candidates = _load_candidates(Path(args.job))
    print_report(audit_candidates(candidates))


if __name__ == "__main__":
    main()
