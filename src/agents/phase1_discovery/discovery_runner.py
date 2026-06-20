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
import math
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
from src.agents.phase1_discovery.scourer import fetch_raw_candidates, fetch_trending_context

logger = logging.getLogger(__name__)


class IdeationUnavailableError(Exception):
    """Raised when the ideation LLM call fails outright (e.g. repeated 503s).

    This is distinct from ideation *succeeding but returning an empty list*:
    a true failure means the foundation of the run is gone, so the caller
    should abort BEFORE spending any Tavily/scoring budget on hardcoded
    fallback topics.
    """


_IDEATION_PROMPT = """You are the Lead Creative Director for AutoShorts, a studio that
produces premium, data-driven short-form videos.

Today is {current_date}. Think about what is relevant and interesting RIGHT NOW, in the
current period — do NOT anchor to specific past years out of habit.

Every video renders a structured dataset into ONE of several visual formats (rankings,
head-to-heads, breakdowns, races, mirrored comparisons, maps, two-group A/B splits). You
are NOT limited to rankings.

{niche_context}

## Live signal — what's currently in the news for this niche
{trend_context}

## Your Task
Ideate {idea_count} novel, highly engaging topic hypotheses for this niche. Act like a free,
unbiased journalist hunting the best stories — with awareness of what we can visualise.

Deliver a deliberate MIX, because a great slate needs both:
- TRENDING: a few topics riding the live signal above (timely, in-the-moment).
- EVERGREEN / VALUABLE: a few topics that may not be breaking news but are genuinely useful
  and almost certainly have solid, extractable published data behind them.
Trending alone is risky (the data may not exist yet); valuable alone can feel stale. Mix both.

## Story Lenses — hunt through ALL of these (they are SEARCH DIRECTIONS, not quotas)
- THE RIVALRY     — two giants locked head-to-head (X vs Y: who actually wins?)
- THE AUTOPSY     — where the money / a total really goes when you cut it open
- THE SHIFT       — something rising or collapsing across years or stages
- THE MAP         — a story where geography IS the story (where in the world...)
- THE LEADERBOARD — a ranking with a surprise at the top or the bottom
- THE SLEEPER     — the boring / ignored thing quietly beating the famous thing

## Rules of the hunt
1. Story quality ALWAYS beats lens coverage. NEVER force a weak story into a lens just to
   tick it — if a lens has no genuinely good story, skip it.
2. But if most of your ideas came from the SAME lens, you defaulted instead of hunting.
   Replace the weakest duplicates using other lenses.
3. ENOUGH DATA: each topic must yield EITHER ~5-8 comparable items, a clean 2-entity
   head-to-head, a parts-of-a-whole split, or a progression. Avoid thin "Top 3" framings
   that leave a chart empty.
4. DYNAMIC & BUILDABLE: frame with tension/recency; each must plausibly have real, published,
   extractable numbers — not vibes. Bake in a year ONLY when it is genuinely part of the story
   (e.g. an annual ranking), and then use the CURRENT period, not an arbitrary past year.

## Output
A JSON list of exactly {idea_count} strings (topic titles only). No commentary, and NO
comments inside the JSON.
The examples below only illustrate the SHAPE/lens variety (a rivalry, an autopsy, a map/shift,
a sleeper) — do NOT copy them, and do NOT treat their phrasing or any year as a template:
[
  "<entity A> vs <entity B>: who actually wins on <shared metric>",
  "Where every unit of <a total budget/price> really goes",
  "The places where <a behaviour> is changing fastest",
  "The overlooked <asset/option> quietly beating the obvious choice"
]

Output EXACTLY AND ONLY the JSON list (a flat array of strings).
"""

def _extract_json_array(raw_text: str) -> list[str]:
    """Best-effort extraction of a flat JSON array of strings from LLM output.

    Tolerates markdown code fences, surrounding prose, and trailing junk. Always
    returns a list (never raises) so a malformed-but-successful response degrades
    gracefully into the caller's fallback instead of aborting the whole run.
    """
    if not raw_text:
        return []

    # Try, in order: the raw text, a ```json ...``` fenced block, then the first
    # balanced [...] span. First variant that parses into a non-empty string list wins.
    attempts: list[str] = [raw_text.strip()]
    fenced = re.search(r"```(?:json)?\s*(.+?)```", raw_text, re.DOTALL | re.IGNORECASE)
    if fenced:
        attempts.append(fenced.group(1).strip())
    bracket = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if bracket:
        attempts.append(bracket.group(0))

    for text in attempts:
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list):
            out = [str(x).strip() for x in parsed if isinstance(x, str) and x.strip()]
            if out:
                return out
    return []


def _apply_feasibility_gate(
    scored: list[TopicCandidate],
    min_feasibility: float,
    log: logging.Logger,
) -> tuple[list[TopicCandidate], list[TopicCandidate]]:
    """Split scored candidates into (eligible, gated_out) by data feasibility.

    A topic with no provable published data is worthless downstream — extraction
    would burn money and fail. The scoring judge already detects this
    (data_feasibility_score + 'No data found' reasoning); this gate ENFORCES the
    verdict instead of letting a strong hook smuggle a dataless topic through the
    weighted final score (feasibility is only 20% of final_score).
    """
    eligible: list[TopicCandidate] = []
    gated: list[TopicCandidate] = []
    for c in scored:
        if c.data_feasibility_score >= min_feasibility:
            eligible.append(c)
        else:
            gated.append(c)
            log.info(
                "Feasibility gate: dropped '%s' (data_feasibility=%.1f < %.1f) — no provable data.",
                c.topic, c.data_feasibility_score, min_feasibility,
            )
    if gated:
        log.warning(
            "Feasibility gate dropped %d/%d scored candidates lacking provable data.",
            len(gated), len(scored),
        )
    return eligible, gated


async def _ideate_hypotheses(
    niche_hint: str | None,
    trend_context: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    idea_count: int = 10,
) -> list[str]:
    """Use Gemini to brainstorm novel topic ideas before we search the web.

    ``trend_context`` is a fresh, live news snapshot (may be "") used to seed the
    brainstorm with what's currently happening — see ``fetch_trending_context``.
    ``idea_count`` over-provisions ideas so the downstream data-feasibility gate
    can cull dataless ones and still fill the requested batch.
    """
    key = settings.gemini_api_key.get_secret_value()
    cfg = APP_CONFIG.llm.discovery_ideation
    model_name = cfg.model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    _headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    niche_context = f"Please focus exclusively on this niche/theme: '{niche_hint}'" if niche_hint else "Focus on broad general internet trends, business, tech, and pop culture."

    current_date = datetime.now(timezone.utc).strftime("%B %Y")
    trend_block = (
        trend_context.strip() if (trend_context and trend_context.strip())
        else "(No live trend data available right now — rely on your own most up-to-date knowledge.)"
    )

    prompt = _IDEATION_PROMPT.format(
        idea_count=idea_count,
        current_date=current_date,
        niche_context=niche_context,
        trend_context=trend_block,
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": cfg.temperature,
            "maxOutputTokens": cfg.max_output_tokens,
        },
    }

    rc = APP_CONFIG.retry
    # -- HTTP call only (with patient retry). ONLY true network/5xx failures
    #    abort the run; JSON parsing is deliberately OUTSIDE this block so a
    #    malformed-but-successful reply never masquerades as an outage. --
    data: dict | None = None
    try:
        async for attempt in standard_retry_policy(
            min_wait=rc.ideation_min_wait,
            max_wait=rc.ideation_max_wait,
            max_attempts=rc.ideation_max_attempts,
        ):
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
    except Exception as e:
        # The call itself never succeeded (e.g. repeated 503s / timeouts).
        # Signal this distinctly so the caller can abort before spending any
        # downstream Tavily/scoring budget on hardcoded fallback topics.
        log.warning("Ideation call failed outright after retries: %s", e)
        raise IdeationUnavailableError(str(e)) from e

    # -- Parse the SUCCESSFUL response robustly. A parse failure here is NOT an
    #    outage — the model replied, we just couldn't read it — so we return []
    #    and let the caller's default-topic fallback take over (never abort). --
    if data is None:  # defensive; the loop either assigns data or raises above
        return []
    try:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        log.warning("Ideation response carried no text payload: %s", e)
        return []

    ideas = _extract_json_array(raw_text)
    if not ideas:
        log.warning("Ideation succeeded but no parseable topic list was found.")
    return ideas


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
        
        # -- 1.5 Trend-seed with a live signal --
        # Fetch what's CURRENTLY trending in the niche so ideation brainstorms from
        # fresh data, not stale model memory (Gemini has no live web access on its
        # own). Fail-safe by design: returns "" on any error and ideation proceeds.
        trend_context = await fetch_trending_context(niche_hint, session, log)

        # -- 2. Ideate Hypotheses --
        # Ideation is the foundation of the whole run. If the call fails outright
        # (e.g. repeated 503s), abort NOW — before spending any Tavily/scoring
        # budget on the 3-topic hardcoded fallback that would just be discarded
        # on the next re-run anyway.
        # Over-provision ideas: the feasibility gate below will cull dataless ones.
        # Take the LARGER of (top_n + flat buffer) and (top_n * multiplier) so small
        # batches keep the cheap +buffer behaviour while large batches in high-cull
        # niches over-provision enough to still fill top_n after the gate.
        idea_count = max(
            top_n + APP_CONFIG.discovery_ideation_buffer,
            math.ceil(top_n * APP_CONFIG.discovery_ideation_multiplier),
        )
        try:
            hypotheses = await _ideate_hypotheses(
                niche_hint, trend_context, session, log, idea_count=idea_count
            )
        except IdeationUnavailableError as e:
            log.error(
                "Ideation unavailable (%s). Aborting discovery before any "
                "search/scoring spend. Re-run in a moment.", e
            )
            return DiscoveryBatch(
                raw_candidate_count=0,
                queued_candidate_count=0,
                returned_candidate_count=0,
                niche_hint=niche_hint,
                error="ideation_unavailable",
                error_detail=str(e),
            )

        if not hypotheses:
            log.warning("Ideation returned 0 hypotheses. Falling back to default topics.")
            base = niche_hint or "business"
            # Year-agnostic, shape-varied fallbacks (no hardcoded year => no anchor).
            hypotheses = [
                f"The biggest players in {base}, ranked",      # leaderboard
                f"Where the money really goes in {base}",      # autopsy / breakdown
                f"What's rising vs falling in {base} right now",  # shift
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

        # -- 5.5 Data-Feasibility Gate --
        # Enforce the scoring judge's verdict: topics without provable published
        # data are dropped HERE, before they can reach extraction and waste real
        # money downstream. A great hook never rescues a dataless topic.
        scored, gated_out = _apply_feasibility_gate(
            scored, APP_CONFIG.discovery_min_data_feasibility, log
        )
        if not scored:
            log.warning(
                "ALL scored candidates failed the data-feasibility gate. "
                "Nothing usable this run — re-run or adjust the niche."
            )
            return DiscoveryBatch(
                raw_candidate_count=raw_count,
                queued_candidate_count=0,
                returned_candidate_count=0,
                gated_candidate_count=len(gated_out),
                niche_hint=niche_hint,
                error="no_feasible_candidates",
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
            gated_candidate_count=len(gated_out),
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
