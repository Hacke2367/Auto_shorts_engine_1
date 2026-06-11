"""
Phase 1 — Summary-First routing + cost-trim regression tests (OFFLINE / no API).
================================================================================
Validates the discovery overhaul purely with fake LLM payloads — no Gemini/Tavily
calls, no API keys spent. Covers:

  1. Summary-First parsing: data_summary captured, template routed, fit_reason
     populated from template_reasoning.
  2. Backward compatibility: an old-format response (fit_reason, no data_summary)
     still parses without crashing.
  3. Robustness: markdown-fenced JSON parses; malformed JSON / invalid template
     return None instead of raising (advice: keep json.loads bulletproof).
  4. Prompt wiring: the rich template menu hides fallbacks; scoring prompt carries
     the word-caps + Summary-First steps; ideation prompt carries the Story Lenses.
  5. Ideation extractor: _extract_json_array tolerates fences/prose/garbage.
  6. Bias audit: tools.phase1_quality_check.audit_candidates flags template skew.

Run directly:   python tests/phase1/test_summary_first_routing.py
Or via pytest:  python -m pytest tests/phase1/test_summary_first_routing.py -v
"""

import json
import sys
from pathlib import Path

# Ensure project root on path when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agents.phase1_discovery.candidate_score import (
    _parse_scoring_response,
    _build_template_list,
    _SCORING_PROMPT_TEMPLATE,
)
from src.agents.phase1_discovery.discovery_runner import (
    _extract_json_array,
    _IDEATION_PROMPT,
)
from tools.phase1_quality_check import audit_candidates


# --------------------------------------------------------------------------- #
# 1. Summary-First parsing                                                      #
# --------------------------------------------------------------------------- #
def test_summary_first_parsing_captures_bridge_and_routes():
    resp = json.dumps({
        "data_summary": "Ranked revenues of 8 banks",
        "template_reasoning": "ranked list of 8 -> bar_chart",
        "best_fit_template": "bar_chart",
        "rationale": "Clear ranking with a surprising leader.",
        "validation_confidence": "high",
        "hook_potential_score": 9,
        "novelty_score": 7,
        "visual_fit_score": 8,
        "data_feasibility_score": 8,
        "freshness_score": 7,
        "source_hint": "annual reports",
    })
    c = _parse_scoring_response(resp, "The 8 biggest banks by revenue", "evidence...")
    assert c is not None
    assert c.best_fit_template == "bar_chart"
    assert c.data_summary == "Ranked revenues of 8 banks"          # bridge captured
    assert c.fit_reason == "ranked list of 8 -> bar_chart"          # mapped from template_reasoning
    assert c.fallback_template is not None                          # Python-owned, not from LLM
    assert c.hook_potential_score == 9.0
    return "summary captured + routed + fallback computed in Python"


def test_routes_two_entity_to_vs_card():
    resp = json.dumps({
        "data_summary": "1v1 of two banks across 6 metrics",
        "template_reasoning": "2 entities -> vs_card",
        "best_fit_template": "vs_card",
        "rationale": "Head to head rivalry.",
        "validation_confidence": "high",
        "hook_potential_score": 8, "novelty_score": 7, "visual_fit_score": 9,
        "data_feasibility_score": 7, "freshness_score": 6,
        "source_hint": "filings",
    })
    c = _parse_scoring_response(resp, "Bank A vs Bank B", "evidence")
    assert c is not None and c.best_fit_template == "vs_card"
    return "2-entity data routed to vs_card"


# --------------------------------------------------------------------------- #
# 2. Backward compatibility (old prompt format)                                #
# --------------------------------------------------------------------------- #
def test_legacy_fit_reason_still_parses():
    # Old format: no data_summary / template_reasoning, only fit_reason.
    resp = json.dumps({
        "rationale": "Strong rivalry.",
        "validation_confidence": "high",
        "hook_potential_score": 9, "novelty_score": 7, "visual_fit_score": 9,
        "data_feasibility_score": 8, "freshness_score": 8,
        "best_fit_template": "vs_card",
        "fit_reason": "Two-entity rivalry.",
        "source_hint": "reports",
    })
    c = _parse_scoring_response(resp, "Nvidia vs AMD", "Nvidia $20B, AMD $4B")
    assert c is not None
    assert c.best_fit_template == "vs_card"
    assert c.fit_reason == "Two-entity rivalry."   # falls back to legacy key
    assert c.data_summary is None                  # absent, but no crash
    return "legacy response parses without crashing"


# --------------------------------------------------------------------------- #
# 3. Robustness                                                                 #
# --------------------------------------------------------------------------- #
def test_markdown_fenced_scoring_response_parses():
    inner = {
        "data_summary": "One budget split into 5 parts",
        "template_reasoning": "parts of a whole -> donut_breakdown",
        "best_fit_template": "donut_breakdown",
        "rationale": "Where the money goes.",
        "validation_confidence": "medium",
        "hook_potential_score": 7, "novelty_score": 6, "visual_fit_score": 8,
        "data_feasibility_score": 6, "freshness_score": 5,
        "source_hint": "budget data",
    }
    wrapped = "```json\n" + json.dumps(inner) + "\n```"
    c = _parse_scoring_response(wrapped, "Where every rupee goes", "evidence")
    assert c is not None and c.best_fit_template == "donut_breakdown"
    return "markdown-fenced scoring JSON still parses"


def test_malformed_and_invalid_template_return_none():
    assert _parse_scoring_response("this is not json", "t", "s") is None
    bad_tpl = json.dumps({
        "data_summary": "x", "template_reasoning": "y",
        "best_fit_template": "pie_3d_explosion",   # not a real template
        "rationale": "z", "validation_confidence": "low",
        "hook_potential_score": 5, "novelty_score": 5, "visual_fit_score": 5,
        "data_feasibility_score": 5, "freshness_score": 5, "source_hint": "h",
    })
    assert _parse_scoring_response(bad_tpl, "t", "s") is None
    return "malformed JSON and invalid template both rejected (None, no raise)"


# --------------------------------------------------------------------------- #
# 4. Prompt wiring                                                              #
# --------------------------------------------------------------------------- #
def test_template_menu_hides_fallbacks_shows_shapes():
    menu = _build_template_list()
    assert "Fallbacks" not in menu and "fallbacks" not in menu   # dead tokens removed
    for t in ("bar_chart", "vs_card", "donut_breakdown", "geo_universal",
              "scan_race", "sort_card", "butterfly_chart"):
        assert t in menu                                         # all 7 present
    assert "ideal" in menu and "max" in menu                     # capacities shown
    return "template menu: 7 shapes + capacities, no fallback tokens"


def test_scoring_prompt_has_caps_and_summary_first():
    p = _SCORING_PROMPT_TEMPLATE
    assert "Summary-First" in p
    assert "MAX 15 words" in p and "MAX 10 words" in p and "MAX 20 words" in p
    assert "Derived-metric" in p or "derived" in p
    return "scoring prompt carries Summary-First + word caps + derived rule"


def test_ideation_prompt_has_story_lenses():
    p = _IDEATION_PROMPT
    for lens in ("THE RIVALRY", "THE AUTOPSY", "THE SHIFT", "THE MAP",
                 "THE LEADERBOARD", "THE SLEEPER"):
        assert lens in p
    assert "not quotas" in p or "NOT quotas" in p     # organic, not forced
    return "ideation prompt carries all 6 story lenses (no quotas)"


# --------------------------------------------------------------------------- #
# 5. Ideation JSON extractor                                                    #
# --------------------------------------------------------------------------- #
def test_extract_json_array_robustness():
    assert _extract_json_array('["a", "b"]') == ["a", "b"]
    assert _extract_json_array('```json\n["x","y"]\n```') == ["x", "y"]
    assert _extract_json_array('Here you go:\n["p","q"]\nThanks!') == ["p", "q"]
    assert _extract_json_array("not json at all") == []
    assert _extract_json_array("") == []
    return "extractor handles plain/fenced/prose and degrades to [] on garbage"


# --------------------------------------------------------------------------- #
# 6. Bias audit                                                                  #
# --------------------------------------------------------------------------- #
def _cand(tpl, summary="A ranked list of 7 items", feas=8, conf="high", final=7.0):
    return {
        "topic": f"topic-{tpl}", "best_fit_template": tpl, "data_summary": summary,
        "fit_reason": "ranked -> " + tpl, "rationale": "short why",
        "data_feasibility_score": feas, "validation_confidence": conf, "final_score": final,
    }


def test_audit_flags_template_bias():
    skewed = [_cand("bar_chart") for _ in range(7)] + [
        _cand("vs_card"), _cand("sort_card"), _cand("donut_breakdown")]
    rep = audit_candidates(skewed)
    assert rep["bias_warning"] is True                 # 7/10 bar_chart > 60%
    assert rep["dominant_template"] == "bar_chart"

    balanced = [_cand("bar_chart"), _cand("bar_chart"), _cand("vs_card"),
                _cand("donut_breakdown"), _cand("geo_universal"), _cand("sort_card")]
    assert audit_candidates(balanced)["bias_warning"] is False
    return "audit flags >60% single-template skew, passes a balanced spread"


def test_audit_catches_wordcap_and_scoring_violations():
    bad = [
        _cand("bar_chart", summary=" ".join(["word"] * 20)),       # 20w > 15 cap
        _cand("vs_card", feas=3, conf="high"),                      # feas<5 but not low
    ]
    rep = audit_candidates(bad)
    assert any("data_summary" in v for v in rep["word_violations"])
    assert any("confidence" in v for v in rep["score_violations"])
    return "audit catches word-cap overrun + feasibility/confidence rule break"


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
