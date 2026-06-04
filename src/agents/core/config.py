"""
AutoShorts — Configuration
==========================
Two STRICTLY separated layers:

1. ``SystemSettings`` / ``settings`` — SECRETS ONLY.
   Loaded from the project ``.env`` (API keys / credentials). Crashes early
   (fail-fast) if a required key is missing. Nothing operational lives here.

2. ``AppConfig`` / ``APP_CONFIG`` — the CENTRAL CONTROL HUB.
   ALL app-level operational settings: per-phase LLM model routing, generation
   params, timeouts, rate limits, authority domains, toggles. Managed here in
   code — NOT in ``.env``. To change a model or a timeout, edit this file.

Rule of thumb:
    .env       -> "who am I / what are my keys"      (secret, per-machine)
    config.py  -> "how should the app behave"        (operational, in code)
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Map from the project root's .env file
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


# ===========================================================================
# Layer 1 — SECRETS (sourced from .env ONLY)
# ===========================================================================
class SystemSettings(BaseSettings):
    """Secret credentials only. Loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tavily_api_key: SecretStr = Field(
        ...,
        description="API key for Tavily search & extraction.",
        validation_alias="TAVILY_API_KEY",
    )
    gemini_api_key: SecretStr = Field(
        ...,
        description="API key for Google Gemini.",
        validation_alias="GEMINI_API_KEY",
    )
    elevenlabs_api_key: SecretStr | None = Field(
        default=None,
        description="API key for ElevenLabs TTS (optional — not needed in offline mode).",
        validation_alias="ELEVENLABS_API_KEY",
    )


@lru_cache(maxsize=1)
def get_settings() -> SystemSettings:
    """Return the global secrets singleton (created once, then cached).

    Testing (no real keys needed)::

        monkeypatch.setattr("src.agents.core.config.get_settings", lambda: MagicMock(...))
        get_settings.cache_clear()   # force a reload after env changes
    """
    return SystemSettings()


# Backward-compatibility alias — existing ``from ...config import settings`` keeps working.
settings: SystemSettings = get_settings()


# ===========================================================================
# Layer 2 — APP CONFIG (central control hub, code-managed)
# ===========================================================================
class PhaseModel(BaseModel):
    """LLM routing + generation params for ONE pipeline task.

    Change ``model`` to route this phase to a different LLM. Each phase is
    independent, so Phase 1 (extraction) and Phase 2 (scripting) can run on
    completely different models.
    """

    model: str = Field(description="Gemini model id used for this phase.")
    temperature: float = Field(ge=0.0, le=2.0, description="Sampling temperature for this phase.")
    max_output_tokens: int | None = Field(
        default=None, ge=1, description="Optional output token cap (None = provider default)."
    )


class LLMConfig(BaseModel):
    """Per-phase LLM routing + shared LLM operational settings.

    ────────────────────────────────────────────────────────────────────────
    EDIT THE `model` VALUES BELOW TO ROUTE EACH PHASE TO A DIFFERENT LLM.
    ────────────────────────────────────────────────────────────────────────
    Defaults: Phase 1 (discovery/extraction) runs the fast/cheap `flash`;
    Phase 2 scripting runs the stronger `pro` for higher-quality voiceover.
    """

    # ---- Phase 1: Discovery ----
    discovery_ideation: PhaseModel = PhaseModel(
        model="gemini-2.5-flash", temperature=0.6, max_output_tokens=1000,
    )
    discovery_scoring: PhaseModel = PhaseModel(
        model="gemini-2.5-flash", temperature=0.1, max_output_tokens=1000,
    )
    # ---- Phase 1: Extraction ----
    extraction: PhaseModel = PhaseModel(
        model="gemini-2.5-flash", temperature=0.1,
    )
    # ---- Phase 2: Scripting (specialized — stronger model) ----
    # Tip: raise `temperature` (e.g. 0.6–0.8) for more creative scripts; keep it
    # low if the XML parser is sensitive to format drift.
    scripting: PhaseModel = PhaseModel(
        model="gemini-2.5-pro", temperature=0.1,
    )

    # ---- Shared LLM operational settings ----
    rpm_limit: int = Field(
        default=60, ge=1,
        description="Requests-per-minute ceiling for batched Gemini calls (Phase 1 scoring).",
    )


class RetryConfig(BaseModel):
    """Centralized tenacity retry/backoff policy for ALL external HTTP calls.

    Two profiles:
      - standard   : transient network/5xx errors (fast, short backoff).
      - rate_limit : HTTP 429 responses (few attempts, long backoff).
    """

    # ---- Standard transient-error retry ----
    max_attempts: int = Field(default=3, ge=1)
    multiplier: float = Field(default=1.0, gt=0)
    min_wait: float = Field(default=2.0, ge=0)
    max_wait: float = Field(default=10.0, ge=0)

    # ---- Rate-limit (HTTP 429) retry — slower, more conservative ----
    rate_limit_max_attempts: int = Field(default=4, ge=1)
    rate_limit_multiplier: float = Field(default=60.0, gt=0)
    rate_limit_min_wait: float = Field(default=60.0, ge=0)
    rate_limit_max_wait: float = Field(default=120.0, ge=0)


class TTSConfig(BaseModel):
    """Phase 3 ElevenLabs TTS defaults. Override per-run via CLI flags.

    `voice_id` is brand/persona-specific — leave empty to force an explicit
    `--voice-id`, or set your default brand voice here.
    """

    provider: str = Field(default="elevenlabs", description="TTS backend provider.")
    model_id: str = Field(default="eleven_multilingual_v2", description="Default ElevenLabs model id.")
    voice_id: str = Field(default="", description="Default ElevenLabs voice id (empty = must pass --voice-id).")
    output_format: str = Field(default="mp3_44100_128", description="ElevenLabs output_format string.")
    concurrency_limit: int = Field(default=3, ge=1, description="Bounded concurrency for synthesis.")


class AppConfig(BaseModel):
    """Top-level operational config hub."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)

    # Shared per-request HTTP timeout (seconds) for ALL external calls
    # (Gemini, Tavily, ElevenLabs). Excludes retry backoff.
    api_timeout_seconds: float = Field(default=60.0, gt=0)

    # Authority domains for Phase 1 source auditing (operational, not secret).
    primary_authority_domains: list[str] = Field(
        default=["bloomberg.com", "un.org", "gov", "wsj.com", "socialblade.com", "youtube.com"],
        description="Domains considered purely authoritative.",
    )
    social_authority_domains: list[str] = Field(
        default=["reddit.com", "twitter.com", "x.com", "tiktok.com", "instagram.com"],
        description="Domains representing social/forum signals.",
    )


# The single source of truth for all operational settings.
APP_CONFIG = AppConfig()
