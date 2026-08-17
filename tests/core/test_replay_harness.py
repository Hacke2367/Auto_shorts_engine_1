"""
Offline execution test for scripts/replay_harness.py.

The harness is the tool that spends real money. If it has a bug, you find out
AFTER the paid call — which is exactly how a `sorted()` over pydantic models got
caught here. So every replay path is executed end-to-end against a stubbed LLM
before a single token is bought.

The stub's canned "model output" is built FROM the archived Gemini artifacts, so
the shapes under test are the real ones the harness will meet, not invented ones.

No network, no API keys.
"""

import asyncio
import functools
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for p in (PROJECT_ROOT, PROJECT_ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import replay_harness as rh  # noqa: E402
from src.agents.core import cost_tracker as ct  # noqa: E402
from src.agents.core import llm_client  # noqa: E402
from src.agents.core.llm_client import LLMResult  # noqa: E402

# NEITHER archived sort_card dataset satisfies the renderer contract — Gemini got
# the category values wrong in _1 and the 'A vs B' TITLE format wrong in _2. So
# sort_card is used only as the Phase 2 (scripting) canary, where its script.json
# IS valid and carries the strictest structure in the repo: 11 tags in exact order.
# vs_card_3 is the extraction baseline: it carries a real semantic constraint
# (winner must be 0/1/2) and is the one archived dataset that passes it.
SORT_CARD = PROJECT_ROOT / "jobs" / "sort_card" / "sort_card_1"
VS_CARD_VALID = PROJECT_ROOT / "jobs" / "vs_card" / "vs_card_3"
AUTO_JOB = PROJECT_ROOT / "jobs" / "auto" / "auto_8"

pytestmark = pytest.mark.skipif(
    not SORT_CARD.exists() or not AUTO_JOB.exists() or not VS_CARD_VALID.exists(),
    reason="archived replay fixtures not present in this checkout",
)


def _sync(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        return asyncio.run(fn(*a, **kw))
    return wrapper


# ---------------------------------------------------------------------------
# Canned responses, derived from the archived Gemini artifacts
# ---------------------------------------------------------------------------


def _archived_dataset_json(template: str = "vs_card") -> str:
    job = VS_CARD_VALID if template == "vs_card" else SORT_CARD
    raw = json.loads(
        (job / "data" / "best_fit" / f"{template}_dataset.json").read_text(encoding="utf-8")
    )
    return json.dumps({
        "meta": raw.get("meta", {}),
        "rows": raw.get("rows", []),
        "image_sourcing_guide": raw.get("image_sourcing_guide", {}),
    })


def _archived_monologue() -> str:
    script = json.loads((SORT_CARD / "script" / "script.json").read_text(encoding="utf-8"))
    body = "".join(f"<{s['tag']}>{s['text']}</{s['tag']}>" for s in script["segments"])
    return f"<MONOLOGUE>{body}</MONOLOGUE>"


_SCORING_JSON = json.dumps({
    "data_summary": "Ranked list of seven payment networks by volume",
    "template_reasoning": "ranked list of 7 -> bar_chart",
    "best_fit_template": "bar_chart",
    "rationale": "Surprising ordering that contradicts the popular assumption",
    "validation_confidence": "high",
    "hook_potential_score": 8,
    "novelty_score": 7,
    "visual_fit_score": 9,
    "data_feasibility_score": 8,
    "freshness_score": 7,
    "source_hint": "central bank annual report",
})

_IDEATION_JSON = json.dumps({"topics": [f"Topic number {i}" for i in range(10)]})


def _fake_response(cost_phase: str, user_prompt: str = "") -> str:
    if cost_phase == "ideation":
        return _IDEATION_JSON
    if cost_phase == "scoring":
        return _SCORING_JSON
    if cost_phase == "extraction":
        # The extraction prompt names its template; echo back that template's
        # archived rows so the row-type check sees a realistic payload.
        return _archived_dataset_json("sort_card" if "sort_card" in user_prompt else "vs_card")
    if cost_phase == "replay_draft":
        return _archived_monologue()
    raise AssertionError(f"unexpected cost_phase {cost_phase!r}")


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    """Intercept every route at one point.

    All four call sites reach `call_llm`, which resolves `call_llm_raw` through
    the module globals — so replacing it here covers ideation, scoring,
    extraction and scripting at once.
    """
    async def fake_raw(system_prompt, user_prompt, session, log,
                       phase_model, cost_phase, **kwargs):
        # Bill something realistic so _spend() is exercised, and make the amount
        # depend on effort so the sweep's cost column is not trivially constant.
        effort = phase_model.reasoning_effort or "low"
        reasoning = {"minimal": 50, "low": 200, "medium": 900, "high": 2600}.get(effort, 200)
        ct.track_llm_call(
            phase=cost_phase, provider=phase_model.provider, model=phase_model.model,
            input_tokens=1000, output_tokens=400 + reasoning,
            cached_input_tokens=200, reasoning_tokens=reasoning,
        )
        return LLMResult(text=_fake_response(cost_phase, user_prompt),
                         usage={}, raw={}, status="completed")

    monkeypatch.setattr(llm_client, "call_llm_raw", fake_raw)
    ct.reset_session()
    ct.set_active_job_dir(None)
    yield
    ct.reset_session()


@pytest.fixture(autouse=True)
def _reports_to_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(rh, "REPORT_DIR", tmp_path / "validation")


# ---------------------------------------------------------------------------
# Every replay path must execute cleanly
# ---------------------------------------------------------------------------


@_sync
async def test_ideation_replay_runs_and_scores():
    r = await rh._run_cell("ideation", type("A", (), {"niche": "finance", "count": 10})(), "low")
    assert r["quality"]["parsed"] is True
    assert r["quality"]["returned"] == 10
    assert r["quality"]["count_within_20pct"] is True
    assert r["score"] > 0
    assert r["spend"]["cost_usd"] > 0


@_sync
async def test_scoring_replay_compares_against_the_gemini_baseline():
    args = type("A", (), {"job": AUTO_JOB, "n": 2})()
    r = await rh._run_cell("scoring", args, "low")
    assert r["quality"]["parse_rate"] == 1.0
    # The archived candidates.json must actually have been consulted.
    assert "/" in r["quality"]["template_agreement"], "baseline comparison did not run"
    assert r["quality"]["word_cap_respected"] == "2/2"
    assert len(r["rows"]) == 2


@_sync
async def test_extraction_replay_validates_schema_and_semantics():
    args = type("A", (), {"job": VS_CARD_VALID})()
    r = await rh._run_cell("extraction", args, "medium")
    q = r["quality"]
    assert q["schema_valid"] is True
    assert q["semantics_valid"] is True, q["semantics_reason"]
    assert q["rows_in_capacity"] is True
    assert q["gemini_baseline_valid"] is True
    assert r["score"] == 10.0


@_sync
async def test_extraction_reports_when_the_gemini_baseline_is_itself_invalid():
    """sort_card_1 pre-dates the renderer-contract fix. The report must say so,
    or 'OpenAI differs from Gemini' gets misread as 'OpenAI is wrong'."""
    args = type("A", (), {"job": SORT_CARD})()
    r = await rh._run_cell("extraction", args, "low")
    assert r["quality"]["gemini_baseline_valid"] is False


@_sync
async def test_draft_replay_measures_structure_not_just_success():
    """This is the path that hid the sorted()-over-pydantic-models crash."""
    args = type("A", (), {"job": SORT_CARD, "persona": "hyper_analyst"})()
    r = await rh._run_cell("draft", args, "medium")
    q = r["quality"]
    assert q["parsed"] is True
    assert q["tags"] == "11/11", "sort_card is the 11-tag canary"
    assert isinstance(q["failing_tags"], list)
    assert all(isinstance(t, str) for t in q["failing_tags"]), "tags must be plain strings"
    assert q["markdown_fences"] is False
    assert q["chars_per_word"] > 0, "the _CHARS_PER_WORD recalibration must be computed"


# ---------------------------------------------------------------------------
# Sweep mechanics — the part that decides right-sizing
# ---------------------------------------------------------------------------


@_sync
async def test_effort_override_is_applied_then_restored():
    from src.agents.core.config import APP_CONFIG
    before = APP_CONFIG.llm.scripting_draft.reasoning_effort
    args = type("A", (), {"job": SORT_CARD, "persona": "hyper_analyst"})()

    r = await rh._run_cell("draft", args, "high")

    assert r["effort"] == "high", "the sweep must actually change the effort"
    assert APP_CONFIG.llm.scripting_draft.reasoning_effort == before, (
        "the override leaked — later cells would be measured at the wrong effort"
    )


@_sync
async def test_identical_output_across_efforts_yields_identical_hash():
    """This equality is what the report turns into a 'waste' verdict."""
    args = type("A", (), {"job": SORT_CARD, "persona": "hyper_analyst"})()
    low = await rh._run_cell("draft", args, "low")
    high = await rh._run_cell("draft", args, "high")

    assert low["output_hash"] == high["output_hash"]
    assert high["spend"]["reasoning_tokens"] > low["spend"]["reasoning_tokens"]


@_sync
async def test_spend_is_measured_per_cell_not_cumulatively():
    args = type("A", (), {"job": SORT_CARD, "persona": "hyper_analyst"})()
    first = await rh._run_cell("draft", args, "low")
    second = await rh._run_cell("draft", args, "low")
    assert first["spend"]["cost_usd"] == pytest.approx(second["spend"]["cost_usd"]), (
        "cost accounting must reset between cells, or later efforts look inflated"
    )
    assert first["spend"]["calls"] == 1


# ---------------------------------------------------------------------------
# The report reader
# ---------------------------------------------------------------------------


def test_compare_report_labels_waste_and_knee(tmp_path):
    import compare_report as cr

    cells = []
    for effort, reasoning in (("low", 200), ("medium", 900), ("high", 2600)):
        for rep in (1, 2):
            cells.append({
                "effort": effort, "score": 10.0, "output_hash": "SAME",
                "model": "gpt-5.6-luna", "rep": rep,
                "spend": {"reasoning_tokens": reasoning, "cached_input_tokens": 100,
                          "cost_usd": 0.001 * reasoning, "calls": 1},
            })
    rows = cr._verdict_rows(cells)

    assert rows[0]["effort"] == "low"
    assert rows[0]["verdict"].startswith("knee")
    assert all("waste" in r["verdict"] for r in rows[1:]), (
        "identical output at higher effort must be called out as waste"
    )


def test_compare_report_flags_noisy_quality_not_merely_different_text():
    """Different wording between reps is normal for a generative route; only a
    swing in QUALITY is a reason to distrust the cell."""
    import compare_report as cr

    cells = [
        {"effort": "low", "score": 9.0, "output_hash": "A", "model": "m", "rep": 1,
         "spend": {"reasoning_tokens": 200, "cached_input_tokens": 0, "cost_usd": 0.001}},
        {"effort": "low", "score": 6.0, "output_hash": "B", "model": "m", "rep": 2,
         "spend": {"reasoning_tokens": 200, "cached_input_tokens": 0, "cost_usd": 0.001}},
    ]
    rows = cr._verdict_rows(cells)
    assert rows[0]["verdict"].startswith("noisy")
    assert rows[0]["hash"] == "varies"


def test_identical_output_is_only_claimed_when_a_real_hash_matches():
    """Two cells that each vary internally are both 'varies' — that is NOT proof
    the higher effort produced the same output."""
    import compare_report as cr

    cells = []
    for effort, reasoning in (("low", 200), ("high", 2000)):
        for rep, h in enumerate(("A", "B"), start=1):
            cells.append({
                "effort": effort, "score": 10.0, "output_hash": f"{h}{effort}",
                "model": "m", "rep": rep,
                "spend": {"reasoning_tokens": reasoning, "cached_input_tokens": 0,
                          "cost_usd": 0.001 * reasoning},
            })
    rows = cr._verdict_rows(cells)
    high = next(r for r in rows if r["effort"] == "high")
    assert high["verdict"] == "waste (no quality gain)", high["verdict"]


def test_compare_report_marks_lower_quality_as_under():
    import compare_report as cr

    cells = [
        {"effort": "low", "score": 5.0, "output_hash": "A", "model": "m", "rep": 1,
         "spend": {"reasoning_tokens": 100, "cached_input_tokens": 0, "cost_usd": 0.0005}},
        {"effort": "high", "score": 10.0, "output_hash": "B", "model": "m", "rep": 1,
         "spend": {"reasoning_tokens": 2000, "cached_input_tokens": 0, "cost_usd": 0.004}},
    ]
    rows = cr._verdict_rows(cells)
    assert rows[0]["verdict"] == "under"
    assert rows[1]["verdict"].startswith("knee")
