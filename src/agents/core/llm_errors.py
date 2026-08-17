"""
AutoShorts Core — LLM Error Taxonomy
====================================
Deliberately a LEAF module: it imports nothing from this package.

``retry.py`` needs the rate-limit exception to build its 429 policy, and
``llm_client.py`` needs ``retry.py``. Putting the exceptions in either of those
creates a cycle — which is exactly why ``retry.py`` used to lazily import
``GeminiRateLimitError`` from deep inside ``phase1_discovery`` at call time.
Keeping this module dependency-free lets both import it normally.

Taxonomy
--------
``LLMBadRequestError`` is the one that must NEVER be retried: a 400 is a
malformed request (wrong param, bad model id, unsupported field), and retrying
it six times with 4-45s backoff just turns a config typo into a multi-minute
hang across every concurrent call.

Transport errors (``aiohttp.ClientError``, ``asyncio.TimeoutError``) are
deliberately NOT wrapped — they propagate unchanged so existing callers that
catch them keep working.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every provider-level LLM failure."""


class LLMRateLimitError(LLMError):
    """HTTP 429. Retried by the long-backoff rate-limit policy."""


class LLMBadRequestError(LLMError):
    """A 4xx other than 429 — malformed request, bad auth, missing key.

    NOT retryable: the same request will fail identically every time.
    """


class LLMIncompleteError(LLMError):
    """The model stopped before finishing.

    OpenAI: ``status == "incomplete"`` (usually ``max_output_tokens`` consumed
    by reasoning). Gemini: ``finishReason == "MAX_TOKENS"``.

    Critically, the provider may still return partial text — a truncated
    ``<MONOLOGUE>`` can even parse cleanly if the cut lands after the last tag.
    Callers must treat this as a failure, never as a short success.
    """


class LLMRefusalError(LLMError):
    """The model declined to answer (safety filter / refusal content item)."""


class LLMMalformedResponseError(LLMError):
    """A 2xx response we could not extract any assistant text from."""
