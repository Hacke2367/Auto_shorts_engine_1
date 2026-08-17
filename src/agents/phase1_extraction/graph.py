"""
AutoShorts Phase 1B — LangGraph Extraction Workflow
====================================================
Orchestrates the Extraction Engine as a robust StateGraph.

Linear Flow:
  Search (tavily) → Scrape (tavily) → Extract (gemini) → Complete
"""

from __future__ import annotations

import logging

try:
    from typing import NotRequired, TypedDict
except ImportError:
    from typing_extensions import NotRequired, TypedDict

import aiohttp
from langgraph.graph import END, START, StateGraph

from src.agents.core.models import SourceAudit, TemplateDataset, TemplateSpec
from src.agents.phase1_extraction.api_clients import (
    extract_dataset,
    tavily_extract,
    tavily_search,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class ExtractionState(TypedDict):
    """The unified state moving through the Phase 1B extraction graph."""

    topic: str
    template_name: str
    template_spec: TemplateSpec

    # Runtime resources
    session: aiohttp.ClientSession
    log: logging.Logger

    # Evidence carried over from Phase 1A discovery. These are the URLs the
    # feasibility gate already proved contain extractable data, so attempt 0
    # uses them directly instead of re-searching from scratch. Empty list =
    # legacy behaviour (search every attempt).
    seed_urls: NotRequired[list[str]]

    # Evolving data
    attempt_number: NotRequired[int]
    search_urls: NotRequired[list[str]]
    raw_context: NotRequired[list[SourceAudit]]
    extracted_data: NotRequired[TemplateDataset | None]
    
    # Explicit Failure tracking
    failure_reason: NotRequired[str | None]
    failure_category: NotRequired[str | None]
    query_attempts: NotRequired[int]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def _build_smart_query(topic: str, template_name: str, attempt: int = 0) -> str:
    """Formulate a semantic search query based on the template type and retry attempt."""
    
    # Attempt 0: Direct template-aware query
    if attempt == 0:
        base_queries = {
            "vs_card": f"{topic} comparison specifications revenue differences",
            "bar_chart": f"{topic} ranking statistics top list",
            "butterfly_chart": f"{topic} versus comparison detailed stats",
            "scan_race": f"{topic} historical data year by year timeline",
            "geo_universal": f"{topic} global distribution countries map data",
            "donut_breakdown": f"{topic} market share percentage breakdown",
            "sort_card": f"{topic} items split into two groups comparison categories",
        }
        return base_queries.get(template_name, f"{topic} latest statistics data facts")

    # Semantic Pivots for Retries
    if attempt == 1:
        # Pivot A: Official sources & reports
        return f"{topic} official report research statistics whitepaper"
    elif attempt == 2:
        # Pivot B: Historical data to bypass noisy recent-news
        return f"{topic} historical data trend timeline analysis"

    # Default fallback (should not be reached with current retry cap of 2)
    return f"{topic} deeper quantitative evidence facts"


async def node_search(state: ExtractionState) -> ExtractionState:
    """Node: Discover relevant URLs on the web."""
    # Clear any stale failure state from a previous attempt before trying again
    state.pop("failure_category", None)
    state.pop("failure_reason", None)

    log = state["log"]
    session = state["session"]
    topic = state["topic"]
    template_name = state["template_name"]

    attempts = state.get("query_attempts", 0)

    # Attempt 0 prefers the discovery evidence over a fresh search. Phase 1A
    # already proved data exists on these exact URLs; re-searching threw that
    # proof away and let a generic query land on pages with no extractable
    # numbers. Retries still fall through to the pivot queries below.
    seed_urls = state.get("seed_urls") or []
    if attempts == 0 and seed_urls:
        log.info(
            "Extraction Search seeded from discovery for '%s' — using %d candidate URL(s), skipping search.",
            topic, len(seed_urls),
        )
        state["search_urls"] = list(seed_urls)
        state["query_attempts"] = attempts + 1
        return state

    query = _build_smart_query(topic, template_name, attempts)

    log.info("Extraction Search executing for '%s' (Attempt %d) | Query: %s", topic, attempts + 1, query)
    try:
        urls = await tavily_search(
            query=query,
            session=session,
            log=log,
            max_results=5,
        )
        if not urls:
            state["failure_reason"] = f"Tavily search attempt {attempts + 1} found 0 URLs."
            state["failure_category"] = "search_failure"
        state["search_urls"] = urls
    except Exception as e:
        log.exception("Extraction Search failed")
        state["failure_reason"] = f"Search exception: {e}"
        state["failure_category"] = "search_failure"
        state["search_urls"] = []

    state["query_attempts"] = attempts + 1
    return state


async def node_scrape(state: ExtractionState) -> ExtractionState:
    """Node: Extract raw markdown from the discovered URLs."""
    if state.get("failure_category"):
        return state

    log = state["log"]
    session = state["session"]
    urls = state.get("search_urls", [])

    if not urls:
        log.warning("Extraction Scrape skipped — no URLs found.")
        state["raw_context"] = []
        state["failure_category"] = "search_failure"
        state["failure_reason"] = "No search URLs available to scrape."
        return state

    log.info("Extraction Scrape executing for %d URLs", len(urls))
    try:
        audits = await tavily_extract(urls=urls, session=session, log=log)
        if not audits:
            state["failure_reason"] = "Tavily extract returned empty content for all URLs."
            state["failure_category"] = "scrape_failure"
        state["raw_context"] = audits
    except Exception as e:
        log.exception("Extraction Scrape failed")
        state["failure_reason"] = f"Scrape exception: {e}"
        state["failure_category"] = "scrape_failure"
        state["raw_context"] = []

    return state


async def node_extract(state: ExtractionState) -> ExtractionState:
    """Node: Let Gemini formulate the structured dataset from raw markdown."""
    if state.get("failure_category"):
        return state

    log = state["log"]
    session = state["session"]
    context = state.get("raw_context", [])

    if not context:
        log.warning("Extraction Extract skipped — raw_context is empty.")
        state["failure_reason"] = "Cannot extract without scraped context."
        state["failure_category"] = "scrape_failure"
        state["extracted_data"] = None
        return state

    # Surface weak-context failures explicitly
    total_len = sum(len(src.raw_snippet) for src in context)
    if total_len < 150:
        log.warning("Extraction Extract skipped — context is critically weak (%d chars).", total_len)
        state["failure_reason"] = f"Context too weak for extraction ({total_len} chars)."
        state["failure_category"] = "weak_context"
        state["extracted_data"] = None
        return state

    log.info("Extraction Extract executing using %d audits (%d chars)", len(context), total_len)
    try:
        dataset = await extract_dataset(
            topic=state["topic"],
            context=context,
            template_name=state["template_name"],
            template_spec=state["template_spec"],
            session=session,
            log=log,
        )
        state["extracted_data"] = dataset
    except ValueError as e:
        msg = str(e)
        log.error("Extraction failed: %s", msg)
        state["failure_reason"] = msg
        if msg.startswith("parse_failure:"):
            state["failure_category"] = "parse_failure"
        elif msg.startswith("schema_failure:"):
            state["failure_category"] = "schema_failure"
        else:
            state["failure_category"] = "extraction_failure"
        state["extracted_data"] = None
    except Exception as e:
        log.exception("Extraction Extract failed unexpectedly")
        state["failure_reason"] = f"Extract exception: {e}"
        state["failure_category"] = "extraction_failure"
        state["extracted_data"] = None

    return state


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------


def should_retry_search(state: ExtractionState) -> str:
    """Conditional edge routing after search."""
    urls = state.get("search_urls", [])
    attempts = state.get("query_attempts", 0)

    if not urls:
        if attempts < 2:
            state["log"].warning("Search yielded 0 URLs. Retrying (attempt %d/2)...", attempts)
            return "search"
        else:
            state["log"].error("Search yielded 0 URLs after 2 attempts. Aborting.")
            return END

    return "scrape"


def build_extraction_graph() -> StateGraph:
    """Assemble and compile the Phase 1B extraction LangGraph."""
    graph = StateGraph(ExtractionState)

    graph.add_node("search", node_search)
    graph.add_node("scrape", node_scrape)
    graph.add_node("extract", node_extract)

    graph.add_edge(START, "search")
    graph.add_conditional_edges(
        "search",
        should_retry_search,
        {
            "search": "search",
            "scrape": "scrape",
            END: END
        }
    )
    graph.add_edge("scrape", "extract")
    graph.add_edge("extract", END)

    return graph.compile()
