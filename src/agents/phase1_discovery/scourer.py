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

logger = logging.getLogger(__name__)


def _get_retry_policy() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )


async def _validate_hypothesis(
    hypothesis: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_results: int = 4,
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

    async for attempt in _get_retry_policy():
        with attempt:
            t0 = time.perf_counter()
            async with session.post(url, json=payload) as resp:
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
                    "source_urls": list(set(urls)),
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
            return await _validate_hypothesis(hypothesis, session, log, max_per_bucket)

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
