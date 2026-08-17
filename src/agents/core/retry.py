"""
AutoShorts Core — Shared Tenacity Retry Policies
=================================================
Centralised retry factories so every HTTP consumer uses ONE consistent policy.
All backoff numbers live in ``config.py`` (``APP_CONFIG.retry``) — edit there,
never inline in modules.

Usage:
    from src.agents.core.retry import standard_retry_policy, rate_limit_retry_policy

    async for attempt in standard_retry_policy():
        with attempt:
            ...

    async for attempt in rate_limit_retry_policy(exceptions=(MyRateLimitError,)):
        with attempt:
            ...
"""

from __future__ import annotations

import asyncio

import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.agents.core.config import APP_CONFIG
from src.agents.core.llm_errors import LLMRateLimitError

# Default exception set for transient network/server errors.
#
# NOTE: ``aiohttp.ClientResponseError`` subclasses ``ClientError``, so anything
# that reaches ``raise_for_status()`` — including 400 and 401 — matches here.
# core/llm_client.py therefore does NOT call raise_for_status() on 4xx; it maps
# those to the non-retryable ``LLMBadRequestError`` first. Non-LLM callers
# (Tavily) still use the blanket behaviour.
_TRANSIENT_EXC = (aiohttp.ClientError, asyncio.TimeoutError)


def standard_retry_policy(
    *,
    min_wait: float | None = None,
    max_wait: float | None = None,
    max_attempts: int | None = None,
    exceptions: tuple[type[BaseException], ...] = _TRANSIENT_EXC,
) -> AsyncRetrying:
    """Exponential backoff for transient HTTP/network errors.

    All defaults come from ``APP_CONFIG.retry``; pass explicit args only to
    override for a specific call site.
    """
    rc = APP_CONFIG.retry
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts if max_attempts is not None else rc.max_attempts),
        wait=wait_exponential(
            multiplier=rc.multiplier,
            min=min_wait if min_wait is not None else rc.min_wait,
            max=max_wait if max_wait is not None else rc.max_wait,
        ),
        retry=retry_if_exception_type(exceptions),
        reraise=True,
    )


def rate_limit_retry_policy(
    *,
    exceptions: tuple[type[BaseException], ...] | None = None,
) -> AsyncRetrying:
    """Conservative long-backoff retry for HTTP 429 responses.

    Defaults to the provider-neutral ``LLMRateLimitError``. This used to lazily
    import a Gemini-specific exception from deep inside ``phase1_discovery`` at
    call time purely to dodge a circular import; ``llm_errors`` is a leaf module,
    so a normal top-level import works now.
    """
    if exceptions is None:
        exceptions = (LLMRateLimitError,)

    rc = APP_CONFIG.retry
    return AsyncRetrying(
        stop=stop_after_attempt(rc.rate_limit_max_attempts),
        wait=wait_exponential(
            multiplier=rc.rate_limit_multiplier,
            min=rc.rate_limit_min_wait,
            max=rc.rate_limit_max_wait,
        ),
        retry=retry_if_exception_type(exceptions),
        reraise=True,
    )
