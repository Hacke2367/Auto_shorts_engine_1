"""AutoShorts Phase 3 Audio Engine — TTS Client
===========================================
Async text-to-speech interaction with ElevenLabs API.

Implements:
- tenacity retries + exponential backoff
- aggressive backoff for HTTP 429
- HTTP 5xx treated as transient (retried by standard policy)
- structured telemetry logging

Returns raw audio bytes only. Disk writes are owned by the Phase 3 runner.
"""

import logging
import os
import time
from typing import Any

import aiohttp
import asyncio

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.logger import log_api_call
from src.agents.phase3_audio.contracts import AudioSynthesisSettings, TTSError

logger = logging.getLogger(__name__)


class ElevenLabsRateLimitError(Exception):
    """Raised to trigger aggressive backoff for HTTP 429."""
    pass


def _get_elevenlabs_key() -> str:
    """Resolve ElevenLabs API key at call time — not at import time.

    Reading the key here (rather than at module level) ensures env-var changes
    after import (e.g., test monkeypatching with os.environ) are picked up on
    each call. Only ImportError is caught — all other errors (missing .env,
    config syntax error) are allowed to propagate so they surface immediately.
    """
    try:
        from src.agents.core.config import settings  # noqa: PLC0415
        if hasattr(settings, "elevenlabs_api_key") and settings.elevenlabs_api_key:
            return settings.elevenlabs_api_key.get_secret_value()
    except ImportError:
        pass
    return os.getenv("ELEVENLABS_API_KEY", "")


def _get_standard_retry() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # aiohttp.ClientResponseError covers HTTP 5xx raised via resp.raise_for_status()
        # or explicitly for 5xx — allows transient server errors to be retried.
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )


def _get_429_retry() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=30, min=30, max=120),
        retry=retry_if_exception_type(ElevenLabsRateLimitError),
        reraise=True,
    )


async def synthesize(
    text: str,
    tts_settings: AudioSynthesisSettings,
    session: aiohttp.ClientSession,
    log: logging.Logger = logger,
) -> bytes:
    if tts_settings.provider != "elevenlabs":
        raise TTSError(f"Unsupported TTS provider: {tts_settings.provider}")

    key = _get_elevenlabs_key()
    if not key:
        raise TTSError("ElevenLabs API key missing. Set ELEVENLABS_API_KEY (or settings.elevenlabs_api_key).")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{tts_settings.voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key,
    }

    params = {"output_format": tts_settings.output_format}
    payload: dict[str, Any] = {"text": text, "model_id": tts_settings.model_id}

    voice_settings: dict[str, Any] = {}
    if tts_settings.stability is not None:
        voice_settings["stability"] = tts_settings.stability
    if tts_settings.similarity_boost is not None:
        voice_settings["similarity_boost"] = tts_settings.similarity_boost
    if tts_settings.style is not None:
        voice_settings["style"] = tts_settings.style
    if tts_settings.speaker_boost is not None:
        voice_settings["use_speaker_boost"] = tts_settings.speaker_boost

    if voice_settings:
        payload["voice_settings"] = voice_settings

    async for rate_attempt in _get_429_retry():
        with rate_attempt:
            async for attempt in _get_standard_retry():
                with attempt:
                    t0 = time.perf_counter()
                    async with session.post(url, headers=headers, params=params, json=payload) as resp:
                        elapsed_ms = (time.perf_counter() - t0) * 1000

                        log_api_call(
                            log,
                            service="elevenlabs.synthesize",
                            status_code=resp.status,
                            retry_count=attempt.retry_state.attempt_number - 1,
                            duration_ms=elapsed_ms,
                        )

                        if resp.status == 429:
                            log.warning("ElevenLabs rate limit hit (429). Triggering outer backoff.")
                            raise ElevenLabsRateLimitError("HTTP 429")

                        # 5xx are transient server errors — raise ClientResponseError so
                        # _get_standard_retry() picks them up and backs off.
                        if resp.status >= 500:
                            raise aiohttp.ClientResponseError(
                                resp.request_info, resp.history, status=resp.status
                            )

                        if resp.status < 200 or resp.status >= 300:
                            err = await resp.text()
                            raise TTSError(f"ElevenLabs synthesis failed: HTTP {resp.status} - {err}")

                        return await resp.read()

    raise TTSError("Exhausted all ElevenLabs synthesis retries.")
