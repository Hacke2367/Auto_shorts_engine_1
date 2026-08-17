"""
AutoShorts Core — Shared LLM Client
===================================
The single place the pipeline talks to an LLM.

Before this module the same HTTP call was duplicated across four files
(ideation, scoring, extraction, scripting), each with its own payload builder,
response unwrapper, 429 handling and cost accounting — four chances to drift.

Provider is chosen PER ROUTE via ``PhaseModel.provider``. OpenAI is the default
everywhere; the Gemini adapter is kept as a secondary option so a single route
can be pinned back for an A/B or a rollback without touching any call site.

Two response-shape traps this module exists to contain
------------------------------------------------------
* **OpenAI** puts the reasoning item FIRST in ``output[]``. Indexing ``output[0]``
  yields the reasoning item, not the message.
* **Gemini** returns ``parts[]`` that may include thought parts and may be split
  across several entries. The old code read ``parts[0]`` only.

Both adapters therefore SCAN for the right item and join every text part. When
no assistant text can be found they raise — they never return ``""``, because a
silent empty string downstream becomes an empty script rather than a loud error.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiohttp
from tenacity import AsyncRetrying

from src.agents.core.config import APP_CONFIG, PhaseModel, settings
from src.agents.core.cost_tracker import track_llm_call, track_rate_limit_hit
from src.agents.core.llm_errors import (
    LLMBadRequestError,
    LLMIncompleteError,
    LLMMalformedResponseError,
    LLMRateLimitError,
)
from src.agents.core.llm_errors import LLMRefusalError
from src.agents.core.logger import log_api_call
from src.agents.core.retry import standard_retry_policy

logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# GPT-5.x and the o-series reject `temperature` outright (HTTP 400 — some
# endpoints reject the field's mere presence, not just non-default values).
_NO_SAMPLING_PARAMS = re.compile(r"^(gpt-5|o\d)", re.IGNORECASE)


def _supports_temperature(model: str) -> bool:
    """Whether ``model`` accepts the `temperature` sampling parameter."""
    return _NO_SAMPLING_PARAMS.match(model) is None


@dataclass
class LLMResult:
    """One completed LLM call."""

    text: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    status: str | None = None


def _require_key(secret, env_name: str, provider: str) -> str:
    if secret is None:
        raise LLMBadRequestError(
            f"{env_name} is not set, but a route is configured with provider="
            f"'{provider}'. Add {env_name} to the project .env, or point that route "
            f"at a provider you have a key for (see LLMConfig in core/config.py)."
        )
    return secret.get_secret_value()


# ---------------------------------------------------------------------------
# OpenAI adapter (default provider)
# ---------------------------------------------------------------------------


def _openai_build(
    cfg: PhaseModel,
    system_prompt: str | None,
    user_prompt: str,
    json_schema: dict | None,
    expect_json: bool,
    cache_key: str | None,
) -> tuple[str, dict, dict]:
    key = _require_key(settings.openai_api_key, "OPENAI_API_KEY", "openai")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    body: dict[str, Any] = {"model": cfg.model, "input": messages}

    if cfg.reasoning_effort:
        body["reasoning"] = {"effort": cfg.reasoning_effort}

    # Only sent when explicitly configured. On OpenAI this caps reasoning AND
    # visible output together, so a value ported from Gemini can be consumed
    # entirely by thinking — billing you for a response with no text in it.
    if cfg.max_output_tokens is not None:
        body["max_output_tokens"] = cfg.max_output_tokens

    if cfg.temperature is not None and _supports_temperature(cfg.model):
        body["temperature"] = cfg.temperature

    text_cfg: dict[str, Any] = {}
    if json_schema is not None:
        text_cfg["format"] = {
            "type": "json_schema",
            "name": json_schema.get("name", "response"),
            "schema": json_schema["schema"],
            "strict": True,
        }
    elif expect_json:
        text_cfg["format"] = {"type": "json_object"}
    if cfg.verbosity:
        text_cfg["verbosity"] = cfg.verbosity
    if text_cfg:
        body["text"] = text_cfg

    # Improves cache routing when many calls share a long static prefix.
    if cache_key:
        body["prompt_cache_key"] = cache_key

    return OPENAI_RESPONSES_URL, headers, body


def _openai_parse(data: dict) -> str:
    status = data.get("status")

    # Check BEFORE reading text. An incomplete response can still carry partial
    # output, and a truncated <MONOLOGUE> may even parse cleanly if the cut lands
    # after the final tag — a short, structurally valid, silently wrong script.
    if status == "incomplete":
        reason = (data.get("incomplete_details") or {}).get("reason", "unknown")
        raise LLMIncompleteError(
            f"OpenAI stopped early (status=incomplete, reason={reason}). If reason is "
            "max_output_tokens, reasoning consumed the budget — raise or unset "
            "max_output_tokens, or lower reasoning_effort."
        )

    message = None
    for item in data.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "message":
            message = item
            break

    if message is None:
        types = [i.get("type") for i in (data.get("output") or []) if isinstance(i, dict)]
        raise LLMMalformedResponseError(
            f"No message item in OpenAI output[] (saw types: {types}). "
            f"status={status!r}"
        )

    texts: list[str] = []
    for chunk in message.get("content") or []:
        if not isinstance(chunk, dict):
            continue
        if chunk.get("type") == "refusal":
            raise LLMRefusalError(chunk.get("refusal") or "model refused the request")
        if chunk.get("type") == "output_text":
            texts.append(chunk.get("text") or "")

    joined = "".join(texts)
    if not joined.strip():
        raise LLMMalformedResponseError("OpenAI message item carried no output_text.")
    return joined


def _openai_usage(data: dict) -> dict[str, int]:
    """Extract token usage.

    The nested field names below were CONFIRMED against a live response on
    2026-08-08 via ``scripts/llm_smoke.py``::

        {"input_tokens": 22,
         "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
         "output_tokens": 19,
         "output_tokens_details": {"reasoning_tokens": 0},
         "total_tokens": 41}

    The flat fallbacks are kept as cheap insurance against a future rename — a
    silently-zeroed cost dashboard is far worse than a redundant ``or``.
    """
    u = data.get("usage") or {}
    details_in = u.get("input_tokens_details") or {}
    details_out = u.get("output_tokens_details") or {}
    return {
        "input_tokens": u.get("input_tokens") or u.get("prompt_tokens") or 0,
        # Already-billed output: on OpenAI reasoning is INSIDE output_tokens.
        "output_tokens": u.get("output_tokens") or u.get("completion_tokens") or 0,
        "cached_input_tokens": details_in.get("cached_tokens") or u.get("cached_tokens") or 0,
        # Cache WRITES bill at 1.25x the input rate, so they must be separated
        # from ordinary fresh input rather than lumped in with it.
        "cache_write_tokens": details_in.get("cache_write_tokens") or 0,
        "reasoning_tokens": details_out.get("reasoning_tokens") or u.get("reasoning_tokens") or 0,
    }


# ---------------------------------------------------------------------------
# Gemini adapter (secondary provider — kept for A/B and rollback)
# ---------------------------------------------------------------------------


def _gemini_build(
    cfg: PhaseModel,
    system_prompt: str | None,
    user_prompt: str,
    json_schema: dict | None,
    expect_json: bool,
    cache_key: str | None,
) -> tuple[str, dict, dict]:
    key = _require_key(settings.gemini_api_key, "GEMINI_API_KEY", "gemini")
    url = f"{GEMINI_BASE_URL}/{cfg.model}:generateContent"
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    gen: dict[str, Any] = {}
    if cfg.temperature is not None:
        gen["temperature"] = cfg.temperature
    if cfg.max_output_tokens is not None:
        gen["maxOutputTokens"] = cfg.max_output_tokens
    if cfg.thinking_budget is not None:
        # Caps (or with 0 on Flash, disables) reasoning tokens, billed at the output rate.
        gen["thinkingConfig"] = {"thinkingBudget": cfg.thinking_budget}
    if json_schema is not None or expect_json:
        # Gemini has no strict-schema equivalent; JSON mode is best-effort, which
        # is why the tolerant hand-written parsers downstream are kept.
        gen["responseMimeType"] = "application/json"

    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": gen,
    }
    if system_prompt:
        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
    return url, headers, payload


def _gemini_parse(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise LLMRefusalError(f"Gemini blocked the prompt: {feedback['blockReason']}")
        raise LLMMalformedResponseError(f"Gemini returned no candidates: {str(data)[:300]}")

    candidate = candidates[0]
    finish = candidate.get("finishReason")
    if finish == "SAFETY":
        raise LLMRefusalError("Gemini finishReason=SAFETY")
    if finish == "MAX_TOKENS":
        raise LLMIncompleteError("Gemini finishReason=MAX_TOKENS (response truncated)")

    parts = (candidate.get("content") or {}).get("parts") or []
    # Join ALL non-thought text parts. The old call sites read parts[0] only, which
    # silently returned a thought fragment when thinking was enabled.
    texts = [
        p["text"] for p in parts
        if isinstance(p, dict) and "text" in p and not p.get("thought")
    ]
    joined = "".join(texts)
    if not joined.strip():
        raise LLMMalformedResponseError(
            f"Gemini candidate carried no text parts (finishReason={finish!r})."
        )
    return joined


def _gemini_usage(data: dict) -> dict[str, int]:
    u = data.get("usageMetadata") or {}
    thoughts = u.get("thoughtsTokenCount", 0) or 0
    return {
        "input_tokens": u.get("promptTokenCount", 0) or 0,
        # Gemini reports thoughts SEPARATELY and bills them at the output rate,
        # so billed output is the sum. (OpenAI is the opposite — see _openai_usage.)
        "output_tokens": (u.get("candidatesTokenCount", 0) or 0) + thoughts,
        "cached_input_tokens": (u.get("cachedContentTokenCount", 0) or 0),
        "cache_write_tokens": 0,  # Gemini has no equivalent surcharge
        "reasoning_tokens": thoughts,
    }


_ADAPTERS = {
    "openai": (_openai_build, _openai_parse, _openai_usage),
    "gemini": (_gemini_build, _gemini_parse, _gemini_usage),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_llm_raw(
    system_prompt: str | None,
    user_prompt: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    phase_model: PhaseModel,
    cost_phase: str,
    *,
    json_schema: dict | None = None,
    expect_json: bool = False,
    retry_policy: Callable[[], AsyncRetrying] | None = None,
    rate_limit_policy: Callable[[], AsyncRetrying] | None = None,
    service_tag: str | None = None,
    on_rate_limit: Callable[[], Awaitable[None]] | None = None,
    job_dir: Path | None = None,
    cache_key: str | None = None,
) -> LLMResult:
    """Make one LLM call and return the assistant text plus usage.

    The first six parameters are positional and match the signature the Phase 2
    writer already used, so existing test fakes keep working.

    ``rate_limit_policy`` controls 429 behaviour and preserves each call site's
    existing semantics: when supplied, a 429 raises :class:`LLMRateLimitError`
    and is retried with the long backoff; when omitted, a 429 is counted and then
    treated as an ordinary transient error by ``retry_policy`` — which is what
    ideation and extraction have always done.

    Raises:
        LLMBadRequestError: 4xx other than 429. Never retried.
        LLMRateLimitError: 429, when ``rate_limit_policy`` is supplied.
        LLMIncompleteError: model stopped early (truncated output).
        LLMRefusalError: safety block / explicit refusal.
        LLMMalformedResponseError: 2xx with no extractable assistant text.
    """
    provider = phase_model.provider
    try:
        build, parse, usage_of = _ADAPTERS[provider]
    except KeyError:
        raise LLMBadRequestError(f"Unknown LLM provider {provider!r}") from None

    url, headers, payload = build(
        phase_model, system_prompt, user_prompt, json_schema, expect_json, cache_key
    )
    tag = service_tag or f"{provider}.{cost_phase}"
    timeout = aiohttp.ClientTimeout(total=APP_CONFIG.llm_timeout_seconds)

    retry_policy = retry_policy or standard_retry_policy
    data: dict | None = None

    async def _one_attempt() -> dict:
        async for attempt in retry_policy():
            with attempt:
                t0 = time.perf_counter()
                async with session.post(
                    url, json=payload, headers=headers, timeout=timeout
                ) as resp:
                    log_api_call(
                        log,
                        service=tag,
                        status_code=resp.status,
                        retry_count=attempt.retry_state.attempt_number - 1,
                        duration_ms=(time.perf_counter() - t0) * 1000,
                    )

                    if resp.status == 429:
                        track_rate_limit_hit()
                        if on_rate_limit is not None:
                            await on_rate_limit()
                        if rate_limit_policy is not None:
                            raise LLMRateLimitError(f"429 from {provider} ({cost_phase})")
                        # No dedicated 429 policy for this route: fall through so the
                        # standard transient profile handles it, as it always has.
                        resp.raise_for_status()

                    if 400 <= resp.status < 500:
                        body = (await resp.text())[:400]
                        raise LLMBadRequestError(
                            f"{provider} HTTP {resp.status} ({cost_phase}): {body}"
                        )

                    resp.raise_for_status()  # 5xx -> ClientResponseError -> retried
                    return await resp.json()
        raise LLMMalformedResponseError(f"{provider} call exhausted retries ({cost_phase}).")

    if rate_limit_policy is not None:
        async for rate_attempt in rate_limit_policy():
            with rate_attempt:
                data = await _one_attempt()
    else:
        data = await _one_attempt()

    if data is None:  # defensive; the loops either assign or raise
        raise LLMMalformedResponseError(f"{provider} call produced no response ({cost_phase}).")

    # Track cost BEFORE parsing: the tokens were spent whether or not the reply
    # turns out to be usable.
    usage = usage_of(data)
    track_llm_call(
        phase=cost_phase,
        provider=provider,
        model=phase_model.model,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cached_input_tokens=usage["cached_input_tokens"],
        cache_write_tokens=usage.get("cache_write_tokens", 0),
        reasoning_tokens=usage["reasoning_tokens"],
        job_dir=job_dir,
    )

    text = parse(data)
    return LLMResult(text=text, usage=usage, raw=data, status=data.get("status"))


async def call_llm(
    system_prompt: str | None,
    user_prompt: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    phase_model: PhaseModel,
    cost_phase: str,
    **kwargs: Any,
) -> str:
    """Convenience wrapper returning just the assistant text. See :func:`call_llm_raw`."""
    result = await call_llm_raw(
        system_prompt, user_prompt, session, log, phase_model, cost_phase, **kwargs
    )
    return result.text
