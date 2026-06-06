import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini Pricing (USD per 1M tokens) — verify at: ai.google.dev/pricing
# gemini-2.5-flash non-thinking tier (prompts <= 200K tokens)
# ---------------------------------------------------------------------------
_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro":   {"input": 1.25,  "output": 10.00},
}
_FALLBACK_PRICING = {"input": 0.075, "output": 0.30}


def _cost_usd(model: str, prompt_tokens: int, output_tokens: int) -> float:
    p = _PRICING.get(model, _FALLBACK_PRICING)
    return (prompt_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# In-memory session accumulator (resets each CLI run)
# ---------------------------------------------------------------------------
_SESSION: dict[str, Any] = {
    "calls": [],          # list of per-call dicts
    "total_prompt": 0,
    "total_output": 0,
    "total_cost_usd": 0.0,
    "rate_limit_hits": 0,
}


def track_gemini_call(
    phase: str,
    model: str,
    prompt_tokens: int,
    output_tokens: int,
    job_dir: Path | None = None,
) -> None:
    """Record one Gemini API call in the session accumulator and optionally to JSONL.

    Fire-and-forget: never raises — pipeline must never crash from cost tracking.
    """
    try:
        cost = _cost_usd(model, prompt_tokens, output_tokens)
        record: dict[str, Any] = {
            "phase": phase,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": prompt_tokens + output_tokens,
            "cost_usd": round(cost, 8),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        _SESSION["calls"].append(record)
        _SESSION["total_prompt"] += prompt_tokens
        _SESSION["total_output"] += output_tokens
        _SESSION["total_cost_usd"] += cost

        if job_dir is not None:
            record_cost(job_dir, record)

    except Exception as exc:
        logger.warning("Cost tracking failed (non-fatal): %s", exc)


def track_rate_limit_hit() -> None:
    """Increment the 429 counter for the current session."""
    _SESSION["rate_limit_hits"] += 1


def get_session_summary(configured_rpm: int | None = None) -> str:
    """Return a formatted cost/usage summary for the current CLI session."""
    calls = _SESSION["calls"]
    if not calls:
        return "No Gemini API calls recorded this session."

    lines = [
        "",
        "=" * 55,
        " GEMINI USAGE — THIS SESSION",
        "=" * 55,
    ]

    # Per-phase breakdown
    phases: dict[str, dict[str, Any]] = {}
    for c in calls:
        ph = c["phase"]
        if ph not in phases:
            phases[ph] = {"calls": 0, "prompt": 0, "output": 0, "cost": 0.0}
        phases[ph]["calls"] += 1
        phases[ph]["prompt"] += c["prompt_tokens"]
        phases[ph]["output"] += c["output_tokens"]
        phases[ph]["cost"] += c["cost_usd"]

    lines.append(f"  {'Phase':<22} {'Calls':>5}  {'Tokens':>8}  {'Cost (USD)':>12}")
    lines.append("  " + "-" * 51)
    for ph, v in phases.items():
        total_tok = v["prompt"] + v["output"]
        lines.append(
            f"  {ph:<22} {v['calls']:>5}  {total_tok:>8,}  ${v['cost']:>11.6f}"
        )

    lines.append("  " + "-" * 51)
    total_tok = _SESSION["total_prompt"] + _SESSION["total_output"]
    total_cost = _SESSION["total_cost_usd"]
    lines.append(
        f"  {'TOTAL':<22} {len(calls):>5}  {total_tok:>8,}  ${total_cost:>11.6f}"
    )

    lines.append("")
    lines.append(f"  Prompt tokens : {_SESSION['total_prompt']:,}")
    lines.append(f"  Output tokens : {_SESSION['total_output']:,}")

    rl = _SESSION["rate_limit_hits"]
    if rl:
        lines.append(f"  Rate limit hits (429): {rl}  <- consider spacing your runs")

    if configured_rpm is not None:
        lines.append(f"  Configured RPM throttle : {configured_rpm}  (your self-imposed cap)")
        lines.append("  Google-side quota       : check AI Studio / Google Cloud Console")

    lines.append("=" * 55)
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
