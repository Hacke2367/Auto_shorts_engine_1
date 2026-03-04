"""
AutoShorts Phase 1A — Discovery Runner
=======================================
The real Phase 1A orchestrator. Discovers, scores, ranks, and returns
approval-ready topic candidates.

Workflow:
  1. Fetch raw candidates across broad verticals (scourer)
  2. Filter against archive (produced/rejected cooldowns)
  3. Score candidates via structured Gemini assessment
  4. Assign best-fit + fallback templates
  5. Rank by weighted final score descending
  6. Slice top N
  7. Persist candidates.json for audit
  8. Return structured DiscoveryBatch

Design Principles:
  - Idempotent: if candidates.json already exists and is valid, skip.
  - Fully async with rate-limited concurrency.
  - Structured logging throughout.
  - Archive is read-only during discovery (write happens at decision time).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from src.agents.core.config import settings
from src.agents.core.logger import timed_operation
from src.agents.core.models import (
    DiscoveryBatch,
    TopicCandidate,
)
from src.agents.phase1_discovery.archive_manager import ArchiveManager
from src.agents.phase1_discovery.candidate_score import score_candidates_batch
from src.agents.phase1_discovery.scourer import fetch_raw_candidates

logger = logging.getLogger(__name__)


async def run_discovery(
    session: aiohttp.ClientSession,
    log: logging.Logger,
    output_dir: Path,
    niche_hint: str | None = None,
    top_n: int = 5,
) -> DiscoveryBatch:
    """Run the full Phase 1A discovery pipeline.

    Args:
        session: Active aiohttp ClientSession.
        log: Structured logger.
        output_dir: Directory to persist candidates.json and logs.
        niche_hint: Optional domain/niche to bias discovery (e.g. "AI tools").
        top_n: Number of top candidates to return.

    Returns:
        A DiscoveryBatch with scored, ranked, approval-ready candidates.
    """
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
        # -- 2. Fetch Raw Candidates --
        log.info("=== Phase 1A: Discovery Start ===")
        raw_candidates = await fetch_raw_candidates(
            session=session,
            log=log,
            niche_hint=niche_hint,
        )

        if not raw_candidates:
            log.warning("Scouring returned 0 raw candidates. Returning empty batch.")
            return DiscoveryBatch(
                raw_candidate_count=0,
                queued_candidate_count=0,
                returned_candidate_count=0,
                niche_hint=niche_hint,
            )

        raw_count = len(raw_candidates)
        log.info("Fetched %d unique raw candidates.", raw_count)

        # -- 3. Archive Filtering & Queue Injection --
        archive = ArchiveManager()
        archive.expire_stale_entries()

        # Inject saved queue topics as raw candidates so they get scored again
        # against the current batch context
        queue = archive.get_queue()
        queued_raw = []
        for q in queue:
            # Only inject source_urls array if we have a real URL
            urls = [q.source_hint] if q.source_hint and q.source_hint.startswith("http") else []
            queued_raw.append({
                "title": q.topic,
                "snippet": q.fit_reason or "Re-evaluating queued topic.",
                "source_urls": urls,
                "bucket": "saved_queue"
            })
            
        if queued_raw:
            log.info("Injecting %d topics from saved queue into scoring batch.", len(queued_raw))
            raw_candidates.extend(queued_raw)
            # Re-dedupe after injection
            from src.agents.phase1_discovery.scourer import _dedupe_raw_candidates
            raw_candidates = _dedupe_raw_candidates(raw_candidates)

        # -- 3.5. Persist Raw Candidates (for debugging / audit) --
        raw_path = output_dir / "raw_candidates.json"
        try:
            raw_path.write_text(json.dumps(raw_candidates, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("Failed to save raw_candidates.json: %s", e)

        novel_candidates: list[dict[str, Any]] = []
        for c in raw_candidates:
            title = c.get("title", "")
            # Do NOT filter out things that just came from the queue
            if c.get("bucket") != "saved_queue" and archive.is_duplicate(title):
                log.debug("Archive filter: skipping '%s'.", title)
            else:
                novel_candidates.append(c)

        log.info(
            "%d/%d candidates survived archive filtering.",
            len(novel_candidates), raw_count,
        )

        if not novel_candidates:
            log.warning("All candidates filtered by archive. Returning empty batch.")
            return DiscoveryBatch(
                raw_candidate_count=raw_count,
                queued_candidate_count=len(queued_raw),
                returned_candidate_count=0,
                niche_hint=niche_hint,
            )

        # -- 4. Score Candidates --
        scored = await score_candidates_batch(
            raw_candidates=novel_candidates,
            session=session,
            log=log,
            max_concurrency=5,
        )

        if not scored:
            log.warning("Scoring returned 0 valid candidates.")
            return DiscoveryBatch(
                raw_candidate_count=raw_count,
                queued_candidate_count=len(queued_raw),
                returned_candidate_count=0,
                niche_hint=niche_hint,
            )

        # Attach merged source URLs from raw candidates
        source_map: dict[str, list[str]] = {}
        for c in novel_candidates:
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

        # -- 5. Rank by Multiple Dimensions (Deterministic Tie-Break) --
        # Sort key: (final_score, template_fit_score, source_quality_score, source_count)
        scored.sort(
            key=lambda c: (
                c.final_score,
                c.template_fit_score,
                c.source_quality_score,
                len(c.candidate_sources)
            ), 
            reverse=True
        )

        # -- 6. Slice Top N --
        top_candidates = scored[:top_n]

        log.info(
            "Top %d candidates (of %d scored):",
            len(top_candidates), len(scored),
        )
        for i, c in enumerate(top_candidates, 1):
            log.info(
                "  #%d: [%.2f] '%s' → %s (fallback=%s)",
                i, c.final_score, c.topic, c.best_fit_template,
                c.fallback_template or "none",
            )

        # -- 7. Build Batch --
        batch = DiscoveryBatch(
            candidates=top_candidates,
            niche_hint=niche_hint,
            raw_candidate_count=raw_count,
            queued_candidate_count=len(queued_raw),
            returned_candidate_count=len(top_candidates),
        )

        # -- 8. Persist candidates.json --
        candidates_path.write_text(
            batch.model_dump_json(indent=2),
            encoding="utf-8",
        )
        log.info("Saved candidates.json to %s", candidates_path)

        log.info("=== Phase 1A: Discovery Complete ===")
        return batch
