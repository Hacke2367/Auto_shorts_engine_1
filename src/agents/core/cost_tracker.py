"""
AutoShorts Core — LLM Cost Tracking
===================================
Provider-neutral accounting for every LLM call the pipeline makes.

The ONE rule that keeps this honest:

    ``output_tokens`` passed to :func:`track_llm_call` is ALREADY-BILLED output.

Providers disagree about whether reasoning tokens are included in their output
count, so the conversion happens at the call site (or in the provider adapter),
never here:

* **Gemini** — ``thoughtsTokenCount`` is *separate* from ``candidatesTokenCount``
  and billed at the output rate, so the caller passes their SUM.
* **OpenAI** — ``output_tokens_details.reasoning_tokens`` is a *breakdown of*
  ``usage.output_tokens``, so the caller passes ``output_tokens`` unchanged.

``reasoning_tokens`` is therefore reporting-only: it is recorded for visibility
but never added to the billed total. Getting this wrong silently double-counts
every reasoning call, which is exactly the failure this module is shaped to
prevent.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing (USD per 1M tokens) — VERIFY / CALIBRATE against your real invoice.
#
# `cached_input` is the discounted rate for prompt-cache reads. OpenAI bills
# cache hits at ~10% of input; Gemini has no equivalent tier here, so its
# cached rate equals its input rate (i.e. no discount is ever assumed).
# ---------------------------------------------------------------------------
_PRICING: dict[str, dict[str, float]] = {
    # ---- OpenAI (verified 2026-08-05) ----
    "gpt-5.6-sol":   {"input": 5.00, "cached_input": 0.50,  "output": 30.00},
    "gpt-5.6-terra": {"input": 2.00, "cached_input": 0.20,  "output": 12.00},
    "gpt-5.6-luna":  {"input": 0.20, "cached_input": 0.02,  "output": 1.20},
    "gpt-5.5":       {"input": 5.00, "cached_input": 0.50,  "output": 30.00},
    "gpt-5.4":       {"input": 2.50, "cached_input": 0.25,  "output": 15.00},
    "gpt-5.4-mini":  {"input": 0.75, "cached_input": 0.075, "output": 4.50},
    "gpt-5.4-nano":  {"input": 0.20, "cached_input": 0.02,  "output": 1.25},
    "gpt-5.1":       {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5":         {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-mini":    {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano":    {"input": 0.05, "cached_input": 0.005, "output": 0.40},
    # ---- Gemini (legacy provider, kept as the secondary option) ----
    # Pro output ($10/M, prompts <=200K) reconciles with the observed ~Rs.14/script bill.
    "gemini-2.5-flash": {"input": 0.30, "cached_input": 0.30, "output": 2.50},
    "gemini-2.5-pro":   {"input": 1.25, "cached_input": 1.25, "output": 10.00},
}

# Convenience aliases the API accepts.
_MODEL_ALIASES: dict[str, str] = {
    "gpt-5.6": "gpt-5.6-sol",
}

# Models we have already warned about — keeps the log to one line per model.
_WARNED_UNKNOWN_MODELS: set[str] = set()


def _resolve_model(model: str) -> str:
    return _MODEL_ALIASES.get(model, model)


def _rates_for(model: str) -> dict[str, float]:
    """Return the price tier for ``model``.

    Unknown models fall back to the MOST EXPENSIVE known rate, not the cheapest.
    Under a "cost must not go up" mandate an over-report is a visible annoyance
    while an under-report is a silent budget hole — so we bias to over-report,
    and warn once so the missing entry actually gets added.
    """
    resolved = _resolve_model(model)
    rates = _PRICING.get(resolved)
    if rates is not None:
        return rates

    if resolved not in _WARNED_UNKNOWN_MODELS:
        _WARNED_UNKNOWN_MODELS.add(resolved)
        logger.warning(
            "No pricing entry for model %r — billing it at the most expensive known "
            "rate so cost is over-reported rather than hidden. Add it to _PRICING "
            "in src/agents/core/cost_tracker.py.",
            resolved,
        )
    return {
        "input": max(r["input"] for r in _PRICING.values()),
        "cached_input": max(r["cached_input"] for r in _PRICING.values()),
        "output": max(r["output"] for r in _PRICING.values()),
    }


# Writing a prompt prefix into the cache costs MORE than processing it normally
# (gpt-5.6+ bills cache writes at 1.25x the input rate). Ignoring it under-reports
# the first call of every run — exactly the call that seeds the Phase 2 system
# prompt — so it is priced explicitly.
_CACHE_WRITE_MULTIPLIER = 1.25


def _cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Cost in USD.

    ``cached_input_tokens`` and ``cache_write_tokens`` are both SUBSETS of
    ``input_tokens`` (cache reads and cache writes respectively), never additions
    to it. Whatever is left over is billed at the plain input rate.
    """
    rates = _rates_for(model)
    fresh_input = max(0, input_tokens - cached_input_tokens - cache_write_tokens)
    return (
        fresh_input * rates["input"]
        + cached_input_tokens * rates["cached_input"]
        + cache_write_tokens * rates["input"] * _CACHE_WRITE_MULTIPLIER
        + output_tokens * rates["output"]
    ) / 1_000_000


# ---------------------------------------------------------------------------
# In-memory session accumulator (resets each CLI run)
# ---------------------------------------------------------------------------
_SESSION: dict[str, Any] = {
    "calls": [],          # list of per-call dicts
    "total_input": 0,
    "total_output": 0,
    "total_cached_input": 0,
    "total_cache_write": 0,
    "total_reasoning": 0,
    "total_cost_usd": 0.0,
    "rate_limit_hits": 0,
}

# Job dir that JSONL records land in when a call site doesn't pass one.
#
# The alternative was threading `job_dir` down four deep call chains
# (discovery -> ideation, scoring batch -> per-candidate, LangGraph node ->
# extract, script writer -> draft/rewrite/doctor) purely for accounting. A
# process runs exactly one job, so the CLI sets this once at startup instead.
_ACTIVE_JOB_DIR: Path | None = None


def set_active_job_dir(job_dir: Path | str | None) -> None:
    """Point cost accounting at ``job_dir`` for the rest of this process.

    Call once per CLI invocation, as early as the run directory is known.
    Passing ``None`` disables JSONL writing again (used by tests).
    """
    global _ACTIVE_JOB_DIR
    _ACTIVE_JOB_DIR = Path(job_dir) if job_dir is not None else None


def get_active_job_dir() -> Path | None:
    """Return the job dir cost accounting currently writes to, if any."""
    return _ACTIVE_JOB_DIR


def track_llm_call(
    *,
    phase: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
    job_dir: Path | None = None,
) -> None:
    """Record one LLM call in the session accumulator and (if given) to JSONL.

    ``output_tokens`` MUST already include whatever the provider bills at the
    output rate — see the module docstring. ``reasoning_tokens`` is recorded for
    visibility only and is never added on top.

    ``cached_input_tokens`` is the cache-hit subset of ``input_tokens`` (not an
    addition to it) and is priced at the discounted tier.

    Fire-and-forget: never raises — the pipeline must never crash on accounting.
    """
    try:
        cost = _cost_usd(model, input_tokens, output_tokens,
                         cached_input_tokens, cache_write_tokens)
        record: dict[str, Any] = {
            "phase": phase,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "cache_write_tokens": cache_write_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(cost, 8),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        _SESSION["calls"].append(record)
        _SESSION["total_input"] += input_tokens
        _SESSION["total_output"] += output_tokens
        _SESSION["total_cached_input"] += cached_input_tokens
        _SESSION["total_cache_write"] += cache_write_tokens
        _SESSION["total_reasoning"] += reasoning_tokens
        _SESSION["total_cost_usd"] += cost

        target_dir = job_dir if job_dir is not None else _ACTIVE_JOB_DIR
        if target_dir is not None:
            record_cost(target_dir, record)

    except Exception as exc:
        logger.warning("Cost tracking failed (non-fatal): %s", exc)


def track_rate_limit_hit() -> None:
    """Increment the 429 counter for the current session."""
    _SESSION["rate_limit_hits"] += 1


def reset_session() -> None:
    """Clear the in-memory accumulator. Used by tests; a CLI run starts clean anyway."""
    _SESSION["calls"] = []
    _SESSION["total_input"] = 0
    _SESSION["total_output"] = 0
    _SESSION["total_cached_input"] = 0
    _SESSION["total_cache_write"] = 0
    _SESSION["total_reasoning"] = 0
    _SESSION["total_cost_usd"] = 0.0
    _SESSION["rate_limit_hits"] = 0
    _WARNED_UNKNOWN_MODELS.clear()


def get_session_totals() -> dict[str, Any]:
    """Return a copy of the running totals (calls list excluded)."""
    return {k: v for k, v in _SESSION.items() if k != "calls"}


def get_session_summary(configured_rpm: int | None = None) -> str:
    """Return a formatted cost/usage summary for the current CLI session."""
    calls = _SESSION["calls"]
    if not calls:
        return "No LLM API calls recorded this session."

    lines = [
        "",
        "=" * 60,
        " LLM USAGE — THIS SESSION",
        "=" * 60,
    ]

    # Per-phase breakdown
    phases: dict[str, dict[str, Any]] = {}
    for c in calls:
        ph = c["phase"]
        if ph not in phases:
            phases[ph] = {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        phases[ph]["calls"] += 1
        phases[ph]["input"] += c["input_tokens"]
        phases[ph]["output"] += c["output_tokens"]
        phases[ph]["cost"] += c["cost_usd"]

    lines.append(f"  {'Phase':<22} {'Calls':>5}  {'Tokens':>8}  {'Cost (USD)':>12}")
    lines.append("  " + "-" * 56)
    for ph, v in phases.items():
        total_tok = v["input"] + v["output"]
        lines.append(
            f"  {ph:<22} {v['calls']:>5}  {total_tok:>8,}  ${v['cost']:>11.6f}"
        )

    lines.append("  " + "-" * 56)
    total_tok = _SESSION["total_input"] + _SESSION["total_output"]
    total_cost = _SESSION["total_cost_usd"]
    lines.append(
        f"  {'TOTAL':<22} {len(calls):>5}  {total_tok:>8,}  ${total_cost:>11.6f}"
    )

    # Which models actually ran — makes a stray route obvious at a glance.
    models = sorted({f"{c['provider']}:{c['model']}" for c in calls})
    lines.append("")
    lines.append(f"  Models used   : {', '.join(models)}")
    lines.append(f"  Input tokens  : {_SESSION['total_input']:,}")
    if _SESSION["total_cached_input"]:
        pct = 100.0 * _SESSION["total_cached_input"] / max(1, _SESSION["total_input"])
        lines.append(
            f"    of which cached: {_SESSION['total_cached_input']:,} ({pct:.0f}%)"
        )
    if _SESSION["total_cache_write"]:
        lines.append(
            f"    of which cache writes: {_SESSION['total_cache_write']:,}  "
            f"(billed at {_CACHE_WRITE_MULTIPLIER}x input)"
        )
    lines.append(f"  Output tokens : {_SESSION['total_output']:,}")
    if _SESSION["total_reasoning"]:
        lines.append(
            f"    of which reasoning: {_SESSION['total_reasoning']:,}  "
            "(billed at the output rate)"
        )

    rl = _SESSION["rate_limit_hits"]
    if rl:
        lines.append(f"  Rate limit hits (429): {rl}  <- consider spacing your runs")

    if configured_rpm is not None:
        lines.append(f"  Configured RPM throttle : {configured_rpm}  (your self-imposed cap)")
        providers = sorted({c["provider"] for c in calls})
        if "openai" in providers:
            lines.append("  Provider-side quota     : check platform.openai.com usage/limits")
        if "gemini" in providers:
            lines.append("  Provider-side quota     : check AI Studio / Google Cloud Console")

    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-job JSONL writer (existing API, unchanged)
# ---------------------------------------------------------------------------


def record_cost(job_dir: Path | str, record: dict[str, Any]) -> None:
    """Record cost/usage info for a single pipeline step in JSONL format.

    Fire-and-forget: failures are logged as warnings and never propagate.
    """
    try:
        job_dir = Path(job_dir)
        logs_dir = job_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        if "recorded_at" not in record:
            record = {**record, "recorded_at": datetime.now(timezone.utc).isoformat()}

        cost_file = logs_dir / "cost.jsonl"
        with open(cost_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    except Exception as exc:
        logger.warning("Cost record failed (non-fatal): %s — job_dir=%s", exc, job_dir)
