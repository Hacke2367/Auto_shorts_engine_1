"""
Phase 1B — discovery seed-URL hand-off regression tests (OFFLINE / no API).
================================================================================
Phase 1A's feasibility gate proves a topic has extractable data by finding real
source URLs, then stores them as ``candidate_sources``. Extraction used to throw
that proof away and re-search with a template-flavoured query, which on a
non-commercial topic ("Rome vs Han China" + "specifications revenue") landed on a
YouTube page and yielded prose instead of numbers.

These tests pin the fix — and, just as importantly, pin that the legacy path is
untouched when no seeds are supplied.

  1. Seeds present on attempt 0  -> scraped directly, NO search call.
  2. No seeds                    -> searches exactly as before (regression guard).
  3. Seeds present but retrying  -> falls through to the pivot query, which must
                                    stay topic-neutral (no product vocabulary).

Run directly:   python tests/phase1/test_extraction_seed_urls.py
Or via pytest:  python -m pytest tests/phase1/test_extraction_seed_urls.py -v
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root on path when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agents.phase1_extraction import graph as graph_mod
from src.agents.phase1_extraction.graph import _build_smart_query, node_search


TOPIC = "Rome vs Han China: who had the stronger economy, army, and infrastructure at their peak?"
DISCOVERY_URLS = [
    "https://www.youtube.com/watch?v=lklN4aH7WvY",
    "https://bigthink.com/strange-maps/china-more-unequal-than-rome",
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC11971292",
    "https://en.wikiversity.org/wiki/Comparison_between_Roman_and_Han_Empires",
]


class _SearchSpy:
    """Stand-in for tavily_search that records calls instead of hitting the API."""

    def __init__(self, returns=None):
        self.calls = []
        self._returns = returns if returns is not None else ["https://searched.example/page"]

    async def __call__(self, query, session, log, max_results=5):
        self.calls.append(query)
        return list(self._returns)


def _state(seed_urls, query_attempts=0):
    return {
        "topic": TOPIC,
        "template_name": "vs_card",
        "session": object(),
        "log": logging.getLogger("test.seed_urls"),
        "seed_urls": list(seed_urls),
        "query_attempts": query_attempts,
    }


def _run(state, spy):
    original = graph_mod.tavily_search
    graph_mod.tavily_search = spy
    try:
        return asyncio.run(node_search(state))
    finally:
        graph_mod.tavily_search = original


# --------------------------------------------------------------------------- #
# 1. Seeds are used on the first attempt                                        #
# --------------------------------------------------------------------------- #
def test_seed_urls_are_used_and_search_is_skipped():
    spy = _SearchSpy()
    out = _run(_state(DISCOVERY_URLS), spy)

    assert out["search_urls"] == DISCOVERY_URLS, out["search_urls"]
    assert spy.calls == [], f"search should not run when seeded, got {spy.calls}"
    assert not out.get("failure_category")
    # The retry counter must still advance so a failed seed attempt can pivot.
    assert out["query_attempts"] == 1
    # The wikiversity comparison table — the page that actually holds the data —
    # must survive into the scrape set.
    assert any("wikiversity" in u for u in out["search_urls"])
    return "seeded attempt scrapes discovery URLs and makes zero search calls"


# --------------------------------------------------------------------------- #
# 2. Legacy behaviour is untouched without seeds                                #
# --------------------------------------------------------------------------- #
def test_no_seeds_falls_back_to_search_unchanged():
    spy = _SearchSpy()
    out = _run(_state([]), spy)

    assert len(spy.calls) == 1, spy.calls
    assert spy.calls[0] == _build_smart_query(TOPIC, "vs_card", 0)
    assert out["search_urls"] == ["https://searched.example/page"]
    assert out["query_attempts"] == 1
    return "no seeds -> identical pre-fix search path"


def test_missing_seed_key_is_treated_as_no_seeds():
    """Callers that never pass seed_urls at all must not crash."""
    spy = _SearchSpy()
    state = _state([])
    del state["seed_urls"]
    out = _run(state, spy)

    assert len(spy.calls) == 1
    assert out["search_urls"] == ["https://searched.example/page"]
    return "absent seed_urls key behaves like empty (backward compatible)"


# --------------------------------------------------------------------------- #
# 3. Retries still pivot, and the pivot stays topic-neutral                     #
# --------------------------------------------------------------------------- #
def test_retry_ignores_seeds_and_uses_neutral_pivot_query():
    spy = _SearchSpy()
    out = _run(_state(DISCOVERY_URLS, query_attempts=1), spy)

    assert len(spy.calls) == 1, "retry must search, not re-scrape the same seeds"
    assert out["query_attempts"] == 2

    pivot = spy.calls[0]
    # The attempt-0 vs_card query carries product vocabulary ("specifications",
    # "revenue") which is what broke this topic. The retry pivots must not.
    for product_word in ("specifications", "revenue", "market share"):
        assert product_word not in pivot.lower(), f"pivot leaked product wording: {pivot}"
    return "retry falls through to search with a topic-neutral pivot query"


def test_attempt_zero_vs_card_query_is_still_the_documented_one():
    """Guard: we did not silently change the fallback query in this change."""
    q = _build_smart_query(TOPIC, "vs_card", 0)
    assert q == f"{TOPIC} comparison specifications revenue differences"
    return "attempt-0 vs_card query left untouched by the seed-URL fix"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        msg = fn()
        print(f"  PASS  {fn.__name__}  ->  {msg}")
        passed += 1
    print(f"\n[DONE] {passed}/{len(tests)} offline tests passed (no API calls made).")


if __name__ == "__main__":
    main()
