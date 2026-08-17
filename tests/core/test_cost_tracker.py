"""
Offline tests for provider-neutral cost accounting.

The single most important property under test: **reasoning tokens must never be
counted twice.** Gemini reports thoughts separately from its output count and
bills them at the output rate; OpenAI already folds reasoning INTO
``output_tokens``. The tracker resolves this by contract — ``output_tokens`` is
always already-billed output, and ``reasoning_tokens`` is reporting-only.

No network, no API keys.
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.core import cost_tracker as ct


@pytest.fixture(autouse=True)
def _clean_session():
    ct.reset_session()
    ct.set_active_job_dir(None)
    yield
    ct.reset_session()
    ct.set_active_job_dir(None)


# ---------------------------------------------------------------------------
# Pricing math
# ---------------------------------------------------------------------------

def test_cached_input_is_billed_at_the_discounted_tier():
    # gpt-5.6-luna: input 0.20, cached 0.02, output 1.20 (per 1M)
    cost = ct._cost_usd("gpt-5.6-luna", input_tokens=1000, output_tokens=500,
                        cached_input_tokens=400)
    expected = (600 * 0.20 + 400 * 0.02 + 500 * 1.20) / 1_000_000
    assert cost == pytest.approx(expected)


def test_cached_tokens_are_a_subset_not_an_addition():
    """400 cached out of 1000 must cost LESS than 1000 fresh, never more."""
    all_fresh = ct._cost_usd("gpt-5.6-luna", 1000, 500, cached_input_tokens=0)
    partly_cached = ct._cost_usd("gpt-5.6-luna", 1000, 500, cached_input_tokens=400)
    assert partly_cached < all_fresh


def test_cache_writes_cost_more_than_plain_input():
    """gpt-5.6 bills cache writes at 1.25x. Confirmed present in the live usage
    block as input_tokens_details.cache_write_tokens."""
    plain = ct._cost_usd("gpt-5.6-luna", 1000, 0)
    with_write = ct._cost_usd("gpt-5.6-luna", 1000, 0, cache_write_tokens=1000)
    assert with_write == pytest.approx(plain * ct._CACHE_WRITE_MULTIPLIER)
    assert with_write > plain, "ignoring cache writes under-reports the first call of a run"


def test_cache_reads_and_writes_are_both_subsets_of_input():
    """400 read + 200 written out of 1000 leaves 400 billed at the plain rate."""
    cost = ct._cost_usd("gpt-5.6-luna", input_tokens=1000, output_tokens=0,
                        cached_input_tokens=400, cache_write_tokens=200)
    expected = (400 * 0.20 + 400 * 0.02 + 200 * 0.20 * 1.25) / 1_000_000
    assert cost == pytest.approx(expected)


def test_model_alias_resolves_to_a_real_price():
    assert ct._cost_usd("gpt-5.6", 1000, 1000) == ct._cost_usd("gpt-5.6-sol", 1000, 1000)


def test_unknown_model_prices_at_the_most_expensive_known_rate(caplog):
    """Over-report loudly; never under-report silently."""
    with caplog.at_level("WARNING"):
        cost = ct._cost_usd("some-future-model-v9", input_tokens=1000, output_tokens=1000)

    max_in = max(r["input"] for r in ct._PRICING.values())
    max_out = max(r["output"] for r in ct._PRICING.values())
    assert cost == pytest.approx((1000 * max_in + 1000 * max_out) / 1_000_000)
    assert any("No pricing entry" in r.message for r in caplog.records)


def test_unknown_model_warns_only_once():
    ct._cost_usd("mystery-model", 10, 10)
    assert "mystery-model" in ct._WARNED_UNKNOWN_MODELS
    # Second call must not re-add (set semantics) — proves the one-shot guard.
    ct._cost_usd("mystery-model", 10, 10)
    assert len([m for m in ct._WARNED_UNKNOWN_MODELS if m == "mystery-model"]) == 1


# ---------------------------------------------------------------------------
# The double-counting contract
# ---------------------------------------------------------------------------

def test_reasoning_tokens_never_affect_cost():
    """reasoning_tokens is reporting-only. Same billed output => same cost."""
    ct.track_llm_call(phase="a", provider="openai", model="gpt-5.6-luna",
                      input_tokens=1000, output_tokens=2000, reasoning_tokens=0)
    cost_without = ct.get_session_totals()["total_cost_usd"]

    ct.reset_session()
    ct.track_llm_call(phase="a", provider="openai", model="gpt-5.6-luna",
                      input_tokens=1000, output_tokens=2000, reasoning_tokens=1500)
    cost_with = ct.get_session_totals()["total_cost_usd"]

    assert cost_with == pytest.approx(cost_without)


def test_gemini_call_site_convention_bills_thoughts_exactly_once():
    """Mirrors what the Gemini call sites do: output = candidates + thoughts."""
    candidates, thoughts = 800, 1200
    ct.track_llm_call(
        phase="scripting_draft", provider="gemini", model="gemini-2.5-pro",
        input_tokens=5000,
        output_tokens=candidates + thoughts,   # already-billed output
        reasoning_tokens=thoughts,             # reporting only
    )
    expected = (5000 * 1.25 + (candidates + thoughts) * 10.00) / 1_000_000
    assert ct.get_session_totals()["total_cost_usd"] == pytest.approx(expected)


def test_openai_call_site_convention_does_not_re_add_reasoning():
    """OpenAI's output_tokens already contains reasoning — pass it through as-is."""
    output_tokens, reasoning = 2000, 1500  # reasoning is INSIDE output_tokens
    ct.track_llm_call(
        phase="scripting_doctor", provider="openai", model="gpt-5.6-luna",
        input_tokens=5000, output_tokens=output_tokens, reasoning_tokens=reasoning,
    )
    expected = (5000 * 0.20 + output_tokens * 1.20) / 1_000_000
    assert ct.get_session_totals()["total_cost_usd"] == pytest.approx(expected)


def test_totals_accumulate_across_calls():
    ct.track_llm_call(phase="a", provider="openai", model="gpt-5.6-luna",
                      input_tokens=100, output_tokens=50, cached_input_tokens=20,
                      reasoning_tokens=10)
    ct.track_llm_call(phase="b", provider="openai", model="gpt-5.6-luna",
                      input_tokens=200, output_tokens=80, cached_input_tokens=30,
                      reasoning_tokens=25)
    t = ct.get_session_totals()
    assert t["total_input"] == 300
    assert t["total_output"] == 130
    assert t["total_cached_input"] == 50
    assert t["total_reasoning"] == 35


def test_tracking_never_raises_on_bad_input():
    """Accounting is fire-and-forget — it must never take the pipeline down."""
    ct.track_llm_call(phase="a", provider="openai", model="gpt-5.6-luna",
                      input_tokens=None, output_tokens=None)  # type: ignore[arg-type]
    # No exception is the assertion.


# ---------------------------------------------------------------------------
# JSONL writing via the active job dir
# ---------------------------------------------------------------------------

def test_active_job_dir_writes_jsonl(tmp_path):
    ct.set_active_job_dir(tmp_path)
    ct.track_llm_call(phase="extraction", provider="openai", model="gpt-5.6-luna",
                      input_tokens=1000, output_tokens=500, cached_input_tokens=100,
                      reasoning_tokens=200)

    cost_file = tmp_path / "logs" / "cost.jsonl"
    assert cost_file.exists(), "no JSONL written — this is the bug Phase 0 exists to fix"

    rec = json.loads(cost_file.read_text(encoding="utf-8").strip())
    assert rec["provider"] == "openai"
    assert rec["model"] == "gpt-5.6-luna"
    assert rec["input_tokens"] == 1000
    assert rec["cached_input_tokens"] == 100
    assert rec["reasoning_tokens"] == 200
    assert rec["cost_usd"] > 0


def test_no_active_job_dir_means_no_file(tmp_path):
    ct.set_active_job_dir(None)
    ct.track_llm_call(phase="a", provider="openai", model="gpt-5.6-luna",
                      input_tokens=10, output_tokens=10)
    assert not (tmp_path / "logs" / "cost.jsonl").exists()


def test_explicit_job_dir_overrides_the_active_one(tmp_path):
    active, explicit = tmp_path / "active", tmp_path / "explicit"
    ct.set_active_job_dir(active)
    ct.track_llm_call(phase="a", provider="openai", model="gpt-5.6-luna",
                      input_tokens=10, output_tokens=10, job_dir=explicit)
    assert (explicit / "logs" / "cost.jsonl").exists()
    assert not (active / "logs" / "cost.jsonl").exists()


def test_session_summary_names_the_models_used():
    ct.track_llm_call(phase="a", provider="openai", model="gpt-5.6-luna",
                      input_tokens=10, output_tokens=10)
    summary = ct.get_session_summary(configured_rpm=60)
    assert "openai:gpt-5.6-luna" in summary
    assert "LLM USAGE" in summary


def test_session_summary_with_no_calls():
    assert "No LLM API calls" in ct.get_session_summary()
