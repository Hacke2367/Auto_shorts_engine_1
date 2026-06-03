"""
AutoShorts Core — Shared Tenacity Retry Policies
=================================================
Centralised retry factories so every HTTP consumer uses a consistent policy.

Usage:
    from src.agents.core.retry import standard_retry_policy, rate_limit_retry_policy

    async for attempt in standard_retry_policy():
        with attempt:
            ...
"""

from __future__ import annotations

import asyncio

import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential


def standard_retry_policy(
    *, min_wait: float = 2, max_wait: float = 10
) -> AsyncRetrying:
    """3-attempt exponential backoff for transient HTTP/network errors.

    Args:
        min_wait: Minimum wait in seconds between retries (default 2).
        max_wait: Maximum wait in seconds between retries (default 10).

    Returns:
        Configured AsyncRetrying instance ready for use in ``async for`` loops.
    """
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )


def rate_limit_retry_policy() -> AsyncRetrying:
    """3-attempt retry with 60–120s backoff for Gemini HTTP 429 responses.

    Imports ``GeminiRateLimitError`` lazily to avoid circular imports.

    Returns:
        Configured AsyncRetrying instance ready for use in ``async for`` loops.
    """
    from src.agents.phase1_discovery.candidate_score import GeminiRateLimitError

    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=60, min=60, max=120),
        retry=retry_if_exception_type(GeminiRateLimitError),
        reraise=True,
    )
