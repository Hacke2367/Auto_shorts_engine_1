"""
Offline tests for tools/cost_report.py.

Two regressions this file locks down:

1. ``cost_report`` used to carry its OWN pricing table that disagreed with
   ``cost_tracker`` by 4x on Flash input (0.075 vs 0.30). It must now import the
   one table, so the numbers you read can never drift from the numbers you pay.
2. ``log_cost()`` in src/cli/autoshorts.py writes phase/step markers with no
   token fields into the same cost.jsonl. Counting those as API calls inflated
   "Total API calls" on every report.

No network, no API keys.
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import cost_report  # noqa: E402
from src.agents.core import cost_tracker as ct  # noqa: E402


# ---------------------------------------------------------------------------
# Single source of truth for pricing
# ---------------------------------------------------------------------------

def test_cost_report_uses_the_tracker_pricing_table():
    """The 4x Flash divergence must be structurally impossible now."""
    assert cost_report._PRICING is ct._PRICING


def test_cost_report_uses_the_tracker_cost_function():
    assert cost_report._cost_usd is ct._cost_usd


# ---------------------------------------------------------------------------
# Record normalization across historical schemas
# ---------------------------------------------------------------------------

def test_token_less_step_markers_are_skipped():
    """This is exactly what src/cli/autoshorts.py log_cost() writes."""
    marker = {
        "timestamp": "2026-01-01T00:00:00Z", "phase": "phase1", "step": "extraction",
        "provider": "unknown", "model": "unknown", "status": "start", "notes": "",
    }
    assert cost_report._normalize(marker) is None


def test_legacy_record_folds_thinking_into_billed_output():
    """Legacy Gemini records stored thoughts separately; Gemini bills them as output."""
    legacy = {
        "phase": "scripting_draft", "model": "gemini-2.5-pro",
        "prompt_tokens": 5000, "output_tokens": 800, "thinking_tokens": 1200,
        "cost_usd": 0.0,  # deliberately wrong; normalization must not silently trust it
    }
    norm = cost_report._normalize(legacy)
    assert norm is not None
    assert norm["input_tokens"] == 5000
    assert norm["output_tokens"] == 2000        # 800 + 1200
    assert norm["reasoning_tokens"] == 1200
    assert norm["provider"] == "gemini"          # inferred from the model name


def test_legacy_record_without_cost_gets_it_recomputed():
    legacy = {
        "phase": "scoring", "model": "gemini-2.5-flash",
        "prompt_tokens": 1000, "output_tokens": 500,
    }
    norm = cost_report._normalize(legacy)
    expected = (1000 * 0.30 + 500 * 2.50) / 1_000_000
    assert norm["cost_usd"] == pytest.approx(expected)


def test_current_record_passes_through_without_re_adding_reasoning():
    current = {
        "phase": "scripting_doctor", "provider": "openai", "model": "gpt-5.6-luna",
        "input_tokens": 5000, "cached_input_tokens": 3500,
        "output_tokens": 2000, "reasoning_tokens": 1500, "cost_usd": 0.0031,
    }
    norm = cost_report._normalize(current)
    assert norm["output_tokens"] == 2000     # NOT 2000 + 1500
    assert norm["cached_input_tokens"] == 3500
    assert norm["cost_usd"] == 0.0031


# ---------------------------------------------------------------------------
# End-to-end over a synthetic cost.jsonl holding BOTH schemas
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )


def test_mixed_schema_file_counts_only_real_api_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(cost_report, "JOBS_ROOT", tmp_path)
    _write_jsonl(tmp_path / "job_1" / "logs" / "cost.jsonl", [
        # step markers — must not be counted as calls
        {"phase": "phase1", "step": "extraction", "provider": "unknown",
         "model": "unknown", "status": "start"},
        {"phase": "phase2", "step": "script_generation", "provider": "unknown",
         "model": "unknown", "status": "success"},
        # legacy Gemini call
        {"phase": "extraction", "model": "gemini-2.5-flash",
         "prompt_tokens": 9000, "output_tokens": 1500, "thinking_tokens": 500},
        # current OpenAI call
        {"phase": "scripting_draft", "provider": "openai", "model": "gpt-5.6-luna",
         "input_tokens": 5000, "cached_input_tokens": 0,
         "output_tokens": 2300, "reasoning_tokens": 1000, "cost_usd": 0.00376},
    ])

    records, skipped = cost_report._load_all_records(None)
    assert skipped == 2, "step markers should be reported separately, not as calls"
    assert len(records) == 2

    by_phase = {r["phase"]: r for r in records}
    assert by_phase["extraction"]["output_tokens"] == 2000   # 1500 + 500 thinking
    assert by_phase["scripting_draft"]["output_tokens"] == 2300  # reasoning not re-added
    assert all(r["job_id"] == "job_1" for r in records)


def test_report_renders_without_crashing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cost_report, "JOBS_ROOT", tmp_path)
    _write_jsonl(tmp_path / "job_1" / "logs" / "cost.jsonl", [
        {"phase": "scoring", "provider": "openai", "model": "gpt-5.6-luna",
         "input_tokens": 1200, "cached_input_tokens": 1000,
         "output_tokens": 300, "reasoning_tokens": 150, "cost_usd": 0.0004},
    ])
    records, skipped = cost_report._load_all_records(None)
    cost_report._print_report(records, skipped)

    out = capsys.readouterr().out
    assert "HISTORICAL LLM COST REPORT" in out
    assert "openai:gpt-5.6-luna" in out
    assert "cached" in out


def test_empty_report_mentions_skipped_markers(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cost_report, "JOBS_ROOT", tmp_path)
    _write_jsonl(tmp_path / "job_1" / "logs" / "cost.jsonl", [
        {"phase": "phase1", "step": "extraction", "status": "start"},
    ])
    records, skipped = cost_report._load_all_records(None)
    cost_report._print_report(records, skipped)

    out = capsys.readouterr().out
    assert "No LLM cost records found" in out
    assert "1 pipeline step markers" in out
