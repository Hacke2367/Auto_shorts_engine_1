import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from src.agents.core.models import TopicCandidate
from src.agents.phase1_discovery import discovery_runner


class FakeArchive:
    def expire_stale_entries(self):
        return None

    def get_queue(self):
        return []

    def is_duplicate(self, topic: str) -> bool:
        return topic.strip().lower() == "top 10 technical giants"

    @staticmethod
    def normalize_topic(topic: str) -> str:
        return topic.strip().lower().replace(" ", "-")


async def fake_ideate_hypotheses(niche_hint, trend_context, session, log, idea_count=10):
    """Stand in for the LLM ideation call — no provider, no key, no network."""
    return [f"Hypothesis {i} about {niche_hint}" for i in range(idea_count)]


async def fake_fetch_raw_candidates(session=None, log=None, niche_hint=None, hypotheses=None):
    return [
        {
            "title": "Nvidia vs AMD revenue race",
            "snippet": "Quarterly rivalry with clear numbers",
            "source_urls": ["https://example.com/a"],
        },
        {
            "title": "Top 10 technical giants",
            "snippet": "Generic and obvious topic",
            "source_urls": ["https://example.com/b"],
        },
        {
            "title": "Smartphone brands losing market share",
            "snippet": "Decline trend with interesting movement",
            "source_urls": ["https://example.com/c"],
        },
    ]


async def fake_score_candidates_batch(raw_candidates, session=None, log=None, max_concurrency=5):
    # Important: duplicate topic should already be filtered before this point
    titles = [c["title"] for c in raw_candidates]
    assert "Top 10 technical giants" not in titles, "Duplicate topic should have been filtered before scoring"

    return [
        TopicCandidate(
            topic="Nvidia vs AMD revenue race",
            normalized_topic="nvidia-vs-amd-revenue-race",
            virality_score=8,
            data_feasibility_score=9,
            template_fit_score=8,
            visual_potential_score=9,
            source_quality_score=7,
            fallback_strength_score=6,
            best_fit_template="vs_card",
            fallback_template="bar_chart",
        ),
        TopicCandidate(
            topic="Smartphone brands losing market share",
            normalized_topic="smartphone-brands-losing-market-share",
            virality_score=7,
            data_feasibility_score=8,
            template_fit_score=8,
            visual_potential_score=8,
            source_quality_score=7,
            fallback_strength_score=6,
            best_fit_template="bar_chart",
            fallback_template="scan_race",
        ),
    ]


def test_run_discovery_writes_candidates_json():
    with TemporaryDirectory() as tmpdir:
        outdir = Path(tmpdir)

        # monkeypatch module-level dependencies
        #
        # _ideate_hypotheses MUST be faked too. It is the first thing run_discovery
        # does, and with session=None the real one raises AttributeError, which
        # run_discovery correctly converts into IdeationUnavailableError and aborts
        # with zero candidates — so the rest of the flow was never exercised.
        original_archive = discovery_runner.ArchiveManager
        original_fetch = discovery_runner.fetch_raw_candidates
        original_score = discovery_runner.score_candidates_batch
        original_ideate = discovery_runner._ideate_hypotheses

        discovery_runner.ArchiveManager = FakeArchive
        discovery_runner.fetch_raw_candidates = fake_fetch_raw_candidates
        discovery_runner.score_candidates_batch = fake_score_candidates_batch
        discovery_runner._ideate_hypotheses = fake_ideate_hypotheses

        try:
            batch = __import__("asyncio").run(
                discovery_runner.run_discovery(
                    session=None,
                    log=logging.getLogger("test_discovery_runner"),
                    output_dir=outdir,
                    niche_hint="AI tools",
                    top_n=2,
                )
            )

            assert batch is not None
            assert len(batch.candidates) == 2
            assert (outdir / "candidates.json").exists(), "candidates.json not created"
        finally:
            discovery_runner.ArchiveManager = original_archive
            discovery_runner.fetch_raw_candidates = original_fetch
            discovery_runner.score_candidates_batch = original_score
            discovery_runner._ideate_hypotheses = original_ideate


def test_run_discovery_uses_cache_on_second_run():
    with TemporaryDirectory() as tmpdir:
        outdir = Path(tmpdir)

        # build cached candidates.json manually
        cached_batch = {
            "candidates": [
                {
                    "topic": "Cached Topic",
                    "normalized_topic": "cached-topic",
                    "virality_score": 8,
                    "data_feasibility_score": 8,
                    "template_fit_score": 8,
                    "visual_potential_score": 8,
                    "source_quality_score": 8,
                    "fallback_strength_score": 8,
                    "best_fit_template": "bar_chart",
                    "fallback_template": "vs_card",
                    "final_score": 8.0,
                    "candidate_sources": [],
                }
            ],
            "niche_hint": "test",
            "raw_candidate_count": 1,
            "queued_candidate_count": 0,
            "returned_candidate_count": 1,
        }
        (outdir / "candidates.json").write_text(json.dumps(cached_batch), encoding="utf-8")

        original_fetch = discovery_runner.fetch_raw_candidates
        original_score = discovery_runner.score_candidates_batch

        async def fail_fetch(*args, **kwargs):
            raise AssertionError("Should not call fetch when cache exists")

        async def fail_score(*args, **kwargs):
            raise AssertionError("Should not call score when cache exists")

        discovery_runner.fetch_raw_candidates = fail_fetch
        discovery_runner.score_candidates_batch = fail_score

        try:
            batch = __import__("asyncio").run(
                discovery_runner.run_discovery(
                    session=None,
                    log=logging.getLogger("test_discovery_runner_cache"),
                    output_dir=outdir,
                    niche_hint="test",
                    top_n=1,
                )
            )
            assert batch is not None
            assert len(batch.candidates) == 1
            assert batch.candidates[0].topic == "Cached Topic"
        finally:
            discovery_runner.fetch_raw_candidates = original_fetch
            discovery_runner.score_candidates_batch = original_score


def test_run_discovery_handles_empty_raw_candidates():
    with TemporaryDirectory() as tmpdir:
        outdir = Path(tmpdir)

        original_fetch = discovery_runner.fetch_raw_candidates

        async def empty_fetch(*args, **kwargs):
            return []

        discovery_runner.fetch_raw_candidates = empty_fetch

        try:
            batch = __import__("asyncio").run(
                discovery_runner.run_discovery(
                    session=None,
                    log=logging.getLogger("test_discovery_runner_empty"),
                    output_dir=outdir,
                    niche_hint="empty-case",
                    top_n=5,
                )
            )
            assert batch.returned_candidate_count == 0
        finally:
            discovery_runner.fetch_raw_candidates = original_fetch


def main():
    tests = [
        test_run_discovery_writes_candidates_json,
        test_run_discovery_uses_cache_on_second_run,
        test_run_discovery_handles_empty_raw_candidates,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__} -> {e}")
            failed += 1

    print(f"\\nSUMMARY: passed={passed}, failed={failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()