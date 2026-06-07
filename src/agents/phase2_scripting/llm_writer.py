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

from src.agents.core.config import settings, APP_CONFIG, PhaseModel
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
from src.agents.phase2_scripting.num_normalizer import build_number_reference
from src.agents.phase2_scripting.xml_parser import parse_monologue

logger = logging.getLogger(__name__)

# Constants & Paths
CONTEXT_DIR = PROJECT_ROOT / ".agent" / "context"
PERSONAS_DIR = CONTEXT_DIR / "personas"
SYSTEM_PROMPTS_DIR = PERSONAS_DIR / "system_prompt"   # canonical — matches runner.py hash

SHARED_CONTRACT_PATH = PERSONAS_DIR / "shared_output_contract.md"
SCRIPTCRAFT_PATH = PERSONAS_DIR / "voice_and_scriptcraft.md"
VISUAL_RULES_PATH = CONTEXT_DIR / "template_visual_rules.md"
COMMENTARY_MODE_PATH = CONTEXT_DIR / "commentary_mode.md"

# Templates whose visual is ONE continuous animation (not discrete per-row beats). They get a
# live-commentary override so the script flows as one broadcast, not per-entity bullet points.
CONTINUOUS_TEMPLATES = {"scan_race"}


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
    scriptcraft_str = _load_text(SCRIPTCRAFT_PATH)

    merged = f"""=== VOICE & SCRIPTCRAFT (universal craft — read first) ===
{scriptcraft_str}

=== PERSONA SYSTEM PROMPT ===
{sys_str}

=== PERSONA DEFINITION ===
{persona_str}

=== SHARED OUTPUT CONTRACT ===
{contract_str}

=== STRICT REMINDER ===
Output ONLY <MONOLOGUE>...</MONOLOGUE>
Exact tags, exact order, roman hinglish. Numbers SACRED — copy spoken forms from NUMBER REFERENCE verbatim; never re-translate. No JSON.
ZERO YAPPING: no markdown fences (no ```), no pre-text, no post-text, no explanations. First character `<`, last character `>`.
"""
    return merged


def _topic_block(dataset: TemplateDataset) -> str:
    """`TOPIC / WHAT THIS IS ABOUT` block from dataset.meta (TITLE/SUB/METRIC/UNIT). Empty if none.

    Without this the model narrates bare {name, value} pairs blind, and the doctor can hallucinate
    facts (e.g. inventing a 'market fragmented' conclusion on a savings-rate dataset).
    """
    meta = getattr(dataset, "meta", None) or {}
    meta_lines = "\n".join(f"- {k}: {v}" for k, v in meta.items() if str(v).strip())
    if not meta_lines:
        return ""
    unit_hint = ""
    if not any(k in meta for k in ("UNIT", "METRIC")):
        unit_hint = "- Each numeric value means what TITLE/SUB says. Do NOT invent a different real-world activity or metric.\n"
    return f"=== TOPIC / WHAT THIS IS ABOUT ===\n{meta_lines}\n{unit_hint}\n"


def _commentary_block(template_name: str) -> str:
    """Live-commentary OVERRIDE block for continuous templates (e.g. scan_race). Empty otherwise.

    Continuous templates (one fluid background animation) shouldn't be narrated row-by-row; this
    block tells the model to call the event like a live sports commentator instead.
    """
    if template_name not in CONTINUOUS_TEMPLATES or not COMMENTARY_MODE_PATH.exists():
        return ""
    return (
        "=== COMMENTARY MODE (OVERRIDE — read before writing) ===\n"
        f"{COMMENTARY_MODE_PATH.read_text(encoding='utf-8')}\n\n"
    )


def _build_user_prompt(
    dataset: TemplateDataset,
    plan: SegmentPlan,
) -> str:
    dataset_json = json.dumps([r.model_dump() for r in dataset.rows], indent=2)
    topic_block = _topic_block(dataset)
    commentary_block = _commentary_block(plan.template_name)
    number_ref = build_number_reference(dataset)

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

{commentary_block}{topic_block}=== REQUIRED STRUCTURE (exact tags, limits, and per-segment visual context) ===
{plan_str}

{number_ref}=== DATASET (facts only; do not mutate numbers) ===
{dataset_json}

Write one continuous script wrapped perfectly in <MONOLOGUE>...</MONOLOGUE>.
No preamble. No postscript. No JSON.
"""


def _build_rewrite_prompt(
    failing_segments: List[Tuple[ParsedSegment, str]],  # (Segment, Reason)
    dataset: TemplateDataset,
    plan: SegmentPlan,
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

Adjust LENGTH only. Keep each line natural, spoken, and connected to its neighbours — a complete
spoken unit, never a dangling fragment. Do NOT strip it into a robotic stub or pad it with filler
just to hit the count. Numbers stay exactly the same (spoken form is fine).

Template: {plan.template_name}
Persona: {plan.persona_id}

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
    phase_model: PhaseModel,
    cost_phase: str,
) -> str:
    key = settings.gemini_api_key.get_secret_value()
    cfg = phase_model
    model_name = cfg.model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    _gemini_headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    gen_config: dict = {"temperature": cfg.temperature}
    if cfg.max_output_tokens is not None:
        gen_config["maxOutputTokens"] = cfg.max_output_tokens
    if cfg.thinking_budget is not None:
        # Cap (or disable, budget=0 on Flash) the reasoning tokens billed at the output rate.
        gen_config["thinkingConfig"] = {"thinkingBudget": cfg.thinking_budget}

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
                            phase=cost_phase,
                            model=model_name,
                            prompt_tokens=usage.get("promptTokenCount", 0),
                            output_tokens=usage.get("candidatesTokenCount", 0),
                            thinking_tokens=usage.get("thoughtsTokenCount", 0),
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

        user_prompt_rewrite = _build_rewrite_prompt(current_failing, dataset, plan)
        raw_output = await _call_gemini(
            system_prompt, user_prompt_rewrite, session, log,
            APP_CONFIG.llm.scripting_rewrite, "scripting_rewrite",
        )

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


_DIGITS_RE = re.compile(r"\d+")


def _numbers_preserved(
    before: Dict[str, ParsedSegment],
    after: Dict[str, ParsedSegment],
    plan: SegmentPlan,
) -> bool:
    """Guard for the script-doctor: every numeric token in each segment must survive unchanged.

    Compares the multiset of digit-runs per segment. Segments with no digits are skipped (nothing
    numeric to protect). The doctor is told to keep numbers written exactly as-is, so a spoken-form
    conversion ("95" -> "ninety-five") counts as drift and is rejected.
    """
    for spec in plan.segments:
        b = before.get(spec.tag)
        a = after.get(spec.tag)
        if b is None or a is None:
            return False
        b_nums = sorted(_DIGITS_RE.findall(b.text))
        if not b_nums:
            continue
        if b_nums != sorted(_DIGITS_RE.findall(a.text)):
            return False
    return True


_DANGLING_WORDS = {"lekin", "aur", "par", "jahan", "jaise", "yaani", "toh", "ki", "ya", "kyunki"}


def _ends_dangling(text: str) -> bool:
    """True if a segment ends on a trailing ellipsis or a dangling conjunction (incomplete unit)."""
    t = text.strip()
    if t.endswith("...") or t.endswith("…"):
        return True
    words = re.findall(r"[A-Za-z]+", t)
    return bool(words) and words[-1].lower() in _DANGLING_WORDS


def _no_dangling_endings(segments: Dict[str, ParsedSegment], plan: SegmentPlan) -> bool:
    """True if NO segment ends on a dangling conjunction / ellipsis (doctor acceptance guard)."""
    for spec in plan.segments:
        seg = segments.get(spec.tag)
        if seg is None or _ends_dangling(seg.text):
            return False
    return True


def _build_doctor_prompt(
    ordered_segments: List[ParsedSegment],
    plan: SegmentPlan,
    dataset: TemplateDataset,
) -> str:
    current_lines = []
    for seg in ordered_segments:
        current_lines.append(
            f"<{seg.tag}>  (keep within {seg.target_min_chars}-{seg.target_max_chars} chars)\n"
            f"{seg.text}\n"
            f"</{seg.tag}>"
        )
    current_block = "\n".join(current_lines)

    topic_block = _topic_block(dataset)
    commentary_block = _commentary_block(plan.template_name)
    dataset_json = json.dumps([r.model_dump() for r in dataset.rows], indent=2)

    return f"""## TASK: PERFORMANCE DOCTOR — rewrite this into a vivid, in-character spoken performance

This is a near-final voiceover script. ELEVATE it — do not just smooth or shorten it:
- Fully ADOPT the persona's voice, attitude, and rhythm (the persona + lexicon are in the system prompt).
- ENHANCE the storytelling and engagement; make every line land and pull the listener to the next.
- ERADICATE repetitive patterns — do NOT let every segment follow the same "[name] [number], [gap
  small]" shape. Vary the openings and the sentence shapes across segments.
It will be spoken VERBATIM by a TTS voice.

HARD CONSTRAINTS (violate any -> your output is discarded and the original is kept):
- Keep the EXACT same tags in the EXACT same order. Each segment within its stated char range.
- Keep every NUMBER exactly as it appears (same digits/words). Do NOT invent, drop, round, or move numbers.
- Stay TRUE TO THE TOPIC / DATA below — do NOT invent facts, entities, or conclusions it doesn't support.
- Each segment is a COMPLETE spoken unit ending in a full stop. NEVER end a segment on a dangling
  conjunction ("lekin", "aur", "par", "jahan", "jaise", "yaani", "toh") or a trailing "...".
  Connect segments by MEANING (contrast, callback, escalation), not by leaving a sentence unfinished.
- Roman Hinglish only.

{commentary_block}{topic_block}=== DATASET (facts only; do not contradict) ===
{dataset_json}

Template: {plan.template_name}    Persona: {plan.persona_id}

=== CURRENT SCRIPT (improve every line; keep tags, order, and numbers) ===
{current_block}

Return ONLY the <MONOLOGUE>...</MONOLOGUE> block — same tags, same order. NO ``` fences, NO "Here is",
NO notes or explanations. First character `<`, last character `>`.
"""


async def _run_script_doctor(
    final_segments: Dict[str, ParsedSegment],
    plan: SegmentPlan,
    dataset: TemplateDataset,
    system_prompt: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> Tuple[Dict[str, ParsedSegment], str]:
    """Final whole-script performance pass. Sees ALL segments + the topic/dataset at once and
    rewrites them into one vivid, in-character performance. Returns (segments, audit_note). Falls
    back to the input segments on ANY violation (parse failure, out-of-budget, number drift, or a
    dangling conjunction) — it never worsens the script.
    """
    ordered = _order_segments(final_segments, plan)
    user_prompt = _build_doctor_prompt(ordered, plan, dataset)

    try:
        raw_output = await _call_gemini(
            system_prompt, user_prompt, session, log,
            APP_CONFIG.llm.scripting_doctor, "scripting_doctor",
        )
    except ScriptGenerationError as e:
        log.warning("Script-doctor call failed (%s). Keeping pre-doctor script.", e)
        return final_segments, f"\n\n--- Script Doctor (call failed: {e}) ---"

    note = f"\n\n--- Script Doctor (flow pass) ---\n{raw_output}"

    try:
        parsed = parse_monologue(raw_output, plan)
    except ScriptParsingError as e:
        log.warning("Script-doctor parse failed (%s). Keeping pre-doctor script.", e)
        return final_segments, note + "\n[DISCARDED: parse failure]"

    polished: Dict[str, ParsedSegment] = {seg.tag: seg for seg in parsed}

    try:
        failing = _get_failing_segments(polished, plan)
    except ScriptParsingError as e:
        log.warning("Script-doctor missing tags (%s). Keeping pre-doctor script.", e)
        return final_segments, note + "\n[DISCARDED: missing tags]"

    if failing:
        log.warning(
            "Script-doctor produced %d out-of-budget segment(s). Keeping pre-doctor script.",
            len(failing),
        )
        return final_segments, note + "\n[DISCARDED: out of budget]"

    if not _numbers_preserved(final_segments, polished, plan):
        log.warning("Script-doctor altered numbers. Keeping pre-doctor script.")
        return final_segments, note + "\n[DISCARDED: number drift]"

    if not _no_dangling_endings(polished, plan):
        log.warning("Script-doctor left a dangling conjunction. Keeping pre-doctor script.")
        return final_segments, note + "\n[DISCARDED: dangling conjunction]"

    log.info("Script-doctor performance pass applied.")
    return polished, note + "\n[APPLIED]"


async def write_script(
    plan: SegmentPlan,
    dataset: TemplateDataset,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> Tuple[List[ParsedSegment], str]:
    system_prompt = _build_system_prompt(plan.persona_id)
    user_prompt_full = _build_user_prompt(dataset, plan)

    max_full_retries = 2
    final_segments: Dict[str, ParsedSegment] = {}
    # Use a list of parts to avoid O(n²) string concatenation across retries.
    history_parts: List[str] = []

    async def _finalize() -> Tuple[List[ParsedSegment], str]:
        """Optionally run the whole-script flow doctor, then return ordered segments + audit."""
        segs = final_segments
        if APP_CONFIG.script_doctor_enabled:
            segs, doc_note = await _run_script_doctor(
                final_segments, plan, dataset, system_prompt, session, log
            )
            history_parts.append(doc_note)
        return _order_segments(segs, plan), "".join(history_parts)

    for attempt in range(max_full_retries + 1):
        log.info(
            "--- Full Monologue Generation (Attempt %d/%d) ---",
            attempt + 1, max_full_retries + 1,
        )
        raw_output = await _call_gemini(
            system_prompt, user_prompt_full, session, log,
            APP_CONFIG.llm.scripting_draft, "scripting_draft",
        )
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
            return await _finalize()

        log.warning("%d segments failed length checks. Entering rewrite loop.", len(failing))
        ok = await _run_rewrite_loop(
            failing,
            final_segments,
            dataset,
            plan,
            system_prompt,
            session,
            log,
        )
        if ok:
            return await _finalize()

        log.warning("Rewrite loop exhausted; retrying full monologue.")

    raise ScriptGenerationError("Exhausted all retries. Failed to generate a valid script.")