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
import time
from typing import Any

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.config import settings
from src.agents.core.logger import log_api_call
from src.agents.core.models import TopicCandidate, VALID_TEMPLATES, TEMPLATE_FALLBACKS
from src.agents.core.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class GeminiRateLimitError(Exception):
    """Raised when Gemini returns HTTP 429 Too Many Requests."""


def _get_retry_policy() -> AsyncRetrying:
    """Standard retry: 3 attempts, exponential backoff, retries on transient errors."""
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )


def _get_429_retry_policy() -> AsyncRetrying:
    """Strict 429-aware retry: waits 60s before retrying after a rate limit hit."""
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=60, min=60, max=120),
        retry=retry_if_exception_type(GeminiRateLimitError),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Gemini Structured Scoring
# ---------------------------------------------------------------------------

_SCORING_PROMPT_TEMPLATE = """You are a strict Data Analyst for AutoShorts.

You are given a raw topic candidate (title + snippet from the web).
Your job is to evaluate whether this topic can become a high-quality data-driven short video.

## Available Visual Templates
{template_list}

## Evaluation Output Format
Return a single JSON object with these exact fields:
{{
  "why_it_matters": "<short 1-2 sentence explanation of audience relevance>",
  "virality_score": <int 1-10>,
  "data_feasibility_score": <int 1-10>,
  "template_fit_score": <int 1-10>,
  "visual_potential_score": <int 1-10>,
  "source_quality_score": <int 1-10>,
  "fallback_strength_score": <int 1-10>,
  "best_fit_template": "<one of the template names above>",
  "fit_reason": "<why this template works for this topic>",
  "source_hint": "<where reliable data might come from>"
}}

## Scoring Guide
- virality_score: How likely to attract attention, clicks, curiosity. 9-10=very clickable, 1-2=boring.
- data_feasibility_score: How likely usable numerical/structured data exists. 9-10=easy to find, 1-2=impossible.
- template_fit_score: How naturally the topic fits the best template. 9-10=obvious fit, 1-2=forced fit.
- visual_potential_score: Will the final output look visually strong. 9-10=beautiful, 1-2=ugly.
- source_quality_score: How trustworthy the likely sources are. 9-10=authoritative, 1-2=unreliable.
- fallback_strength_score: If the best template fails, is there a strong second option. 9-10=strong fallback, 1-2=none.

## Rules
- Do NOT inflate scores just because a topic seems exciting.
- Do NOT give high data_feasibility if you cannot imagine a real data source.
- Do NOT give high template_fit if the topic is forced into the template.
- Return pure JSON only. No markdown wrapping. No commentary before or after.

## Topic to Evaluate

Title: {title}
Snippet: {snippet}
"""


def _build_template_list() -> str:
    """Build a human-readable template list for the LLM prompt."""
    lines = []
    for t in sorted(VALID_TEMPLATES):
        fallbacks = TEMPLATE_FALLBACKS.get(t, [])
        fb_str = ", ".join(fallbacks) if fallbacks else "none"
        lines.append(f"- {t} (fallbacks: {fb_str})")
    return "\n".join(lines)


import re

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

    # Extract and clamp scores
    virality = _safe_parse_score(data.get("virality_score"), "virality_score")
    data_feas = _safe_parse_score(data.get("data_feasibility_score"), "data_feasibility_score")
    template_fit = _safe_parse_score(data.get("template_fit_score"), "template_fit_score")
    visual_pot = _safe_parse_score(data.get("visual_potential_score"), "visual_potential_score")
    source_qual = _safe_parse_score(data.get("source_quality_score"), "source_quality_score")
    fb_strength = _safe_parse_score(data.get("fallback_strength_score"), "fallback_strength_score")

    # Option B: Python strictly assumes ownership of fallback_template
    # Prompt asks only for best_fit_template.
    best_fit = str(data.get("best_fit_template", "")).strip()

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
        why_it_matters=str(data.get("why_it_matters", "")),
        virality_score=virality,
        data_feasibility_score=data_feas,
        template_fit_score=template_fit,
        visual_potential_score=visual_pot,
        source_quality_score=source_qual,
        fallback_strength_score=fb_strength,
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
    model_name = settings.gemini_model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent?key={key}"
    )

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
            "temperature": 0.1,
            "maxOutputTokens": 1000,
        },
    }

    async for rate_attempt in _get_429_retry_policy():
        with rate_attempt:
            async for attempt in _get_retry_policy():
                with attempt:
                    t0 = time.perf_counter()
                    async with session.post(url, json=payload) as resp:
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
                            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        except (KeyError, IndexError):
                            log.error("Malformed Gemini response for '%s': %s", title, data)
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
    limiter = TokenBucketRateLimiter(rpm=settings.gemini_rpm_limit)

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
