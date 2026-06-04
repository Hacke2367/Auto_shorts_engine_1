"""
AutoShorts Phase 1A — Discovery Runner
=======================================
The real Phase 1A orchestrator. Discovers, scores, ranks, and returns
approval-ready topic candidates.

Workflow (Idea-First):
  1. Generate novel topic hypotheses via Gemini (Ideation).
  2. Filter hypotheses against archive (produced/rejected).
  3. Validate valid hypotheses (search for evidence via scourer).
  4. Score candidates via structured Gemini assessment.
  5. Merge a limited set of fresh queued items to prevent rescoring waste.
  6. Rank by weighted final score descending.
  7. Persist candidates.json for audit.
  8. Return structured DiscoveryBatch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.agents.core.config import settings, APP_CONFIG
from src.agents.core.retry import standard_retry_policy
from src.agents.core.logger import timed_operation, log_api_call
from src.agents.core.models import (
    DiscoveryBatch,
    TopicCandidate,
)
from src.agents.phase1_discovery.archive_manager import ArchiveManager
from src.agents.phase1_discovery.candidate_score import score_candidates_batch
from src.agents.phase1_discovery.scourer import fetch_raw_candidates

logger = logging.getLogger(__name__)

_IDEATION_PROMPT = """You are the Lead Creative Director for AutoShorts.
Your job is to ideate 10 novel, highly engaging topic hypotheses that could make incredible, data-driven short-form videos.

{niche_context}

Requirements for a good hypothesis:
1. Must be high-interest, viral, or deeply curious.
2. Must have a high likelihood of having actual rankable or comparable data backing it up (e.g., revenue, user count, market share, tiers, populations).
3. Do not just say "History of X". Say "Fastest growing X of 2024". Frame it dynamically.

Format your output strictly as a JSON list of strings representing the topic titles.
Example:
[
  "Top 10 AI companies by computing power",
  "Richest gaming companies vs their most profitable game",
  "Most subscribed YouTubers who lost the most views this year"
]

Output EXACTLY AND ONLY the JSON list.
"""

async def _ideate_hypotheses(
    niche_hint: str | None,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> list[str]:
    """Use Gemini to brainstorm novel topic ideas before we search the web."""
    key = settings.gemini_api_key.get_secret_value()
    cfg = APP_CONFIG.llm.discovery_ideation
    model_name = cfg.model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    _headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    niche_context = f"Please focus exclusively on this niche/theme: '{niche_hint}'" if niche_hint else "Focus on broad general internet trends, business, tech, and pop culture."

    prompt = _IDEATION_PROMPT.format(niche_context=niche_context)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": cfg.temperature,
            "maxOutputTokens": cfg.max_output_tokens,
        },
    }

    try:
        async for attempt in standard_retry_policy():
            with attempt:
                t0 = time.perf_counter()
                async with session.post(url, json=payload, headers=_headers) as resp:
                    elapsed = (time.perf_counter() - t0) * 1000
                    log_api_call(
                        log,
                        service="gemini.ideate",
                        status_code=resp.status,
                        retry_count=attempt.retry_state.attempt_number - 1,
                        duration_ms=elapsed,
                    )
                    resp.raise_for_status()
                    data = await resp.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

                    # Simple brace extraction if it got markdown wrapped
                    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
                    if match:
                        raw_text = match.group(0)

                    ideas = json.loads(raw_text)
                    if isinstance(ideas, list) and all(isinstance(x, str) for x in ideas):
                        return [x.strip() for x in ideas if x.strip()]
                    return []
    except Exception as e:
        log.warning("Failed to ideate hypotheses after retries: %s", e)
        return []


async def run_discovery(
    session: aiohttp.ClientSession,
    log: logging.Logger,
    output_dir: Path,
    niche_hint: str | None = None,
    top_n: int = 5,
) -> DiscoveryBatch:
    """Run the full Phase 1A discovery pipeline."""
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = output_dir / "candidates.json"

    # -- 1. Idempotency Check --
    if candidates_path.exists():
        log.info("candidates.json already exists at %s. Loading cached batch.", candidates_path)
        try:
            raw = json.loads(candidates_path.read_text(encoding="utf-8"))
            batch = DiscoveryBatch.model_validate(raw)
            log.info(
                "Loaded cached discovery batch: %d candidates.",
                len(batch.candidates),
            )
            return batch
        except Exception as e:
            log.warning(
                "Failed to parse cached candidates.json: %s. Rerunning discovery.", e
            )

    with timed_operation(log, "phase1a_discovery", niche=niche_hint or "broad"):
        log.info("=== Phase 1A: Discovery Start (Idea-First) ===")
        
        # -- 2. Ideate Hypotheses --
        hypotheses = await _ideate_hypotheses(niche_hint, session, log)
        if not hypotheses:
            log.warning("Ideation returned 0 hypotheses. Falling back to default topics.")
            hypotheses = [
                f"{niche_hint or 'Business'} revenue comparisons",
                f"Most popular {niche_hint or 'tech'} trends",
                "Fastest growing companies 2024"
            ]
            
        log.info("Ideated %d hypotheses from LLM.", len(hypotheses))

        # -- 3. Archive Filtering (Pre-Search) --
        archive = ArchiveManager()
        archive.expire_stale_entries()
        
        novel_hypotheses = []
        for h in hypotheses:
            if not archive.is_duplicate(h):
                novel_hypotheses.append(h)
            else:
                log.info("Archive filter (pre-search): skipping duplicate idea '%s'.", h)
                
        if not novel_hypotheses:
            log.warning("All ideated hypotheses were duplicates! Generating emergency backups...")
            novel_hypotheses = [
                f"{niche_hint or 'Technology'} latest performance metrics",
                f"{niche_hint or 'Business'} historical market share breakdown"
            ]
                
        # -- 4. Search Validation (Scouring) --
        raw_candidates = await fetch_raw_candidates(
            hypotheses=novel_hypotheses,
            session=session,
            log=log,
        )

        # -- 4.5 Post-Search Archive Filter --
        # Tavily might return articles with titles that accidentally match old videos
        novel_raw_candidates = []
        for c in raw_candidates:
            if not archive.is_duplicate(c.get("title", "")):
                novel_raw_candidates.append(c)
            else:
                log.info("Archive filter (post-search): skipping duplicate raw candidate '%s'", c.get("title"))

        raw_count = len(novel_raw_candidates)
        # ------------------------------------------------
        
        if raw_count == 0:
            log.warning("Validation returned 0 raw candidates. Returning empty batch.")
            return DiscoveryBatch(
                raw_candidate_count=0,
                queued_candidate_count=0,
                returned_candidate_count=0,
                niche_hint=niche_hint,
            )

        # -- 5. Score Candidates --
        scored = await score_candidates_batch(
            raw_candidates=novel_raw_candidates,
            session=session,
            log=log,
            max_concurrency=5,
        )

        if not scored:
            log.warning("Scoring returned 0 valid candidates.")
            return DiscoveryBatch(
                raw_candidate_count=raw_count,
                queued_candidate_count=0,
                returned_candidate_count=0,
                niche_hint=niche_hint,
            )

        # Attach merged source URLs from raw candidates
        source_map: dict[str, list[str]] = {}
        for c in raw_candidates:
            norm = ArchiveManager.normalize_topic(c.get("title", ""))
            urls = c.get("source_urls", [])
            if norm and urls:
                if norm not in source_map:
                    source_map[norm] = []
                for u in urls:
                    if u not in source_map[norm]:
                        source_map[norm].append(u)

        for candidate in scored:
            candidate.candidate_sources = source_map.get(
                candidate.normalized_topic, []
            )

        # -- 6. Merge Queue (Bounded) --
        # We take up to 3 highly-rated queued items and insert them directly.
        # (Note: QueuedTopic does not store 'discovered_at', so we sort strictly by final_score).
        queue = archive.get_queue()
        queued_injected = 0
        
        # Sort queue by descending final score
        queue_sorted = sorted(queue, key=lambda q: q.final_score, reverse=True)
        
        # Take up to 3 queue items
        for q_item in queue_sorted[:3]:
            # Convert QueuedTopic back to a TopicCandidate.
            # We map the final score to all premium sub-dimensions so the Pydantic validator's 
            # weighted sum equals exactly the queued final_score without legacy branch fallback.
            qt_candidate = TopicCandidate(
                topic=q_item.topic,
                normalized_topic=q_item.normalized_topic,
                why_it_matters="Re-evaluated from saved queue.",
                rationale="Re-evaluated from saved queue (legacy sub-scores omitted).",
                validation_confidence="medium",
                
                # Pure Premium Dimensions fallback
                hook_potential_score=q_item.final_score,
                novelty_score=q_item.final_score,
                visual_fit_score=q_item.final_score,
                data_feasibility_score=q_item.final_score,
                freshness_score=q_item.final_score,
                
                # Backfill legacy strictly for compatibility constraints
                virality_score=q_item.final_score,
                template_fit_score=q_item.final_score,
                visual_potential_score=q_item.final_score,
                source_quality_score=q_item.final_score,
                fallback_strength_score=q_item.final_score,
                
                best_fit_template=q_item.best_fit_template,
                fallback_template=q_item.fallback_template,
                fit_reason=q_item.fit_reason,
                source_hint=q_item.source_hint,
                candidate_sources=[q_item.source_hint] if q_item.source_hint and q_item.source_hint.startswith("http") else []
            )
            
            # Avoid dupes with newly scored items
            if not any(c.normalized_topic == qt_candidate.normalized_topic for c in scored):
                scored.append(qt_candidate)
                queued_injected += 1

        if queued_injected > 0:
            log.info("Injected %d highly-rated topics from saved queue directly into ranked batch.", queued_injected)

        # -- 7. Rank by Premium Dimensions --
        scored.sort(
            key=lambda c: (
                c.final_score,
                c.hook_potential_score,
                c.novelty_score,
                c.freshness_score,
                len(c.candidate_sources)
            ), 
            reverse=True
        )

        # -- 8. Slice Top N --
        top_candidates = scored[:top_n]

        log.info(
            "Top %d candidates (of %d eligible):",
            len(top_candidates), len(scored),
        )
        for i, c in enumerate(top_candidates, 1):
            log.info(
                "  #%d: [%.2f] '%s' → %s (fallback=%s)",
                i, c.final_score, c.topic, c.best_fit_template,
                c.fallback_template or "none",
            )

        # -- 9. Build Batch & Persist --
        batch = DiscoveryBatch(
            candidates=top_candidates,
            niche_hint=niche_hint,
            raw_candidate_count=raw_count,
            queued_candidate_count=queued_injected,
            returned_candidate_count=len(top_candidates),
        )

        # Atomic write of candidates.json
        _batch_content = batch.model_dump_json(indent=2)
        _batch_fd, _batch_tmp = tempfile.mkstemp(dir=str(output_dir), suffix=".tmp")
        try:
            with os.fdopen(_batch_fd, "w", encoding="utf-8") as _f:
                _f.write(_batch_content)
            os.replace(_batch_tmp, str(candidates_path))
        except BaseException:
            try:
                os.unlink(_batch_tmp)
            except OSError:
                pass
            raise
        log.info("Saved candidates.json to %s", candidates_path)

        # Persist raw_candidates.json for transparency/audit of what search returned
        raw_path = output_dir / "raw_candidates.json"
        try:
            raw_path.write_text(json.dumps(raw_candidates, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("Failed to save raw_candidates.json: %s", e)

        log.info("=== Phase 1A: Discovery Complete ===")
        return batch
