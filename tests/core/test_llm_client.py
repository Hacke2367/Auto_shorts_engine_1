"""
Offline tests for the shared LLM client — both adapters, no network.

The properties that matter most here are the ones that fail SILENTLY in
production if they regress:

* OpenAI puts the reasoning item FIRST in ``output[]`` — reading ``output[0]``
  gets the wrong item.
* An ``incomplete`` response can still carry partial text that parses cleanly.
* ``temperature`` on a gpt-5.x model is a hard 400, and because
  ``ClientResponseError`` subclasses ``ClientError`` a naive retry policy would
  turn that into six 4-45s waits per call.
* Gemini bills thoughts on TOP of its output count; OpenAI folds reasoning INTO
  it. Getting that backwards doubles or halves every cost number.
"""

import asyncio
import functools
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.core import cost_tracker as ct  # noqa: E402
from src.agents.core import llm_client  # noqa: E402
from src.agents.core.config import PhaseModel  # noqa: E402
from src.agents.core.llm_client import call_llm, call_llm_raw  # noqa: E402
from src.agents.core.llm_errors import (  # noqa: E402
    LLMBadRequestError,
    LLMIncompleteError,
    LLMMalformedResponseError,
    LLMRateLimitError,
    LLMRefusalError,
)
from src.agents.core.retry import standard_retry_policy  # noqa: E402

LOG = __import__("logging").getLogger("test_llm_client")


def _sync(fn):
    """Run an async test body via asyncio.run — matches the repo's existing style
    and keeps pytest-asyncio out of requirements.txt."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return wrapper


# ---------------------------------------------------------------------------
# Stub session
# ---------------------------------------------------------------------------


class _StubResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = ""):
        self.status = status
        self._payload = payload or {}
        self._text = text

    async def json(self):
        return self._payload

    async def text(self):
        return self._text

    def raise_for_status(self):
        if self.status >= 400:
            import aiohttp
            raise aiohttp.ClientResponseError(
                request_info=None, history=(), status=self.status,
                message=f"HTTP {self.status}",
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _StubSession:
    """Replays a scripted list of responses and records every request body."""

    def __init__(self, *responses: _StubResponse):
        self._responses = list(responses)
        self.requests: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "json": json, "headers": headers or {}, "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError("StubSession ran out of scripted responses")
        return self._responses.pop(0)

    @property
    def call_count(self) -> int:
        return len(self.requests)


def _fast_retry():
    """Retry policy with no real waiting, so failure paths stay instant."""
    return standard_retry_policy(min_wait=0, max_wait=0, max_attempts=3)


@pytest.fixture(autouse=True)
def _keys_and_session(monkeypatch):
    monkeypatch.setattr(
        llm_client.settings, "openai_api_key", SecretStr("sk-test"), raising=False
    )
    monkeypatch.setattr(
        llm_client.settings, "gemini_api_key", SecretStr("gem-test"), raising=False
    )
    ct.reset_session()
    ct.set_active_job_dir(None)
    yield
    ct.reset_session()


OPENAI_ROUTE = PhaseModel(
    provider="openai", model="gpt-5.6-luna", reasoning_effort="low", verbosity="low"
)
GEMINI_ROUTE = PhaseModel(
    provider="gemini", model="gemini-2.5-flash", temperature=0.4, thinking_budget=512
)


def _openai_ok(text="hello", usage=None, extra_output=None):
    output = [
        # Reasoning item comes FIRST — this ordering is the whole point.
        {"type": "reasoning", "id": "rs_1", "summary": []},
        {
            "type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text}],
        },
    ]
    if extra_output:
        output = extra_output
    return {
        "status": "completed",
        "output": output,
        "usage": usage or {
            "input_tokens": 1000,
            "output_tokens": 500,
            "input_tokens_details": {"cached_tokens": 400},
            "output_tokens_details": {"reasoning_tokens": 300},
        },
    }


def _gemini_ok(parts=None, finish="STOP", usage=None):
    return {
        "candidates": [{
            "finishReason": finish,
            "content": {"parts": parts if parts is not None else [{"text": "hello"}]},
        }],
        "usageMetadata": usage or {
            "promptTokenCount": 1000,
            "candidatesTokenCount": 500,
            "thoughtsTokenCount": 300,
        },
    }


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------


@_sync
async def test_openai_skips_the_reasoning_item_and_reads_the_message():
    session = _StubSession(_StubResponse(200, _openai_ok("THE ANSWER")))
    text = await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)
    assert text == "THE ANSWER"


@_sync
async def test_openai_joins_multiple_output_text_chunks():
    data = _openai_ok(extra_output=[
        {"type": "reasoning", "id": "rs_1"},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "part-one "},
            {"type": "output_text", "text": "part-two"},
        ]},
    ])
    session = _StubSession(_StubResponse(200, data))
    assert await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t",
                          retry_policy=_fast_retry) == "part-one part-two"


@_sync
async def test_openai_incomplete_raises_even_when_partial_text_exists():
    """Partial text that happens to parse is worse than no text at all."""
    data = _openai_ok("<MONOLOGUE><HOOK>truncated</HOOK>")
    data["status"] = "incomplete"
    data["incomplete_details"] = {"reason": "max_output_tokens"}
    session = _StubSession(_StubResponse(200, data))

    with pytest.raises(LLMIncompleteError, match="max_output_tokens"):
        await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)


@_sync
async def test_openai_refusal_is_detected():
    data = _openai_ok(extra_output=[
        {"type": "message", "role": "assistant",
         "content": [{"type": "refusal", "refusal": "I can't help with that."}]},
    ])
    session = _StubSession(_StubResponse(200, data))
    with pytest.raises(LLMRefusalError, match="can't help"):
        await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)


@_sync
async def test_openai_never_returns_empty_string_on_a_missing_message():
    """A defensive `return ""` here would become a silent empty script."""
    data = {"status": "completed", "output": [{"type": "reasoning", "id": "rs_1"}], "usage": {}}
    session = _StubSession(_StubResponse(200, data))
    with pytest.raises(LLMMalformedResponseError):
        await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)


@_sync
async def test_openai_body_omits_temperature_for_reasoning_models():
    route = OPENAI_ROUTE.model_copy(update={"temperature": 0.4})
    session = _StubSession(_StubResponse(200, _openai_ok()))
    await call_llm(None, "p", session, LOG, route, "t", retry_policy=_fast_retry)

    body = session.requests[0]["json"]
    assert "temperature" not in body, "gpt-5.x rejects temperature with HTTP 400"
    assert body["reasoning"] == {"effort": "low"}
    assert body["text"]["verbosity"] == "low"
    assert session.requests[0]["headers"]["Authorization"] == "Bearer sk-test"


@_sync
async def test_openai_body_keeps_temperature_for_a_non_reasoning_model():
    route = PhaseModel(provider="openai", model="gpt-4.1-mini", temperature=0.4)
    session = _StubSession(_StubResponse(200, _openai_ok()))
    await call_llm(None, "p", session, LOG, route, "t", retry_policy=_fast_retry)
    assert session.requests[0]["json"]["temperature"] == 0.4


@_sync
async def test_openai_system_prompt_leads_the_input_for_cache_prefix_reuse():
    session = _StubSession(_StubResponse(200, _openai_ok()))
    await call_llm("SYS", "USER", session, LOG, OPENAI_ROUTE, "t",
                   retry_policy=_fast_retry, cache_key="as-p2-demo")
    body = session.requests[0]["json"]
    assert body["input"][0] == {"role": "system", "content": "SYS"}
    assert body["input"][1] == {"role": "user", "content": "USER"}
    assert body["prompt_cache_key"] == "as-p2-demo"


@_sync
async def test_openai_strict_json_schema_is_attached():
    schema = {"name": "thing", "schema": {"type": "object", "properties": {}}}
    session = _StubSession(_StubResponse(200, _openai_ok('{"a":1}')))
    await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t",
                   json_schema=schema, retry_policy=_fast_retry)
    fmt = session.requests[0]["json"]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["name"] == "thing"


@_sync
async def test_openai_cost_does_not_re_add_reasoning_tokens():
    session = _StubSession(_StubResponse(200, _openai_ok()))
    await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)

    # 1000 in (400 cached), 500 out INCLUDING 300 reasoning.
    expected = (600 * 0.20 + 400 * 0.02 + 500 * 1.20) / 1_000_000
    assert ct.get_session_totals()["total_cost_usd"] == pytest.approx(expected)
    assert ct.get_session_totals()["total_output"] == 500  # not 800


# ---------------------------------------------------------------------------
# Gemini adapter (secondary provider)
# ---------------------------------------------------------------------------


@_sync
async def test_gemini_success_and_header_auth():
    session = _StubSession(_StubResponse(200, _gemini_ok()))
    assert await call_llm("SYS", "p", session, LOG, GEMINI_ROUTE, "t",
                          retry_policy=_fast_retry) == "hello"
    req = session.requests[0]
    assert req["headers"]["x-goog-api-key"] == "gem-test"
    assert "key=" not in req["url"], "API key must never ride in the query string"
    assert req["json"]["system_instruction"]["parts"][0]["text"] == "SYS"
    assert req["json"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 512}
    assert req["json"]["generationConfig"]["temperature"] == 0.4


@_sync
async def test_gemini_joins_parts_and_drops_thought_parts():
    """The old call sites read parts[0] only — a thought part would win."""
    parts = [
        {"text": "internal musing", "thought": True},
        {"text": "real "},
        {"text": "answer"},
    ]
    session = _StubSession(_StubResponse(200, _gemini_ok(parts=parts)))
    assert await call_llm(None, "p", session, LOG, GEMINI_ROUTE, "t",
                          retry_policy=_fast_retry) == "real answer"


@_sync
async def test_gemini_safety_and_max_tokens_map_to_distinct_errors():
    session = _StubSession(_StubResponse(200, _gemini_ok(finish="SAFETY")))
    with pytest.raises(LLMRefusalError):
        await call_llm(None, "p", session, LOG, GEMINI_ROUTE, "t", retry_policy=_fast_retry)

    session = _StubSession(_StubResponse(200, _gemini_ok(finish="MAX_TOKENS")))
    with pytest.raises(LLMIncompleteError):
        await call_llm(None, "p", session, LOG, GEMINI_ROUTE, "t", retry_policy=_fast_retry)


@_sync
async def test_gemini_cost_adds_thoughts_to_billed_output():
    session = _StubSession(_StubResponse(200, _gemini_ok()))
    await call_llm(None, "p", session, LOG, GEMINI_ROUTE, "t", retry_policy=_fast_retry)

    # Gemini reports thoughts SEPARATELY, so billed output is 500 + 300.
    expected = (1000 * 0.30 + 800 * 2.50) / 1_000_000
    assert ct.get_session_totals()["total_cost_usd"] == pytest.approx(expected)
    assert ct.get_session_totals()["total_output"] == 800


# ---------------------------------------------------------------------------
# HTTP status handling — the retry-storm guard
# ---------------------------------------------------------------------------


@_sync
async def test_400_is_attempted_exactly_once():
    """Without the 4xx split this becomes 6 attempts x 4-45s per call."""
    session = _StubSession(_StubResponse(400, text="Unsupported parameter: 'temperature'"))
    with pytest.raises(LLMBadRequestError, match="temperature"):
        await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)
    assert session.call_count == 1


@_sync
async def test_401_is_not_retried_either():
    session = _StubSession(_StubResponse(401, text="invalid api key"))
    with pytest.raises(LLMBadRequestError):
        await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)
    assert session.call_count == 1


@_sync
async def test_503_is_retried_then_succeeds():
    session = _StubSession(
        _StubResponse(503, text="unavailable"),
        _StubResponse(200, _openai_ok("recovered")),
    )
    text = await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)
    assert text == "recovered"
    assert session.call_count == 2


@_sync
async def test_429_raises_rate_limit_and_runs_the_penalty_hook():
    fired = []

    async def _hook():
        fired.append(True)

    def _no_wait_rate_policy():
        return standard_retry_policy(
            min_wait=0, max_wait=0, max_attempts=1, exceptions=(LLMRateLimitError,)
        )

    session = _StubSession(_StubResponse(429, text="slow down"))
    with pytest.raises(LLMRateLimitError):
        await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t",
                       retry_policy=_fast_retry,
                       rate_limit_policy=_no_wait_rate_policy,
                       on_rate_limit=_hook)
    assert fired == [True]
    assert ct.get_session_totals()["rate_limit_hits"] == 1


@_sync
async def test_429_without_a_rate_limit_policy_stays_transient():
    """Ideation and extraction have never distinguished 429 — keep it that way."""
    session = _StubSession(
        _StubResponse(429, text="slow down"),
        _StubResponse(200, _openai_ok("recovered")),
    )
    text = await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)
    assert text == "recovered"
    assert ct.get_session_totals()["rate_limit_hits"] == 1


# ---------------------------------------------------------------------------
# Config / key handling
# ---------------------------------------------------------------------------


@_sync
async def test_missing_key_is_a_clear_non_retryable_error(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "openai_api_key", None, raising=False)
    session = _StubSession(_StubResponse(200, _openai_ok()))
    with pytest.raises(LLMBadRequestError, match="OPENAI_API_KEY"):
        await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)
    assert session.call_count == 0, "must fail before spending a request"


@_sync
async def test_llm_timeout_is_applied_per_request():
    from src.agents.core.config import APP_CONFIG
    session = _StubSession(_StubResponse(200, _openai_ok()))
    await call_llm(None, "p", session, LOG, OPENAI_ROUTE, "t", retry_policy=_fast_retry)
    assert session.requests[0]["timeout"].total == APP_CONFIG.llm_timeout_seconds


@_sync
async def test_raw_result_exposes_usage_and_status():
    session = _StubSession(_StubResponse(200, _openai_ok("x")))
    result = await call_llm_raw(None, "p", session, LOG, OPENAI_ROUTE, "t",
                                retry_policy=_fast_retry)
    assert result.text == "x"
    assert result.status == "completed"
    assert result.usage["reasoning_tokens"] == 300
    assert result.raw["output"][0]["type"] == "reasoning"
