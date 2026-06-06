"""
AutoShorts Phase 2 Scripting — LLM Writer
==========================================
Coordinates the construction of system & user prompts, interacts with
the Gemini API to fetch the script monologue, and implements the
structural/length retry rules.
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.config import settings, APP_CONFIG
from src.agents.core.retry import standard_retry_policy, rate_limit_retry_policy
from src.agents.core.job_manager import PROJECT_ROOT
from src.agents.core.logger import log_api_call
from src.agents.core.cost_tracker import track_gemini_call, track_rate_limit_hit
from src.agents.core.models import TemplateDataset
from src.agents.phase2_scripting.contracts import (
    ParsedSegment,
    ScriptGenerationError,
    ScriptParsingError,
    SegmentPlan,
    count_chars,
    normalize_text,
)
from src.agents.phase2_scripting.xml_parser import parse_monologue

logger = logging.getLogger(__name__)

# Constants & Paths
CONTEXT_DIR = PROJECT_ROOT / ".agent" / "context"
PERSONAS_DIR = CONTEXT_DIR / "personas"
SYSTEM_PROMPTS_DIR = PERSONAS_DIR / "system_prompt"   # canonical — matches runner.py hash

SHARED_CONTRACT_PATH = PERSONAS_DIR / "shared_output_contract.md"
VISUAL_RULES_PATH = CONTEXT_DIR / "template_visual_rules.md"


class GeminiRateLimitError(Exception):
    """Raised when Gemini returns HTTP 429 Too Many Requests."""
    pass


def _get_retry_policy() -> AsyncRetrying:
    """Standard transient-error retry (config-driven, see APP_CONFIG.retry)."""
    return standard_retry_policy()


def _get_429_retry_policy() -> AsyncRetrying:
    """Strict 429-aware retry (config-driven, see APP_CONFIG.retry)."""
    return rate_limit_retry_policy(exceptions=(GeminiRateLimitError,))


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required context file: {path}")
    return path.read_text(encoding="utf-8")


def _build_system_prompt(persona_id: str) -> str:
    # ✅ FIX: system prompt must exist (no silent empty fallback)
    sys_prompt_path = SYSTEM_PROMPTS_DIR / f"{persona_id}_system.md"
    persona_path = PERSONAS_DIR / f"{persona_id}.md"

    sys_str = _load_text(sys_prompt_path)
    persona_str = _load_text(persona_path)
    contract_str = _load_text(SHARED_CONTRACT_PATH)

    merged = f"""{sys_str}

=== PERSONA DEFINITION ===
{persona_str}

=== SHARED OUTPUT CONTRACT ===
{contract_str}

=== STRICT REMINDER ===
Output ONLY <MONOLOGUE>...</MONOLOGUE>
Exact tags, exact order, roman hinglish, numbers sacred. No JSON.
"""
    return merged


def _build_user_prompt(
    dataset: TemplateDataset,
    plan: SegmentPlan,
    visual_rules_text: str,
) -> str:
    dataset_json = json.dumps([r.model_dump() for r in dataset.rows], indent=2)

    plan_lines = []
    for spec in plan.segments:
        rule = spec.visual_rule or "No specific visual rule."
        plan_lines.append(
            f"<{spec.tag}> (Min chars: {spec.min_chars}, Max chars: {spec.max_chars})\n"
            f"  Visual context: {rule}\n"
            f"</{spec.tag}>"
        )
    plan_str = "\n".join(plan_lines)

    return f"""## TASK: WRITE THE MONOLOGUE

Template: {plan.template_name}
Persona: {plan.persona_id}

=== TEMPLATE VISUAL RULES (reference) ===
{visual_rules_text}

=== REQUIRED STRUCTURE (exact tags and limits) ===
{plan_str}

=== DATASET (facts only; do not mutate numbers) ===
{dataset_json}

Write one continuous script wrapped perfectly in <MONOLOGUE>...</MONOLOGUE>.
No preamble. No postscript. No JSON.
"""


def _build_rewrite_prompt(
    failing_segments: List[Tuple[ParsedSegment, str]],  # (Segment, Reason)
    dataset: TemplateDataset,
    plan: SegmentPlan,
    visual_rules_text: str,
) -> str:
    dataset_json = json.dumps([r.model_dump() for r in dataset.rows], indent=2)

    issues = []
    for seg, reason in failing_segments:
        issues.append(
            f"- <{seg.tag}>: {reason} (current {seg.char_count}, target {seg.target_min_chars}-{seg.target_max_chars})"
        )
    issues_str = "\n".join(issues)

    return f"""## TASK: REWRITE FAILING SEGMENTS ONLY

Rewrite ONLY the failing tags listed below.
Do NOT rewrite passing tags.
Return ONLY the rewritten tags wrapped in <MONOLOGUE>...</MONOLOGUE>.

Template: {plan.template_name}
Persona: {plan.persona_id}

=== TEMPLATE VISUAL RULES (reference) ===
{visual_rules_text}

=== FAILING TAGS ===
{issues_str}

=== DATASET ===
{dataset_json}

Output format example:
<MONOLOGUE>
<HOOK>rewritten...</HOOK>
</MONOLOGUE>
"""


async def _call_gemini(
    system_prompt: str,
    user_prompt: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> str:
    key = settings.gemini_api_key.get_secret_value()
    cfg = APP_CONFIG.llm.scripting
    model_name = cfg.model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    _gemini_headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    gen_config: dict = {"temperature": cfg.temperature}
    if cfg.max_output_tokens is not None:
        gen_config["maxOutputTokens"] = cfg.max_output_tokens

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": gen_config,
    }

    async for rate_attempt in _get_429_retry_policy():
        with rate_attempt:
            async for attempt in _get_retry_policy():
                with attempt:
                    t0 = time.perf_counter()
                    async with session.post(url, json=payload, headers=_gemini_headers) as resp:
                        elapsed = (time.perf_counter() - t0) * 1000
                        log_api_call(
                            log,
                            service="gemini.monologue",
                            status_code=resp.status,
                            retry_count=attempt.retry_state.attempt_number - 1,
                            duration_ms=elapsed,
                        )

                        if resp.status == 429:
                            log.warning("Gemini 429 rate limit hit. Backing off.")
                            track_rate_limit_hit()
                            raise GeminiRateLimitError("429 rate limit hit")

                        resp.raise_for_status()
                        data = await resp.json()

                        usage = data.get("usageMetadata", {})
                        track_gemini_call(
                            phase="scripting",
                            model=model_name,
                            prompt_tokens=usage.get("promptTokenCount", 0),
                            output_tokens=usage.get("candidatesTokenCount", 0),
                        )

                        try:
                            return data["candidates"][0]["content"]["parts"][0]["text"]
                        except (KeyError, IndexError):
                            raise ScriptGenerationError(
                                f"Malformed Gemini response structure: {str(data)[:300]}"
                            )

    raise ScriptGenerationError("Gemini call failed after retries.")


def _get_failing_segments(
    segments: Dict[str, ParsedSegment],
    plan: SegmentPlan,
) -> List[Tuple[ParsedSegment, str]]:
    failing: List[Tuple[ParsedSegment, str]] = []
    for spec in plan.segments:
        seg = segments.get(spec.tag)
        if seg is None:
            # Structural issue; treat as parsing error upstream
            raise ScriptParsingError(f"Missing parsed segment for tag '{spec.tag}'")
        if seg.char_count < spec.min_chars:
            failing.append((seg, "Too short"))
        elif seg.char_count > spec.max_chars:
            failing.append((seg, "Too long"))
    return failing


def _order_segments(segments: Dict[str, ParsedSegment], plan: SegmentPlan) -> List[ParsedSegment]:
    return [segments[spec.tag] for spec in plan.segments]


async def _run_rewrite_loop(
    initial_failing: List[Tuple[ParsedSegment, str]],
    final_segments: Dict[str, ParsedSegment],
    dataset: TemplateDataset,
    plan: SegmentPlan,
    system_prompt: str,
    visual_rules_text: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> bool:
    max_retries = 2
    current_failing = initial_failing

    for rewrite_attempt in range(max_retries):
        log.info(
            "--- Segment Rewrite Loop (Attempt %d/%d) ---",
            rewrite_attempt + 1, max_retries,
        )

        user_prompt_rewrite = _build_rewrite_prompt(current_failing, dataset, plan, visual_rules_text)
        raw_output = await _call_gemini(system_prompt, user_prompt_rewrite, session, log)

        # Extract only the rewritten tags
        for seg, _ in current_failing:
            tag_pattern = re.compile(rf"<{seg.tag}>(.*?)</{seg.tag}>", re.DOTALL | re.IGNORECASE)
            match = tag_pattern.search(raw_output)
            if match:
                text = normalize_text(match.group(1))
                final_segments[seg.tag] = ParsedSegment(
                    tag=seg.tag,
                    text=text,
                    char_count=count_chars(text),
                    target_min_chars=seg.target_min_chars,
                    target_max_chars=seg.target_max_chars,
                )
            else:
                log.warning("Rewrite response missing tag <%s>", seg.tag)

        current_failing = _get_failing_segments(final_segments, plan)
        if not current_failing:
            log.info("All failing segments fixed.")
            return True

    return False


async def write_script(
    plan: SegmentPlan,
    dataset: TemplateDataset,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> Tuple[List[ParsedSegment], str]:
    system_prompt = _build_system_prompt(plan.persona_id)
    visual_rules_text = _load_text(VISUAL_RULES_PATH)

    user_prompt_full = _build_user_prompt(dataset, plan, visual_rules_text)

    max_full_retries = 2
    final_segments: Dict[str, ParsedSegment] = {}
    # Use a list of parts to avoid O(n²) string concatenation across retries.
    history_parts: List[str] = []

    for attempt in range(max_full_retries + 1):
        log.info(
            "--- Full Monologue Generation (Attempt %d/%d) ---",
            attempt + 1, max_full_retries + 1,
        )
        raw_output = await _call_gemini(system_prompt, user_prompt_full, session, log)
        history_parts.append(f"\n\n--- Full Gen Attempt {attempt + 1} ---\n{raw_output}")

        try:
            parsed = parse_monologue(raw_output, plan)
        except ScriptParsingError as e:
            log.warning("Structural parsing failed: %s. Retrying full monologue.", e)
            continue

        for seg in parsed:
            final_segments[seg.tag] = seg

        failing = _get_failing_segments(final_segments, plan)
        if not failing:
            return _order_segments(final_segments, plan), "".join(history_parts)

        log.warning("%d segments failed length checks. Entering rewrite loop.", len(failing))
        ok = await _run_rewrite_loop(
            failing,
            final_segments,
            dataset,
            plan,
            system_prompt,
            visual_rules_text,
            session,
            log,
        )
        if ok:
            return _order_segments(final_segments, plan), "".join(history_parts)

        log.warning("Rewrite loop exhausted; retrying full monologue.")

    raise ScriptGenerationError("Exhausted all retries. Failed to generate a valid script.")