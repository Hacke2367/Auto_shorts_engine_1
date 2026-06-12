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
    thinking_budget: int | None = Field(
        default=None, ge=0,
        description="Gemini 2.5 thinkingConfig.thinkingBudget. 0 disables thinking (Flash only); "
                    "Pro requires >=128. None = provider default (dynamic). Thinking tokens are "
                    "billed at the OUTPUT rate, so this is a direct cost dial.",
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
        model="gemini-2.5-flash", temperature=0.6,
    )
    discovery_scoring: PhaseModel = PhaseModel(
        model="gemini-2.5-flash", temperature=0.1,
    )
    # ---- Phase 1: Extraction ----
    extraction: PhaseModel = PhaseModel(
        model="gemini-2.5-flash", temperature=0.1,
    )
    # ---- Phase 2: Scripting — COST-ROUTED across sub-tasks ----
    # Cheap Flash does the heavy lifting (creative draft + mechanical length-rewrites); expensive
    # Pro runs ONCE for the final flow polish (script-doctor). This keeps Pro as the final creative
    # pass while cutting cost ~85%. THE one quality/cost dial: if a persona's draft feels flat,
    # flip `scripting_draft.model` to "gemini-2.5-pro".
    #
    # thinking_budget is the STRUCTURE dial (not the same as the model dial): Flash with thinking
    # OFF (=0) fumbles long, strict-structure jobs — e.g. a 7-card sort_card needs 11 exact tags in
    # exact order within per-segment char budgets, and zero-thinking Flash drops tags / overshoots
    # length. Giving the draft a planning budget lets Flash lay out all tags first (keeps it cheap
    # Flash, NOT Pro); the rewrite gets a smaller budget so it can actually land each char window.
    scripting_draft: PhaseModel = PhaseModel(
        model="gemini-2.5-flash", temperature=0.4, thinking_budget=1024,
    )
    scripting_rewrite: PhaseModel = PhaseModel(
        model="gemini-2.5-flash", temperature=0.2, thinking_budget=512,
    )
    scripting_doctor: PhaseModel = PhaseModel(
        model="gemini-2.5-pro", temperature=0.3, thinking_budget=512,
    )
    # Back-compat alias (was the single Phase-2 route). Not used by the writer anymore.
    scripting: PhaseModel = PhaseModel(
        model="gemini-2.5-pro", temperature=0.3,
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

    # ---- Ideation retry (Phase 1 discovery foundation call) ----
    # Ideation is the single call the whole discovery run depends on; everything
    # downstream (Tavily search + scoring) only runs if it succeeds. Give it a
    # more patient retry than the standard profile so a transient 503 doesn't
    # collapse the run into the 3-topic hardcoded fallback.
    ideation_max_attempts: int = Field(default=6, ge=1)
    ideation_min_wait: float = Field(default=4.0, ge=0)
    ideation_max_wait: float = Field(default=45.0, ge=0)

    # ---- Scoring retry (Phase 1 per-candidate scoring) ----
    # Scoring fires ~10 calls concurrently; on a flaky-503 day the standard
    # 3-attempt profile drops candidates (we lost 1/10). These calls run in
    # parallel, so a few extra patient attempts cost little wall-clock time but
    # save whole candidates from a transient blip.
    scoring_max_attempts: int = Field(default=5, ge=1)
    scoring_min_wait: float = Field(default=2.0, ge=0)
    scoring_max_wait: float = Field(default=20.0, ge=0)

    # ---- Extraction retry (Phase 1B Gemini extract call) ----
    # Extraction is one heavy Gemini call per attempt and the WHOLE topic depends
    # on it; the default 3-attempt profile let a transient 503 burst kill a run.
    # Mirror ideation's patience so short Gemini blips are ridden out.
    extraction_max_attempts: int = Field(default=6, ge=1)
    extraction_min_wait: float = Field(default=4.0, ge=0)
    extraction_max_wait: float = Field(default=45.0, ge=0)

    # ---- Scripting retry (Phase 2 monologue calls) ----
    # Phase 2 fires SEVERAL sequential Gemini calls per run (draft + each rewrite
    # round + the doctor pass). The default 3-attempt profile let a transient 503
    # burst kill the whole phase mid-rewrite-loop — even when the draft was nearly
    # valid. Mirror extraction's patience so a short Gemini blip is ridden out
    # instead of discarding an otherwise-good script.
    scripting_max_attempts: int = Field(default=6, ge=1)
    scripting_min_wait: float = Field(default=4.0, ge=0)
    scripting_max_wait: float = Field(default=45.0, ge=0)

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

    # ---- Phase 1 discovery: data-feasibility gate + ideation over-provisioning ----
    # A topic without provable published data is worthless downstream (extraction
    # would burn money and fail), no matter how viral the hook. The scoring judge
    # already detects this (data_feasibility_score); this gate ENFORCES the verdict:
    # candidates scoring below the threshold are dropped from the returned batch.
    # 5.0 = the scoring rubric's boundary between "real figures exist in prose"
    # (5-6, extractable) and "no structured data / derived metric" (1-3, unbuildable).
    discovery_min_data_feasibility: float = Field(default=5.0, ge=1, le=10)
    # Because the gate culls dataless ideas, ideation over-provisions by this many
    # extra hypotheses (top_n + buffer) so a gated run still fills the batch.
    # Each extra idea costs ~1 Tavily basic search + 1 scoring call (~$0.001).
    discovery_ideation_buffer: int = Field(default=4, ge=0)

    # Phase 2 script-doctor — a final whole-script flow-polish LLM pass that makes the segmented
    # monologue sound like one seamless spoken performance. Safe by design: any constraint
    # violation in its output (bad tags, out-of-budget, number drift) is discarded and the
    # pre-doctor script is kept. Set False to skip the extra LLM call (and its cost).
    script_doctor_enabled: bool = Field(
        default=True, description="Enable the Phase 2 whole-script flow-polish pass."
    )

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
