"""
AutoShorts — OpenAI validation replay harness
=============================================
Feeds ARCHIVED Gemini-era inputs to the current OpenAI routes and scores the
output against objective, already-existing checks.

Why replay instead of re-running the pipeline: every input AND the Gemini
baseline is already on disk under ``jobs/``. Replaying spends nothing on Tavily
(sources are archived), nothing on Gemini (its answers are archived), and nothing
on TTS/render (validation stops at the script). Only OpenAI tokens are burned.

Nothing here re-implements quality judgement — every metric calls the same code
the pipeline itself uses (``parse_monologue``, ``_get_failing_segments``,
``validate_template_semantics``, ``_parse_scoring_response``, ...), so a passing
replay means the real pipeline would have passed too.

Subcommands
-----------
    ideate   --niche "..."                     one ideation call
    score    --from jobs/auto/auto_8 --n 5     N archived candidates -> scoring
    extract  --from jobs/sort_card/sort_card_1 archived sources -> extraction
    draft    --from jobs/sort_card/sort_card_1 archived dataset -> one draft call
    sweep    --route scoring --efforts a,b,c   same input at several efforts

Reports land in ``validation/*.json``. Read them with scripts/compare_report.py.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Model output contains smart quotes and em-dashes; a cp1252 console mangles them
# and makes a clean extraction look corrupted. Mirrors the CLI entry points.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from src.agents.core import cost_tracker as ct  # noqa: E402
from src.agents.core.config import APP_CONFIG, PhaseModel  # noqa: E402
from src.agents.core.models import (  # noqa: E402
    SourceAudit,
    TemplateDataset,
    TEMPLATE_CAPACITIES,
    TEMPLATE_PRESENTATION_FIELDS,
    VALID_TEMPLATES,
    validate_template_semantics,
)
from src.agents.phase1_discovery.candidate_score import (  # noqa: E402
    _parse_scoring_response,
    score_single_candidate,
)
from src.agents.core.rate_limiter import TokenBucketRateLimiter  # noqa: E402
from src.agents.phase1_discovery.discovery_runner import _ideate_hypotheses  # noqa: E402
from src.agents.phase1_extraction.api_clients import extract_dataset  # noqa: E402
from src.agents.phase1_extraction.runner import _build_template_spec  # noqa: E402
from src.agents.phase2_scripting.contracts import ParsedSegment  # noqa: E402
from src.agents.phase2_scripting.llm_writer import (  # noqa: E402
    _build_system_prompt,
    _build_user_prompt,
    _call_llm,
    _ends_dangling,
    _get_failing_segments,
    _numbers_preserved,
    _run_script_doctor,
)
from src.agents.phase2_scripting.timing import build_segment_plan  # noqa: E402
from src.agents.phase2_scripting.xml_parser import parse_monologue  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("replay")

REPORT_DIR = PROJECT_ROOT / "validation"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=APP_CONFIG.llm_timeout_seconds)
    )


def _route(name: str, effort: str | None = None) -> PhaseModel:
    """The configured route, optionally with reasoning_effort overridden."""
    cfg: PhaseModel = getattr(APP_CONFIG.llm, name)
    return cfg if effort is None else cfg.model_copy(update={"reasoning_effort": effort})


def _spend() -> dict[str, Any]:
    """Token/cost totals for the calls made since the last reset."""
    t = ct.get_session_totals()
    return {
        "input_tokens": t["total_input"],
        "cached_input_tokens": t["total_cached_input"],
        # Shown separately so a run that merely SEEDED the cache is not mistaken
        # for one that failed to use it — writes cost 1.25x, reads cost 0.1x.
        "cache_write_tokens": t["total_cache_write"],
        "output_tokens": t["total_output"],
        "reasoning_tokens": t["total_reasoning"],
        "cost_usd": round(t["total_cost_usd"], 6),
        "calls": len(ct._SESSION["calls"]),
    }


def _hash(value: Any) -> str:
    """Stable digest of an output — equal hashes across efforts mean the extra
    reasoning bought nothing."""
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _save(name: str, payload: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    path = REPORT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def _latest(pattern: str) -> Path | None:
    hits = sorted((PROJECT_ROOT / "jobs").glob(pattern))
    return hits[-1] if hits else None


# ---------------------------------------------------------------------------
# Route replays. Each returns {quality: {...}, score: 0-10, output_hash: str}
# ---------------------------------------------------------------------------


async def replay_ideation(effort: str | None, niche: str, count: int = 10) -> dict:
    async with _session() as session:
        ideas = await _ideate_hypotheses(niche, "", session, log, idea_count=count)

    uniq = {i.strip().lower() for i in ideas}
    dup_rate = 1 - (len(uniq) / len(ideas)) if ideas else 1.0
    count_ok = bool(ideas) and abs(len(ideas) - count) <= max(1, round(count * 0.2))

    quality = {
        "parsed": bool(ideas),
        "returned": len(ideas),
        "requested": count,
        "count_within_20pct": count_ok,
        "duplicate_rate": round(dup_rate, 3),
    }
    score = 0.0 if not ideas else 10.0 * (1 - dup_rate) * (1.0 if count_ok else 0.6)
    return {"quality": quality, "score": round(score, 2),
            "output_hash": _hash(sorted(uniq)), "sample": ideas[:3]}


async def replay_scoring(effort: str | None, job: Path, n: int) -> dict:
    raw_path = job / "discovery" / "raw_candidates.json"
    base_path = job / "discovery" / "candidates.json"
    raw_all = json.loads(raw_path.read_text(encoding="utf-8"))

    # Gemini's answers for the same titles — the free baseline.
    baseline = {}
    if base_path.exists():
        for c in json.loads(base_path.read_text(encoding="utf-8")).get("candidates", []):
            baseline[c["topic"].strip().lower()] = c

    # Only a subset of raw candidates survived scoring into candidates.json, and
    # they are not the first N. Score the ones we HAVE a Gemini answer for first,
    # otherwise the agreement column is empty and the whole comparison is wasted.
    with_base = [r for r in raw_all if r["title"].strip().lower() in baseline]
    without = [r for r in raw_all if r["title"].strip().lower() not in baseline]
    raw = (with_base + without)[:n]

    limiter = TokenBucketRateLimiter(rpm=APP_CONFIG.llm.rpm_limit)
    results, agree, compared = [], 0, 0

    async with _session() as session:
        for item in raw:
            cand = await score_single_candidate(
                item["title"], item.get("snippet", ""), session, limiter, log
            )
            if cand is None:
                results.append({"topic": item["title"], "parsed": False})
                continue
            base = baseline.get(item["title"].strip().lower())
            row = {
                "topic": item["title"],
                "parsed": True,
                "template": cand.best_fit_template,
                "feasibility": cand.data_feasibility_score,
                "final": round(cand.final_score, 2),
                # The prompt caps this at 15 words; an overrun means the model
                # is ignoring an explicit instruction.
                "summary_words": len((cand.data_summary or "").split()),
            }
            if base:
                compared += 1
                row["gemini_template"] = base.get("best_fit_template")
                row["gemini_feasibility"] = base.get("data_feasibility_score")
                if row["template"] == base.get("best_fit_template"):
                    agree += 1
            results.append(row)

    parsed = [r for r in results if r.get("parsed")]
    parse_rate = len(parsed) / len(raw) if raw else 0.0
    cap_ok = sum(1 for r in parsed if r["summary_words"] <= 15)
    quality = {
        "parse_rate": round(parse_rate, 2),
        "template_agreement": f"{agree}/{compared}" if compared else "no baseline",
        "word_cap_respected": f"{cap_ok}/{len(parsed)}" if parsed else "0/0",
    }
    score = 10.0 * parse_rate * (cap_ok / len(parsed) if parsed else 0)
    return {"quality": quality, "score": round(score, 2),
            "output_hash": _hash([(r.get("template"), r.get("feasibility")) for r in results]),
            "rows": results}


async def replay_extraction(effort: str | None, job: Path) -> dict:
    audit_path = next(job.glob("data/best_fit/sources_audit.json"), None)
    if audit_path is None:
        raise SystemExit(f"No sources_audit.json under {job}")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    template = audit["template_name"]
    sources = [SourceAudit.model_validate(s) for s in audit["sources"]]
    topic = audit.get("topic") or job.name

    baseline_path = next(job.glob(f"data/best_fit/{template}_dataset.json"), None)
    baseline = (
        TemplateDataset.model_validate(json.loads(baseline_path.read_text(encoding="utf-8")))
        if baseline_path else None
    )

    # Some archived datasets PRE-DATE the renderer-contract fixes and are
    # themselves invalid (e.g. sort_card_1 stores category='Instant Settlement'
    # instead of '1'/'2'). Compute the baseline's own verdict UP FRONT and report
    # it on every path, so "OpenAI differs from Gemini" is never mistaken for
    # "OpenAI is wrong" — including when our own extraction fails.
    base_ok = None
    if baseline is not None:
        base_ok, _ = validate_template_semantics(template, baseline.rows, baseline.meta)

    spec = _build_template_spec(template)
    async with _session() as session:
        try:
            dataset = await extract_dataset(topic, sources, template, spec, session, log)
            err = None
        except Exception as exc:  # parse_failure / schema_failure / transport
            dataset, err = None, f"{type(exc).__name__}: {exc}"

    if dataset is None:
        return {
            "quality": {"schema_valid": False, "error": err,
                        "gemini_baseline_valid": base_ok},
            "score": 0.0, "output_hash": "n/a",
        }

    ok, reason = validate_template_semantics(template, dataset.rows, dataset.meta)
    cap = TEMPLATE_CAPACITIES[template]
    presentation = TEMPLATE_PRESENTATION_FIELDS.get(template, set())
    nulls = sum(
        1 for r in dataset.rows
        for f, v in r.model_dump().items()
        if f not in presentation and (v is None or v == "")
    )
    quality = {
        "schema_valid": True,
        "semantics_valid": ok,
        "semantics_reason": reason,
        "rows": len(dataset.rows),
        "capacity": f"{cap.min}-{cap.max}",
        "rows_in_capacity": cap.min <= len(dataset.rows) <= cap.max,
        "null_fields": nulls,
        "gemini_rows": len(baseline.rows) if baseline else None,
        "gemini_baseline_valid": base_ok,
    }
    score = 10.0 if (ok and quality["rows_in_capacity"] and nulls == 0) else (
        6.0 if ok else 2.0
    )
    return {"quality": quality, "score": score,
            "output_hash": _hash(dataset.model_dump(mode="json")),
            "meta": dataset.meta}


async def replay_draft(effort: str | None, job: Path, persona: str) -> dict:
    """ONE draft call — isolates the model from the rewrite/doctor loop."""
    ds_path = next(job.glob("data/best_fit/*_dataset.json"), None)
    if ds_path is None:
        raise SystemExit(f"No dataset under {job}")
    dataset = TemplateDataset.model_validate(json.loads(ds_path.read_text(encoding="utf-8")))
    plan = build_segment_plan(job.name, dataset.template_name, persona, dataset)

    system_prompt = _build_system_prompt(persona)
    user_prompt = _build_user_prompt(dataset, plan)
    # `effort` is already applied to APP_CONFIG by _run_cell — read it back rather
    # than re-deriving, so every replay path uses the identical override mechanism.
    route = _route("scripting_draft")

    async with _session() as session:
        try:
            raw = await _call_llm(system_prompt, user_prompt, session, log,
                                  route, "replay_draft", cache_key=f"as-p2-{persona}")
            err = None
        except Exception as exc:
            raw, err = None, f"{type(exc).__name__}: {exc}"

    if raw is None:
        return {"quality": {"parsed": False, "error": err}, "score": 0.0, "output_hash": "n/a"}

    fenced = "```" in raw
    try:
        # parse_monologue returns a LIST; the budget checker wants a tag->segment
        # dict. Same conversion llm_writer.write_script does before calling it.
        segments = {seg.tag: seg for seg in parse_monologue(raw, plan)}
        parsed = True
        parse_err = None
    except Exception as exc:
        segments, parsed, parse_err = {}, False, str(exc)

    if not parsed:
        return {"quality": {"parsed": False, "error": parse_err, "markdown_fences": fenced},
                "score": 0.0, "output_hash": _hash(raw)}

    # Returns [(ParsedSegment, reason), ...] — not bare tags.
    failing = _get_failing_segments(segments, plan)
    failing_tags = sorted(seg.tag for seg, _reason in failing)
    dangling = [t for t, s in segments.items() if _ends_dangling(s.text)]
    in_budget = len(plan.segments) - len(failing)

    quality = {
        "parsed": True,
        "tags": f"{len(segments)}/{len(plan.segments)}",
        "in_budget": f"{in_budget}/{len(plan.segments)}",
        "failing_tags": failing_tags,
        "failing_reasons": [reason for _seg, reason in failing],
        "dangling_endings": dangling,
        "markdown_fences": fenced,
        # Gemini-era calibration (_CHARS_PER_WORD = 6.0) — re-derive it for free.
        "chars_per_word": round(
            sum(len(s.text) for s in segments.values())
            / max(1, sum(len(s.text.split()) for s in segments.values())), 2),
    }
    score = 10.0 * (in_budget / len(plan.segments))
    if dangling:
        score -= 1.0
    if fenced:
        score -= 1.0
    return {"quality": quality, "score": round(max(0.0, score), 2),
            "output_hash": _hash({t: s.text for t, s in segments.items()})}


async def replay_doctor(effort: str | None, job: Path, persona: str) -> dict:
    """Run ONLY the script-doctor over an already-valid script.

    The doctor is the single most expensive call in Phase 2 and it is
    accept-or-revert: any budget/tag/number violation in its output causes the
    pre-doctor script to be kept, so a discarded pass is money spent for nothing
    AND polish not delivered. Replaying it against an archived script isolates it
    from the draft, which is what makes an effort sweep here affordable.
    """
    ds_path = next(job.glob("data/best_fit/*_dataset.json"), None)
    script_path = job / "script" / "script.json"
    if ds_path is None or not script_path.exists():
        raise SystemExit(f"{job} needs both a dataset and a script.json")

    dataset = TemplateDataset.model_validate(json.loads(ds_path.read_text(encoding="utf-8")))
    script = json.loads(script_path.read_text(encoding="utf-8"))
    plan = build_segment_plan(job.name, dataset.template_name, persona, dataset)

    before = {
        s["tag"]: ParsedSegment(
            tag=s["tag"], text=s["text"], char_count=s["char_count"],
            target_min_chars=s["target_min_chars"], target_max_chars=s["target_max_chars"],
        )
        for s in script["segments"]
    }

    system_prompt = _build_system_prompt(persona)
    async with _session() as session:
        after, note = await _run_script_doctor(before, plan, dataset, system_prompt, session, log)

    applied = "[DISCARDED" not in note
    changed = any(before[t].text != after[t].text for t in before if t in after)
    failing_after = _get_failing_segments(after, plan)

    quality = {
        "applied": applied,
        "note": note.strip().splitlines()[-1] if note.strip() else "",
        "text_changed": changed,
        "in_budget_after": f"{len(plan.segments) - len(failing_after)}/{len(plan.segments)}",
    }
    # Applying a real polish is the whole point; a discard is a total loss.
    score = 10.0 if (applied and changed) else (5.0 if applied else 0.0)
    return {"quality": quality, "score": score,
            "output_hash": _hash({t: s.text for t, s in after.items()})}


_REPLAYS = {
    "ideation": lambda a, e: replay_ideation(e, a.niche, a.count),
    "scoring": lambda a, e: replay_scoring(e, a.job, a.n),
    "extraction": lambda a, e: replay_extraction(e, a.job),
    "draft": lambda a, e: replay_draft(e, a.job, a.persona),
    "doctor": lambda a, e: replay_doctor(e, a.job, a.persona),
}

# Which configured route each replay drives (for the effort override).
_ROUTE_OF = {
    "ideation": "discovery_ideation",
    "scoring": "discovery_scoring",
    "extraction": "extraction",
    "draft": "scripting_draft",
    "doctor": "scripting_doctor",
}


async def _run_cell(name: str, args, effort: str | None) -> dict:
    """One measured call-set at one effort, with its own cost accounting."""
    route_name = _ROUTE_OF[name]
    original = getattr(APP_CONFIG.llm, route_name)
    if effort is not None:
        setattr(APP_CONFIG.llm, route_name, _route(route_name, effort))
    ct.reset_session()
    try:
        result = await _REPLAYS[name](args, effort)
    finally:
        setattr(APP_CONFIG.llm, route_name, original)
    result["spend"] = _spend()
    result["effort"] = effort or original.reasoning_effort
    result["model"] = original.model
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_source_args(p, need_persona=False):
    p.add_argument("--job", type=Path, help="Archived job dir to replay from.")
    if need_persona:
        p.add_argument("--persona", default="hyper_analyst")


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay archived inputs through OpenAI routes.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ideate")
    p.add_argument("--niche", default="personal finance")
    p.add_argument("--count", type=int, default=10)

    p = sub.add_parser("score")
    _add_source_args(p)
    p.add_argument("-n", type=int, default=5, help="How many archived candidates to score.")

    p = sub.add_parser("extract")
    _add_source_args(p)

    p = sub.add_parser("draft")
    _add_source_args(p, need_persona=True)

    p = sub.add_parser("doctor")
    _add_source_args(p, need_persona=True)

    p = sub.add_parser("sweep")
    p.add_argument("--route", required=True, choices=sorted(_REPLAYS))
    p.add_argument("--efforts", default="minimal,low,medium,high")
    p.add_argument("--reps", type=int, default=2)
    p.add_argument("--niche", default="personal finance")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("-n", type=int, default=3)
    _add_source_args(p, need_persona=True)

    args = ap.parse_args()

    name = args.route if args.cmd == "sweep" else {
        "ideate": "ideation", "score": "scoring",
        "extract": "extraction", "draft": "draft", "doctor": "doctor",
    }[args.cmd]

    # Sensible archived defaults so the common case needs no --job. Scoring reads
    # from a discovery run; extraction/draft read from a template job.
    if getattr(args, "job", None) is None:
        if name == "scoring":
            found = _latest("auto/*/discovery/candidates.json")
            args.job = found.parent.parent if found else None
        elif name == "extraction":
            # vs_card_3 is the ONLY archived dataset that both carries a real
            # renderer-contract constraint (winner must be 0/1/2) and passes it.
            # Neither sort_card baseline is valid — Gemini failed that template on
            # category values once and on the 'A vs B' TITLE format the other time.
            args.job = PROJECT_ROOT / "jobs" / "vs_card" / "vs_card_3"
        else:
            # draft needs an archived script.json to compare against — only _1 has one.
            args.job = PROJECT_ROOT / "jobs" / "sort_card" / "sort_card_1"
        if args.job is None or not args.job.exists():
            raise SystemExit(
                f"No archived job found for '{name}'. Pass --job <dir> explicitly."
            )

    if args.cmd != "sweep":
        result = asyncio.run(_run_cell(name, args, None))
        path = _save(f"replay_{name}", {"route": name, "cells": [result]})
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        print(f"\nsaved -> {path}")
        return 0 if result["score"] > 0 else 1

    efforts = [e.strip() for e in args.efforts.split(",") if e.strip()]
    cells = []
    for effort in efforts:
        for rep in range(args.reps):
            print(f"  {name} effort={effort} rep={rep + 1}/{args.reps} ...", flush=True)
            cell = asyncio.run(_run_cell(name, args, effort))
            cell["rep"] = rep + 1
            cells.append(cell)
            print(f"    score={cell['score']}  reasoning={cell['spend']['reasoning_tokens']}"
                  f"  ${cell['spend']['cost_usd']}  hash={cell['output_hash']}")

    path = _save(f"sweep_{name}", {"route": name, "efforts": efforts,
                                   "reps": args.reps, "cells": cells})
    print(f"\nsaved -> {path}")
    print("Read it with: python scripts/compare_report.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
