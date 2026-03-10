"""AutoShorts Phase 3 Audio Engine — TTS Client
===========================================
Async text-to-speech interaction with ElevenLabs API.

Implements:
- tenacity retries + exponential backoff
- aggressive backoff for HTTP 429
- structured telemetry logging

Returns raw audio bytes only. Disk writes are owned by the Phase 3 runner.
"""

import aiohttp
import asyncio
import logging
import os
import time

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.logger import log_api_call
from src.agents.phase3_audio.contracts import AudioSynthesisSettings, TTSError

logger = logging.getLogger(__name__)

# Fetch from core config if available, else ENV fallback.
try:
    from src.agents.core.config import settings
    _ELEVENLABS_KEY = (
        settings.elevenlabs_api_key.get_secret_value()
        if hasattr(settings, "elevenlabs_api_key") and getattr(settings, "elevenlabs_api_key")
        else os.getenv("ELEVENLABS_API_KEY", "")
    )
except Exception:
    _ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")


class ElevenLabsRateLimitError(Exception):
    """Raised to trigger aggressive backoff for HTTP 429."""
    pass


def _get_standard_retry() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
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

    if not _ELEVENLABS_KEY:
        raise TTSError("ElevenLabs API key missing. Set ELEVENLABS_API_KEY (or settings.elevenlabs_api_key).")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{tts_settings.voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": _ELEVENLABS_KEY,
    }

    params = {"output_format": tts_settings.output_format}
    payload: dict = {"text": text, "model_id": tts_settings.model_id}

    voice_settings: dict = {}
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

                        if resp.status < 200 or resp.status >= 300:
                            err = await resp.text()
                            raise TTSError(f"ElevenLabs synthesis failed: HTTP {resp.status} - {err}")

                        return await resp.read()

    raise TTSError("Exhausted all ElevenLabs synthesis retries.")
