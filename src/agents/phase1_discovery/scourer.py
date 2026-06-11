"""
AutoShorts Phase 1A — The Scouring Engine (Idea-First Validator)
================================================================
Validates topic hypotheses using targeted search to gather evidence.

Design Principles:
  - Takes specific topic hypotheses (ideas).
  - Uses Tavily to validate if data/evidence exists for the hypothesis.
  - Returns raw candidate snippets for downstream scoring.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.config import settings, APP_CONFIG
from src.agents.core.retry import standard_retry_policy
from src.agents.core.logger import log_api_call

logger = logging.getLogger(__name__)


def _get_retry_policy() -> AsyncRetrying:
    """Standard transient-error retry (config-driven, see APP_CONFIG.retry)."""
    return standard_retry_policy()


async def fetch_trending_context(
    niche_hint: str | None,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_results: int = 6,
    request_timeout: float = APP_CONFIG.api_timeout_seconds,
) -> str:
    """Fetch a condensed snapshot of what is CURRENTLY trending in the niche.

    Runs a single broad Tavily *news* search so ideation can brainstorm from live
    signals instead of stale model memory. This is an ENHANCEMENT, not a hard
    dependency: ANY failure returns "" and ideation proceeds on model knowledge
    alone — trend-seeding must never be able to break a discovery run.
    """
    topic_hint = niche_hint or "business technology finance"
    now = datetime.now(timezone.utc)
    query = f"latest trending {topic_hint} news and developments {now.strftime('%B %Y')}"

    payload = {
        "api_key": settings.tavily_api_key.get_secret_value(),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_raw_content": False,
        "topic": "news",   # biases toward recent/timely results
        "days": 21,
    }
    per_req_timeout = aiohttp.ClientTimeout(total=request_timeout)

    try:
        async for attempt in _get_retry_policy():
            with attempt:
                t0 = time.perf_counter()
                async with session.post(
                    "https://api.tavily.com/search", json=payload, timeout=per_req_timeout
                ) as resp:
                    elapsed = (time.perf_counter() - t0) * 1000
                    log_api_call(
                        log,
                        service="tavily.search.trending",
                        status_code=resp.status,
                        retry_count=attempt.retry_state.attempt_number - 1,
                        duration_ms=elapsed,
                    )
                    resp.raise_for_status()
                    data = await resp.json()

                    headlines: list[str] = []
                    for res in data.get("results", []):
                        title = (res.get("title") or "").strip()
                        content = (res.get("content") or "").strip()
                        if not title:
                            continue
                        # Keep each line short: title + a clipped lead so ideation
                        # input stays lean (we only need a fresh signal, not articles).
                        clip = content[:160].rsplit(" ", 1)[0] if content else ""
                        headlines.append(f"- {title}" + (f" — {clip}" if clip else ""))

                    if not headlines:
                        return ""
                    log.info("Trend-seeding: fetched %d fresh headlines for ideation.", len(headlines))
                    return "\n".join(headlines[:max_results])
    except Exception as e:
        log.warning(
            "Trend-seeding search failed (%s); ideation will rely on model knowledge.", e
        )
        return ""
    return ""


async def _validate_hypothesis(
    hypothesis: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_results: int = 4,
    request_timeout: float = APP_CONFIG.api_timeout_seconds,
) -> dict[str, Any] | None:
    """Fetch evidence for a specific topic hypothesis via Tavily."""
    url = "https://api.tavily.com/search"

    # We append data-seeking terms to validate if the topic has buildable numbers
    query = f"{hypothesis} statistics data market share ranking comparison"

    payload = {
        "api_key": settings.tavily_api_key.get_secret_value(),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_raw_content": False,
        "topic": "general",
    }

    per_req_timeout = aiohttp.ClientTimeout(total=request_timeout)

    async for attempt in _get_retry_policy():
        with attempt:
            t0 = time.perf_counter()
            async with session.post(url, json=payload, timeout=per_req_timeout) as resp:
                elapsed = (time.perf_counter() - t0) * 1000
                log_api_call(
                    log,
                    service="tavily.search.validate",
                    status_code=resp.status,
                    retry_count=attempt.retry_state.attempt_number - 1,
                    duration_ms=elapsed,
                )
                resp.raise_for_status()
                data = await resp.json()

                snippets = []
                urls = []
                for res in data.get("results", []):
                    title = (res.get("title") or "").strip()
                    content = (res.get("content") or "").strip()
                    source_url = (res.get("url") or "").strip()
                    
                    if content:
                        snippets.append(f"Source: {title}\n{content}")
                        if source_url:
                            urls.append(source_url)

                if not snippets:
                    log.debug("No evidence found for hypothesis: '%s'", hypothesis)
                    return None

                # Combine the snippets into one pool of evidence
                combined_snippet = "\n\n".join(snippets)
                
                log.debug("Validated hypothesis '%s' with %d sources.", hypothesis, len(urls))
                return {
                    "title": hypothesis,
                    "snippet": combined_snippet,
                    "source_urls": list(dict.fromkeys(urls)),   # deduplicate while preserving insertion order
                    "bucket": "hypothesis_validation",
                }

    log.warning("Failed to validate hypothesis '%s' after retries.", hypothesis)
    return None


def _dedupe_raw_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Smart deduplication merging URLs and keeping the longest snippet."""
    from src.agents.phase1_discovery.archive_manager import ArchiveManager

    unique_map: dict[str, dict[str, Any]] = {}
    for c in candidates:
        norm = ArchiveManager.normalize_topic(c.get("title", ""))
        if not norm:
            continue
            
        if norm not in unique_map:
            unique_map[norm] = dict(c) # copy
        else:
            existing = unique_map[norm]
            curr_len = len(existing.get("snippet", ""))
            new_len = len(c.get("snippet", ""))
            
            if new_len > curr_len:
                existing["snippet"] = c.get("snippet", "")
            
            new_urls = c.get("source_urls", [])
            for url in new_urls:
                if url not in existing["source_urls"]:
                    existing["source_urls"].append(url)
                
    return list(unique_map.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_raw_candidates(
    hypotheses: list[str],
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_per_bucket: int = 4,
    max_concurrency: int = 5,
    request_timeout_seconds: float = APP_CONFIG.api_timeout_seconds,
) -> list[dict[str, Any]]:
    """Validate topic hypotheses by gathering evidence from the web.

    This function represents the search verification step. It no longer invents
    topics from broad buckets, but instead tries to prove whether an ideated 
    hypothesis actually has data backing it.

    Args:
        hypotheses: List of topic ideas to validate.
        session: Active aiohttp ClientSession.
        log: Job logger.
        max_per_bucket: Max search results per hypothesis.
        max_concurrency: Max concurrent Tavily calls.

    Returns:
        Deduplicated list of raw candidate dicts with 'title', 'snippet',
        'source_url', and 'bucket' keys.
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def _validate_wrapped(hypothesis: str) -> dict[str, Any] | None:
        async with sem:
            return await _validate_hypothesis(hypothesis, session, log, max_per_bucket, request_timeout_seconds)

    log.info(
        "Validating %d topic hypotheses via search (max_concurrency=%d)...",
        len(hypotheses), max_concurrency,
    )

    tasks = [_validate_wrapped(h) for h in hypotheses]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_candidates: list[dict[str, Any]] = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            log.error("Validation failed for hypothesis '%s': %s", hypotheses[idx], result)
        elif result is not None:
            valid_candidates.append(result)

    # Deduplicate before returning
    unique = _dedupe_raw_candidates(valid_candidates)
    log.info(
        "Validation complete: %d hypotheses -> %d valid candidates with evidence.",
        len(hypotheses), len(unique),
    )
    return unique
