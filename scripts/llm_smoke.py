"""
AutoShorts — LLM smoke test (the ONE paid verification step)
============================================================
Fires a single tiny call and dumps the RAW provider response.

Why this exists: two details could not be confirmed from documentation alone,
and both fail silently rather than loudly if we guessed wrong.

1. The exact ``usage.*`` field names. The client reads
   ``usage.input_tokens_details.cached_tokens`` and
   ``usage.output_tokens_details.reasoning_tokens`` with flat fallbacks. If the
   real names differ from BOTH, every cost number quietly reports 0.
2. Where ``verbosity`` nests (``text.verbosity`` vs top level). Wrong placement
   is a 400 on every call once it is wired into all six routes.

Cost: roughly $0.001. Run it once, paste the output back, and the numbers in the
cost dashboard become trustworthy.

Usage:
    python scripts/llm_smoke.py
    python scripts/llm_smoke.py --provider gemini --model gemini-2.5-flash
    python scripts/llm_smoke.py --effort medium --verbosity high
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Windows consoles default to cp1252 and mangle the em-dashes in the cost summary.
# Mirrors what src/cli/autoshorts.py and src/cli/phase1.py already do.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from src.agents.core import cost_tracker as ct  # noqa: E402
from src.agents.core.config import APP_CONFIG, PhaseModel  # noqa: E402
from src.agents.core.llm_client import call_llm_raw  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("llm_smoke")

PROMPT = (
    "Reply with exactly one sentence about why data visualisation matters. "
    "No preamble."
)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Single-call LLM smoke test.")
    ap.add_argument("--provider", default="openai", choices=["openai", "gemini"])
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--effort", default="low", help="OpenAI reasoning.effort")
    ap.add_argument("--verbosity", default="low", help="OpenAI text.verbosity")
    ap.add_argument("--json-mode", action="store_true",
                    help="Also exercise JSON mode (asks for a JSON object).")
    args = ap.parse_args()

    route = PhaseModel(
        provider=args.provider,
        model=args.model,
        reasoning_effort=args.effort if args.provider == "openai" else None,
        verbosity=args.verbosity if args.provider == "openai" else None,
    )

    print("=" * 68)
    print(" LLM SMOKE TEST")
    print("=" * 68)
    print(f"  provider={route.provider}  model={route.model}")
    print(f"  effort={route.reasoning_effort}  verbosity={route.verbosity}")
    print(f"  timeout={APP_CONFIG.llm_timeout_seconds}s")
    print()

    prompt = PROMPT
    if args.json_mode:
        prompt = 'Reply with a JSON object shaped {"answer": "<one sentence>"}.'

    timeout = aiohttp.ClientTimeout(total=APP_CONFIG.llm_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            result = await call_llm_raw(
                None, prompt, session, log, route, "smoke",
                expect_json=args.json_mode,
                cache_key="as-smoke-v1",
            )
        except Exception as exc:
            print(f"FAILED: {type(exc).__name__}: {exc}")
            return 1

    print("--- TEXT ---")
    print(result.text.strip())
    print()
    print("--- USAGE AS PARSED BY THE CLIENT ---")
    print(json.dumps(result.usage, indent=2))
    print()
    print("--- RAW usage BLOCK (verify the field names above match) ---")
    print(json.dumps(result.raw.get("usage") or result.raw.get("usageMetadata") or {}, indent=2))
    print()
    print("--- OUTPUT ITEM TYPES, IN ORDER ---")
    if args.provider == "openai":
        types = [i.get("type") for i in (result.raw.get("output") or []) if isinstance(i, dict)]
        print(types)
        if "reasoning" in types:
            print("(a reasoning item is present, and precedes the message —")
            print(" indexing output[0] would grab the WRONG item; the adapter scans instead)")
        else:
            print("(no reasoning item on this call — it only appears when the model")
            print(" actually reasons, which is why the adapter must scan, not index)")
    print()
    print("--- COST ---")
    print(ct.get_session_summary())

    zero_usage = not any(result.usage.values())
    if zero_usage:
        print()
        print("!! Every usage field parsed as 0. The provider's field names have")
        print("!! changed — update _openai_usage/_gemini_usage in core/llm_client.py")
        print("!! using the RAW block above, or cost tracking will report nothing.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
