"""
AutoShorts Phase 2 Scripting — LLM Writer
==========================================
Coordinates the construction of system & user prompts, calls the LLM to fetch
the script monologue, and implements the structural/length retry rules.

Output is XML, not JSON — deliberately. Structured Outputs could guarantee the
exact tags in the exact order, but models write measurably differently inside
JSON string values (flatter register, escaped quotes, less rhythm), and the
voice IS the product.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

import aiohttp
from tenacity import AsyncRetrying

from src.agents.core.config import APP_CONFIG, PhaseModel
from src.agents.core.llm_client import call_llm
from src.agents.core.llm_errors import LLMError
from src.agents.core.retry import standard_retry_policy, rate_limit_retry_policy
from src.agents.core.job_manager import PROJECT_ROOT
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

# Rough chars→words heuristic for roman Hinglish (avg word + trailing space ≈ 6
# chars). Used ONLY to translate Python-measured char counts/deltas into
# word-level guidance the model can actually act on — LLMs cannot count
# characters, but they estimate word counts reasonably well.
_CHARS_PER_WORD = 6.0


def _approx_words(chars: int) -> int:
    """Translate a character count into an approximate word count (min 1)."""
    return max(1, round(chars / _CHARS_PER_WORD))


def _get_retry_policy() -> AsyncRetrying:
    """Patient transient-error retry for the Phase 2 monologue calls.

    Phase 2 fires several sequential LLM calls (draft + rewrites + doctor); a
    transient 503 burst on any one used to kill the whole phase under the default
    3-attempt profile. Use the patient ``scripting_*`` profile (mirrors Phase 1
    extraction) so short provider blips are ridden out instead of failing the run.
    """
    rc = APP_CONFIG.retry
    return standard_retry_policy(
        min_wait=rc.scripting_min_wait,
        max_wait=rc.scripting_max_wait,
        max_attempts=rc.scripting_max_attempts,
    )


def _get_429_retry_policy() -> AsyncRetrying:
    """Strict 429-aware retry (config-driven, see APP_CONFIG.retry)."""
    return rate_limit_retry_policy()


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
        # Anchor on a single TARGET (the window midpoint), not the [min, max]
        # range. Given a range, models chase the top edge and then overshoot it
        # (observed ~13% over the ceiling). Given one target stated in WORDS
        # (which they estimate far better than characters) they land inside the
        # window; the ceiling is restated as a hard, do-not-cross limit.
        target_chars = (spec.min_chars + spec.max_chars) // 2
        plan_lines.append(
            f"<{spec.tag}> TARGET ~{_approx_words(target_chars)} words (~{target_chars} chars). "
            f"HARD CEILING {spec.max_chars} chars — NEVER exceed. Floor {spec.min_chars} chars.\n"
            f"  Visual context: {rule}\n"
            f"</{spec.tag}>"
        )
    plan_str = "\n".join(plan_lines)

    return f"""## TASK: WRITE THE MONOLOGUE

Template: {plan.template_name}
Persona: {plan.persona_id}

{commentary_block}{topic_block}=== REQUIRED STRUCTURE (exact tags, limits, and per-segment visual context) ===
{plan_str}

=== LENGTH DISCIPLINE (critical) ===
Hit each segment's TARGET length — do NOT drift up toward the ceiling. Any segment longer than its
HARD CEILING is rejected and the whole take is regenerated. A tight, punchy line at the target beats
a long, padded one. Count by WORDS as you write and keep every segment at its stated target.

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

    # Give the model a Python-MEASURED, actionable instruction (cut/add N words to
    # reach the midpoint) instead of a raw range it has to re-count itself. Python
    # owns the counting; the model only performs the edit. Aiming at the midpoint
    # (not the just-passing edge) leaves headroom so the rewrite lands inside.
    issues = []
    for seg, reason in failing_segments:
        target_mid = (seg.target_min_chars + seg.target_max_chars) // 2
        if seg.char_count > seg.target_max_chars:
            delta_words = _approx_words(seg.char_count - target_mid)
            issues.append(
                f"- <{seg.tag}>: TOO LONG by {seg.char_count - seg.target_max_chars} chars. "
                f"Cut about {delta_words} word(s) — drop a clause or adjective, do NOT just shave "
                f"letters — to land near ~{target_mid} chars (ceiling {seg.target_max_chars})."
            )
        else:
            delta_words = _approx_words(target_mid - seg.char_count)
            issues.append(
                f"- <{seg.tag}>: TOO SHORT by {seg.target_min_chars - seg.char_count} chars. "
                f"Add about {delta_words} word(s) — one concrete detail, not filler — to land near "
                f"~{target_mid} chars (floor {seg.target_min_chars})."
            )
    issues_str = "\n".join(issues)

    return f"""## TASK: REWRITE FAILING SEGMENTS ONLY

Rewrite ONLY the failing tags listed below.
Do NOT rewrite passing tags.
Return ONLY the rewritten tags wrapped in <MONOLOGUE>...</MONOLOGUE>.

Adjust LENGTH only, by exactly the word amount stated per tag. Keep each line natural, spoken, and
connected to its neighbours — a complete spoken unit, never a dangling fragment. Do NOT strip it into
a robotic stub or pad it with filler just to hit the count. Numbers stay exactly the same (spoken
form is fine).

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


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    phase_model: PhaseModel,
    cost_phase: str,
    cache_key: str | None = None,
) -> str:
    """Phase 2's LLM entry point.

    Binds the patient ``scripting_*`` retry profile plus the 429 policy, and
    funnels every provider-level failure into ``ScriptGenerationError`` — which
    is the exception the whole repair/regeneration machinery above is written
    against. Transport errors still propagate untouched to the retry policy.
    """
    try:
        return await call_llm(
            system_prompt,
            user_prompt,
            session,
            log,
            phase_model,
            cost_phase,
            retry_policy=_get_retry_policy,
            rate_limit_policy=_get_429_retry_policy,
            service_tag="llm.monologue",
            # The ~3.5K-token persona system prompt is byte-identical across the
            # draft, every rewrite round and the doctor (~5 calls/run), so the
            # cache prefix is reused at ~10% of the input rate. The key only
            # improves routing consistency; caching itself is automatic.
            cache_key=cache_key,
        )
    except LLMError as exc:
        raise ScriptGenerationError(f"{cost_phase} call failed: {exc}") from exc


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
    # 3 rounds (was 2): each round re-sends ONLY the still-failing segments, so the
    # set shrinks every round and the extra round cheaply catches the long tail when
    # many segments miss at once (e.g. a 7-card sort_card with 9+ initial misses).
    max_retries = 3
    current_failing = initial_failing

    for rewrite_attempt in range(max_retries):
        log.info(
            "--- Segment Rewrite Loop (Attempt %d/%d) ---",
            rewrite_attempt + 1, max_retries,
        )

        user_prompt_rewrite = _build_rewrite_prompt(current_failing, dataset, plan)
        raw_output = await _call_llm(
            system_prompt, user_prompt_rewrite, session, log,
            APP_CONFIG.llm.scripting_rewrite, "scripting_rewrite",
            cache_key=f"as-p2-{plan.persona_id}",
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
        raw_output = await _call_llm(
            system_prompt, user_prompt, session, log,
            APP_CONFIG.llm.scripting_doctor, "scripting_doctor",
            cache_key=f"as-p2-{plan.persona_id}",
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
        raw_output = await _call_llm(
            system_prompt, user_prompt_full, session, log,
            APP_CONFIG.llm.scripting_draft, "scripting_draft",
            cache_key=f"as-p2-{plan.persona_id}",
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

        # DIAGNOSTIC: per-segment breakdown so we can see whether segments are
        # missing on the MIN side (too short) or MAX side (too long) — this tells
        # us if the persona writes terse (below floor) vs the windows being too
        # tight. Safe to remove once tuning is locked.
        for _seg, _reason in failing:
            log.warning(
                "  length miss: <%s> %s — got %d chars, allowed window %d-%d",
                _seg.tag, _reason, _seg.char_count,
                _seg.target_min_chars, _seg.target_max_chars,
            )
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