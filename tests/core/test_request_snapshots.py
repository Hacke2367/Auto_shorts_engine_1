"""
Golden request-body snapshots for all six LLM routes.

This is the single highest-value offline test for a provider migration: it builds
the EXACT body each route would put on the wire and asserts it, so one run
catches every category of routing bug at once —

* a leaked ``temperature`` (a hard 400 on gpt-5.x)
* a missing or wrong ``reasoning.effort`` (the cost dial; default is "medium")
* the wrong JSON schema attached to the wrong route, or attached to the XML route
* a wrong model id after an edit to LLMConfig
* dynamic content leaking into the cached prompt prefix
* a ``max_output_tokens`` regression (on OpenAI it caps reasoning too, so a value
  ported from Gemini can be eaten entirely by thinking)

No network, no API keys.
"""

import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.core import llm_client  # noqa: E402
from src.agents.core.config import APP_CONFIG, GEMINI_ROUTES  # noqa: E402
from src.agents.core.llm_client import _gemini_build, _openai_build  # noqa: E402
from src.agents.core.llm_schemas import (  # noqa: E402
    IDEATION_SCHEMA,
    SCORING_SCHEMA,
    extraction_schema,
)

USER = "USER-PROMPT"
SYS = "SYSTEM-PROMPT"


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "openai_api_key", SecretStr("sk-test"), raising=False)
    monkeypatch.setattr(llm_client.settings, "gemini_api_key", SecretStr("gem-test"), raising=False)


# route name -> (system prompt, schema, expect_json, cache_key)
_ROUTE_CALLS = {
    "discovery_ideation": (None, IDEATION_SCHEMA, True, None),
    "discovery_scoring": (None, SCORING_SCHEMA, True, "as-scoring-v1"),
    "extraction": (None, extraction_schema("sort_card", True), True, None),
    "scripting_draft": (SYS, None, False, "as-p2-hyper_analyst"),
    "scripting_rewrite": (SYS, None, False, "as-p2-hyper_analyst"),
    "scripting_doctor": (SYS, None, False, "as-p2-hyper_analyst"),
}

# The committed golden: what each route must put on the wire.
_EXPECTED = {
    "discovery_ideation": {"model": "gpt-5.6-luna", "effort": "low", "verbosity": "medium",
                           "format": "json_schema", "schema_name": "topic_ideas"},
    "discovery_scoring": {"model": "gpt-5.6-luna", "effort": "low", "verbosity": "low",
                          "format": "json_schema", "schema_name": "candidate_score"},
    "extraction": {"model": "gpt-5.6-luna", "effort": "medium", "verbosity": "low",
                   "format": "json_schema", "schema_name": "sort_card_dataset"},
    "scripting_draft": {"model": "gpt-5.6-luna", "effort": "medium", "verbosity": "medium",
                        "format": None, "schema_name": None},
    "scripting_rewrite": {"model": "gpt-5.6-luna", "effort": "low", "verbosity": "low",
                          "format": None, "schema_name": None},
    "scripting_doctor": {"model": "gpt-5.6-luna", "effort": "high", "verbosity": "medium",
                         "format": None, "schema_name": None},
}

ROUTES = sorted(_ROUTE_CALLS)


def _build(route: str):
    cfg = getattr(APP_CONFIG.llm, route)
    system, schema, expect_json, cache_key = _ROUTE_CALLS[route]
    return _openai_build(cfg, system, USER, schema, expect_json, cache_key)


@pytest.mark.parametrize("route", ROUTES)
def test_route_body_matches_golden(route):
    _, headers, body = _build(route)
    want = _EXPECTED[route]

    assert body["model"] == want["model"]
    assert body["reasoning"] == {"effort": want["effort"]}, (
        "reasoning.effort is the cost dial — gpt-5.6 defaults to 'medium' when unset"
    )
    assert body["text"]["verbosity"] == want["verbosity"]
    assert headers["Authorization"] == "Bearer sk-test"

    fmt = body["text"].get("format")
    if want["format"] is None:
        assert fmt is None, f"{route} emits XML — no response format may be attached"
    else:
        assert fmt["type"] == want["format"]
        assert fmt["strict"] is True
        assert fmt["name"] == want["schema_name"]


@pytest.mark.parametrize("route", ROUTES)
def test_no_route_leaks_temperature(route):
    """gpt-5.x rejects `temperature` with HTTP 400 — some endpoints reject its
    mere presence. Combined with a blanket retry that is ~3 minutes per call."""
    _, _, body = _build(route)
    assert "temperature" not in body
    assert "top_p" not in body


@pytest.mark.parametrize("route", ROUTES)
def test_no_route_sets_max_output_tokens(route):
    """On OpenAI this caps reasoning AND visible output together. Every route
    currently leaves it unset so reasoning can never starve the answer."""
    _, _, body = _build(route)
    assert "max_output_tokens" not in body


@pytest.mark.parametrize("route", ROUTES)
def test_static_content_leads_the_input(route):
    """Prompt caching is prefix-based, so the stable part must come first."""
    _, _, body = _build(route)
    system, *_ = _ROUTE_CALLS[route]
    if system is None:
        assert body["input"] == [{"role": "user", "content": USER}]
    else:
        assert body["input"][0] == {"role": "system", "content": SYS}
        assert body["input"][-1] == {"role": "user", "content": USER}


def test_phase2_routes_share_one_cache_key():
    """Draft + rewrites + doctor reuse the same ~3.5K-token persona prefix across
    ~5 calls per run. A differing key per call throws that discount away."""
    keys = {
        _build(r)[2].get("prompt_cache_key")
        for r in ("scripting_draft", "scripting_rewrite", "scripting_doctor")
    }
    assert keys == {"as-p2-hyper_analyst"}


def test_cache_key_carries_no_dynamic_content():
    """A job id / timestamp in the key (or the prefix) silently turns the 10%
    cached rate back into 100% across every call in the run."""
    import re
    for route in ROUTES:
        key = _build(route)[2].get("prompt_cache_key")
        if key:
            assert not re.search(r"\d{4}-\d{2}-\d{2}|\d{10}", key), (
                f"{route}: cache key {key!r} looks like it embeds a date/timestamp"
            )


def test_all_six_routes_are_covered():
    """Guards against a route being added to LLMConfig without a snapshot."""
    from src.agents.core.config import PhaseModel
    configured = {
        name for name, v in APP_CONFIG.llm.__dict__.items() if isinstance(v, PhaseModel)
    }
    assert configured == set(ROUTES), f"snapshot coverage drift: {configured ^ set(ROUTES)}"


# ---------------------------------------------------------------------------
# The Gemini A/B arm must still build a valid legacy request
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_gemini_arm_reproduces_the_legacy_request(route):
    cfg = GEMINI_ROUTES[route]
    system, schema, expect_json, cache_key = _ROUTE_CALLS[route]
    url, headers, payload = _gemini_build(cfg, system, USER, schema, expect_json, cache_key)

    assert url.endswith(f"{cfg.model}:generateContent")
    assert headers["x-goog-api-key"] == "gem-test"
    assert "key=" not in url, "the API key must never ride in the query string"

    gen = payload["generationConfig"]
    assert gen["temperature"] == cfg.temperature, "Gemini still uses temperature"
    if cfg.thinking_budget is not None:
        assert gen["thinkingConfig"] == {"thinkingBudget": cfg.thinking_budget}
    # JSON mode on the Phase 1 routes, absent on the XML scripting routes.
    assert ("responseMimeType" in gen) is expect_json
