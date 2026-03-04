"""
AutoShorts Phase 1A — The Scouring Engine (Topic-First)
=======================================================
Discovers raw topic candidates from the web across multiple verticals.

Design Principles:
  - Topic-first, template-second: search broadly, not through a template lens.
  - Returns raw candidate snippets for downstream scoring.
  - Does NOT assign templates or compute final scores (that is candidate_score.py).
  - Does NOT persist archive state (that is discovery_runner.py).
  - Uses Tavily for broad web search across multiple discovery buckets.
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


# ---------------------------------------------------------------------------
# Discovery Buckets — broad topic verticals
# ---------------------------------------------------------------------------

# Each bucket is a search query designed to surface topics across a vertical.
# These are intentionally broad and NOT template-specific.
DISCOVERY_BUCKETS: list[dict[str, str]] = [
    {
        "name": "trending_data",
        "query": "trending statistics data rankings comparisons",
        "topic": "news",
    },
    {
        "name": "ai_tech",
        "query": "AI tools products market share growth comparison",
        "topic": "news", 
    },
    {
        "name": "business_finance",
        "query": "business revenue market cap rankings richest companies",
        "topic": "finance",
    },
    {
        "name": "gaming_entertainment",
        "query": "gaming most popular players statistics esports",
        "topic": "general",
    },
    {
        "name": "pop_culture",
        "query": "most followed celebrities creators subscribers views",
        "topic": "general",
    },
    {
        "name": "internet_trends",
        "query": "viral internet trends creator economy social media statistics",
        "topic": "general",
    },
    {
        "name": "wildcard",
        "query": "surprising statistics data you didn't know interesting facts",
        "topic": "general",
    },
]


async def _fetch_bucket(
    bucket: dict[str, str],
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_results: int = 5,
) -> list[dict[str, str]]:
    """Fetch raw candidates from a single discovery bucket via Tavily."""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": settings.tavily_api_key.get_secret_value(),
        "query": bucket["query"],
        "search_depth": "basic",
        "max_results": max_results,
        "include_raw_content": False,
        "topic": bucket.get("topic", "general"),
    }

    bucket_name = bucket["name"]
    async for attempt in _get_retry_policy():
        with attempt:
            t0 = time.perf_counter()
            async with session.post(url, json=payload) as resp:
                elapsed = (time.perf_counter() - t0) * 1000
                log_api_call(
                    log,
                    service=f"tavily.search.scour.{bucket_name}",
                    status_code=resp.status,
                    retry_count=attempt.retry_state.attempt_number - 1,
                    duration_ms=elapsed,
                )
                resp.raise_for_status()
                data = await resp.json()

                results = []
                for res in data.get("results", []):
                    title = (res.get("title") or "").strip()
                    content = (res.get("content") or "").strip()
                    source_url = (res.get("url") or "").strip()
                    if title and content:
                        results.append({
                            "title": title,
                            "snippet": content,
                            # We store sources as a list from the start
                            "source_urls": [source_url] if source_url else [],
                            "bucket": bucket_name,
                        })

                log.debug(
                    "Bucket '%s' returned %d candidates.", bucket_name, len(results)
                )
                return results

    log.warning("Failed to fetch bucket '%s' after retries.", bucket_name)
    return []


def _dedupe_raw_candidates(
    candidates: list[dict[str, str]],
) -> list[dict[str, str]]:
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
            # Merge logic: if we have a duplicate, keep the longest snippet
            existing = unique_map[norm]
            curr_len = len(existing.get("snippet", ""))
            new_len = len(c.get("snippet", ""))
            
            if new_len > curr_len:
                existing["snippet"] = c.get("snippet", "")
            
            # Preserve source diversity: merge URLs
            new_urls = c.get("source_urls", [])
            for url in new_urls:
                if url not in existing["source_urls"]:
                    existing["source_urls"].append(url)
                
    return list(unique_map.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_raw_candidates(
    session: aiohttp.ClientSession,
    log: logging.Logger,
    niche_hint: str | None = None,
    max_per_bucket: int = 5,
    max_concurrency: int = 3,
) -> list[dict[str, str]]:
    """Fetch raw topic candidates from all discovery buckets.

    This function is topic-first: it searches broadly across verticals
    and does NOT filter by template. Template assignment happens downstream
    in the scoring layer.

    Args:
        session: Active aiohttp ClientSession.
        log: Job logger.
        niche_hint: Optional niche to add to every query (e.g. "AI tools").
        max_per_bucket: Max results per bucket.
        max_concurrency: Max concurrent Tavily calls.

    Returns:
        Deduplicated list of raw candidate dicts with 'title', 'snippet',
        'source_url', and 'bucket' keys.
    """
    buckets = DISCOVERY_BUCKETS.copy()

    # If niche_hint is provided, add it as an extra focused bucket
    if niche_hint:
        buckets.append({
            "name": "niche_focused",
            "query": f"{niche_hint} statistics data rankings comparison",
            "topic": "general",
        })

    sem = asyncio.Semaphore(max_concurrency)

    async def _fetch_wrapped(bucket: dict[str, str]) -> list[dict[str, str]]:
        async with sem:
            return await _fetch_bucket(bucket, session, log, max_per_bucket)

    log.info(
        "Scouring %d discovery buckets (max_concurrency=%d)...",
        len(buckets), max_concurrency,
    )

    tasks = [_fetch_wrapped(b) for b in buckets]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    combined: list[dict[str, str]] = []
    for idx, result in enumerate(all_results):
        if isinstance(result, Exception):
            log.error("Bucket %d failed: %s", idx, result)
        elif isinstance(result, list):
            combined.extend(result)

    # Deduplicate before returning
    unique = _dedupe_raw_candidates(combined)
    log.info(
        "Scouring complete: %d raw → %d unique candidates.",
        len(combined), len(unique),
    )
    return unique
