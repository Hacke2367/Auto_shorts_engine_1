"""
AutoShorts Phase 1A — Candidate Scoring & Template Assignment
=============================================================
Replaces boolean-only qualification with structured Gemini scoring.

Design Principles:
  - Gemini provides sub-scores and reasoning as structured JSON.
  - Python computes the deterministic weighted final score.
  - Best-fit + fallback templates assigned from TEMPLATE_FALLBACKS.
  - Malformed LLM output never crashes the batch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.config import settings, APP_CONFIG
from src.agents.core.retry import standard_retry_policy, rate_limit_retry_policy
from src.agents.core.logger import log_api_call
from src.agents.core.models import TopicCandidate, VALID_TEMPLATES, TEMPLATE_FALLBACKS
from src.agents.core.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class GeminiRateLimitError(Exception):
    """Raised when Gemini returns HTTP 429 Too Many Requests."""


def _get_retry_policy() -> AsyncRetrying:
    """Standard transient-error retry (config-driven, see APP_CONFIG.retry)."""
    return standard_retry_policy()


def _get_429_retry_policy() -> AsyncRetrying:
    """Strict 429-aware retry (config-driven, see APP_CONFIG.retry)."""
    return rate_limit_retry_policy(exceptions=(GeminiRateLimitError,))


# ---------------------------------------------------------------------------
# Gemini Structured Scoring
# ---------------------------------------------------------------------------

_SCORING_PROMPT_TEMPLATE = """You are the Lead Quality Assurer for AutoShorts.

You are evaluating a proposed topic hypothesis and its validated search evidence.
Your job is to strictly grade if this is a premium, highly engaging short-form video concept.

## Available Visual Templates
{template_list}

## Evaluation Output Format
Return a single JSON object with these exact fields:
{{
  "rationale": "<deep 1-2 sentence breakdown of why this topic is highly interesting or novel>",
  "validation_confidence": "<high|medium|low - based on if the evidence proves data is actually buildable>",
  "hook_potential_score": <int 1-10>,
  "novelty_score": <int 1-10>,
  "visual_fit_score": <int 1-10>,
  "data_feasibility_score": <int 1-10>,
  "freshness_score": <int 1-10>,
  "best_fit_template": "<one of the template names above>",
  "fit_reason": "<why this template visually suits the data>",
  "source_hint": "<where reliable data likely comes from based on evidence>"
}}

## Scoring Guide
- hook_potential_score: Does the title naturally stop the scroll? 9-10=Instant curiosity, 1-2=Boring.
- novelty_score: Is this a unique angle or overdone? 9-10=Fresh/surprising, 1-2=Cliché.
- visual_fit_score: How beautifully does this map into the chosen template? 9-10=Perfect translation, 1-2=Forced.
- data_feasibility_score: Does a SINGLE published source already hold this as a ready-to-extract table, ranking, or list? Grade only what the evidence PROVES exists — never what could theoretically be assembled. 9-10=A pre-compiled table or ranking is provably present in the evidence. 5-6=Real figures exist but lie scattered across prose and would need manual assembly. 1-3=No structured data is shown, OR the metric is derived (see below).
- freshness_score: Is this incredibly timely/relevant right now? 9-10=Trending today, 1-2=Outdated content.

## The Derived-Metric Trap — read before grading data_feasibility
A metric is "derived" when NO single source publishes it directly, and producing it would demand joining two or more independent datasets or computing a ratio, per-unit, average, or composite figure. Tell-tale phrasing: "per", "ratio", "vs", "adjusted for", "relative to", "ROI", "average X across Y".
- The raw ingredients existing separately is IRRELEVANT. If no single source publishes the FINAL computed metric as a structured table, the data is NOT feasibly extractable.
- The absence of a pre-compiled table for a derived metric is positive evidence that the underlying join is ill-defined. Treat it as a red flag, never a gap for the pipeline to fill.
- For ANY derived metric where the evidence does not show a single source already publishing the computed result, data_feasibility_score MUST be <= 3.

## Rules
- Do NOT inflate scores for boring corporate data unless it has a viral angle.
- A magnetic hook NEVER rescues weak feasibility — an un-buildable topic is worthless no matter how viral it sounds. Score the two axes independently.
- If data_feasibility_score is < 5, validation_confidence MUST be low.
- Return pure JSON only. No markdown formatting wraps.

## Hypothesis & Evidence
Topic: {title}
Evidence: 
{snippet}
"""


def _build_template_list() -> str:
    """Build a human-readable template list for the LLM prompt."""
    lines = []
    for t in sorted(VALID_TEMPLATES):
        fallbacks = TEMPLATE_FALLBACKS.get(t, [])
        fb_str = ", ".join(fallbacks) if fallbacks else "none"
        lines.append(f"- {t} (fallbacks: {fb_str})")
    return "\n".join(lines)


def _strip_markdown_json(raw: str) -> str:
    """Robustly extract the first top-level JSON object using a brace parser."""
    start_idx = raw.find("{")
    if start_idx == -1:
        return raw.strip()
        
    brace_count = 0
    in_string = False
    escape = False
    
    for i in range(start_idx, len(raw)):
        char = raw[i]
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return raw[start_idx:i+1]
                    
    # Fallback if unbalanced
    return raw.strip()


def _safe_parse_score(raw: Any, field: str, default: float = 5.0) -> float:
    """Safely coerce a score value to float within [1, 10]."""
    try:
        val = float(raw)
        return max(1.0, min(10.0, val))
    except (TypeError, ValueError):
        logger.warning("Invalid %s value: %r. Defaulting to %.1f.", field, raw, default)
        return default


def _parse_scoring_response(
    raw_json: str, topic_title: str, snippet: str
) -> TopicCandidate | None:
    """Parse Gemini's structured scoring response into a TopicCandidate.

    Returns None if the response is fundamentally unparseable.
    """
    text = _strip_markdown_json(raw_json)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(
            "JSON parse failed for topic '%s': %s\nRaw: %s",
            topic_title, e, text[:500],
        )
        return None

    if not isinstance(data, dict):
        logger.error("Expected dict, got %s for topic '%s'.", type(data).__name__, topic_title)
        return None

    # Extract and clamp ideation-first scores
    hook = _safe_parse_score(data.get("hook_potential_score"), "hook_potential_score")
    novelty = _safe_parse_score(data.get("novelty_score"), "novelty_score")
    vfit = _safe_parse_score(data.get("visual_fit_score"), "visual_fit_score")
    data_feas = _safe_parse_score(data.get("data_feasibility_score"), "data_feasibility_score")
    freshness = _safe_parse_score(data.get("freshness_score"), "freshness_score")

    # Option B: Python strictly assumes ownership of fallback_template
    # Prompt asks only for best_fit_template.
    best_fit = str(data.get("best_fit_template", "")).strip().lower()

    if best_fit not in VALID_TEMPLATES:
        # Deterministic rejection: if best_fit doesn't exist, we do not guess
        logger.warning(
            "LLM returned invalid best_fit_template '%s' for '%s'. Discarding candidate.",
            best_fit, topic_title,
        )
        return None

    # Compute fallback purely in Python based on the valid best_fit
    fallbacks = TEMPLATE_FALLBACKS.get(best_fit, [])
    fallback = fallbacks[0] if fallbacks else None

    # Cheap normalization without depending on ArchiveManager directly
    norm = topic_title.lower().strip()
    norm = re.sub(r"\s+", " ", norm)

    candidate = TopicCandidate(
        topic=topic_title,
        normalized_topic=norm,
        why_it_matters=str(data.get("rationale", "")),
        rationale=str(data.get("rationale", "")),
        validation_confidence=str(data.get("validation_confidence", "low")).lower().strip(),
        # Rich idea-first metrics
        hook_potential_score=hook,
        novelty_score=novelty,
        visual_fit_score=vfit,
        data_feasibility_score=data_feas,
        freshness_score=freshness,
        # Legacy mapping to support sorting ties safely
        virality_score=hook,
        template_fit_score=vfit,
        visual_potential_score=vfit,
        source_quality_score=novelty,
        fallback_strength_score=freshness,
        
        best_fit_template=best_fit,
        fallback_template=fallback,
        fit_reason=str(data.get("fit_reason", "")),
        source_hint=data.get("source_hint"),
        candidate_sources=[],
    )

    # Compute deterministic weighted final score in Python
    candidate.compute_final_score()
    return candidate


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def score_single_candidate(
    title: str,
    snippet: str,
    session: aiohttp.ClientSession,
    limiter: TokenBucketRateLimiter,
    log: logging.Logger,
) -> TopicCandidate | None:
    """Score a single raw candidate via Gemini structured assessment.

    Uses a two-layer retry strategy:
      - Outer loop: catches HTTP 429 with a strict 60s backoff.
      - Inner loop: catches transient network errors with fast exponential backoff.

    Returns:
        A TopicCandidate with all scores computed, or None if scoring failed.
    """
    key = settings.gemini_api_key.get_secret_value()
    cfg = APP_CONFIG.llm.discovery_scoring
    model_name = cfg.model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    _gemini_headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    template_list = _build_template_list()
    prompt = _SCORING_PROMPT_TEMPLATE.format(
        template_list=template_list,
        title=title,
        snippet=snippet[:2000],
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": cfg.temperature,
            "maxOutputTokens": cfg.max_output_tokens,
        },
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
                            service="gemini.score",
                            status_code=resp.status,
                            retry_count=attempt.retry_state.attempt_number - 1,
                            duration_ms=elapsed,
                        )

                        if resp.status == 429:
                            log.warning(
                                "Gemini 429 rate-limited for '%s'. Will backoff 60s.",
                                title,
                            )
                            await limiter.apply_penalty(60.0)
                            raise GeminiRateLimitError(
                                f"429 rate limit hit for '{title}'"
                            )

                        resp.raise_for_status()
                        data = await resp.json()

                        try:
                            candidate_data = data["candidates"][0]
                            # Handle Safety or other Finish Reasons first
                            if candidate_data.get("finishReason") == "SAFETY":
                                log.warning("Gemini blocked topic '%s' due to SAFETY filters.", title)
                                return None

                            raw_text = candidate_data["content"]["parts"][0]["text"]
                        except (KeyError, IndexError):
                            log.error("Malformed or blocked Gemini response for '%s': %s", title, data)
                            return None

                        candidate = _parse_scoring_response(raw_text, title, snippet)
                        if candidate:
                            log.info(
                                "Scored '%s': final=%.2f, template=%s",
                                title, candidate.final_score, candidate.best_fit_template,
                            )
                        return candidate

    log.error("Exhausted all retries scoring '%s'.", title)
    return None


async def score_candidates_batch(
    raw_candidates: list[dict[str, str]],
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_concurrency: int = 5,
) -> list[TopicCandidate]:
    """Score a batch of raw candidates concurrently with strict RPM limits.

    Args:
        raw_candidates: list of dicts with 'title' and 'snippet' keys.
        session: Active aiohttp session.
        log: Logger.
        max_concurrency: Max parallel Gemini calls.

    Returns:
        List of successfully scored TopicCandidate objects.
    """
    sem = asyncio.Semaphore(max_concurrency)
    limiter = TokenBucketRateLimiter(rpm=APP_CONFIG.llm.rpm_limit)

    async def _score_wrapped(c: dict[str, str]) -> TopicCandidate | None:
        # Acquire time-based quota token *before* entering the concurrency limit
        # This prevents locking the concurrency pool while just waiting for an RPM token.
        await limiter.acquire()
        
        async with sem:
            return await score_single_candidate(
                title=c.get("title", ""),
                snippet=c.get("snippet", ""),
                session=session,
                log=log,
                limiter=limiter,
            )

    log.info("Scoring %d candidates (max concurrency=%d)...", len(raw_candidates), max_concurrency)
    tasks = [_score_wrapped(c) for c in raw_candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_candidates: list[TopicCandidate] = []
    for idx, r in enumerate(results):
        if isinstance(r, TopicCandidate):
            valid_candidates.append(r)
        elif isinstance(r, Exception):
            log.error("Batch scoring failed for candidate %d: %s", idx, r, exc_info=True)
        # else: result was None, already logged by score_single_candidate if it failed internally

    log.info(
        "Scoring complete: %d/%d candidates scored successfully.",
        len(valid_candidates), len(raw_candidates),
    )
    return valid_candidates
