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
from typing import Literal

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
    # LLM provider keys are OPTIONAL at import time and validated at CALL time by
    # the adapter that needs them (see core/llm_client.py). Making either one
    # required here meant that merely importing this module — which almost every
    # module does transitively — crashed for anyone without that provider's key,
    # including the offline test suite.
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="API key for OpenAI (the default provider).",
        validation_alias="OPENAI_API_KEY",
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        description="API key for Google Gemini (secondary provider, kept for rollback/A-B).",
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

    Change ``model`` (and ``provider``) to route this phase to a different LLM.
    Each phase is independent, so Phase 1 and Phase 2 can run on completely
    different models — or even different providers, which is how an A/B is run.
    """

    provider: Literal["openai", "gemini"] = Field(
        default="openai",
        description="Which backend serves this route. OpenAI is the default everywhere; "
                    "Gemini is kept as a secondary option so a single route can be pinned "
                    "back for A/B comparison or rollback.",
    )
    model: str = Field(description="Provider-specific model id used for this phase.")
    temperature: float | None = Field(
        default=None, ge=0.0, le=2.0,
        description="Sampling temperature. GPT-5.x reasoning models REJECT this parameter "
                    "outright (HTTP 400), so the OpenAI adapter drops it for those models; "
                    "it is kept here because the Gemini adapter still uses it.",
    )
    max_output_tokens: int | None = Field(
        default=None, ge=1,
        description="Optional output token cap (None = provider default). On OpenAI this caps "
                    "reasoning AND visible output together — set too low and the model burns "
                    "the budget thinking and returns NOTHING while still billing you. Leave "
                    "None unless you have measured the route.",
    )

    # ---- OpenAI-only dials ----
    reasoning_effort: str | None = Field(
        default=None,
        description="OpenAI reasoning.effort: none|minimal|low|medium|high|xhigh|max. "
                    "This is THE quality/cost dial — reasoning tokens bill at the OUTPUT rate "
                    "and the gpt-5.6 default is 'medium', so leaving it unset is a cost risk. "
                    "Unlike Gemini's thinking_budget this is NOT a hard token cap.",
    )
    verbosity: str | None = Field(
        default=None,
        description="OpenAI text.verbosity: low|medium|high. Output-length dial — a better fit "
                    "than temperature ever was for 'cut N words' style rewrite work.",
    )

    # ---- Gemini-only dial (secondary provider) ----
    thinking_budget: int | None = Field(
        default=None, ge=0,
        description="Gemini 2.5 thinkingConfig.thinkingBudget. 0 disables thinking (Flash only); "
                    "Pro requires >=128. None = provider default (dynamic). Thinking tokens are "
                    "billed at the OUTPUT rate, so this is a direct cost dial.",
    )


class LLMConfig(BaseModel):
    """Per-phase LLM routing + shared LLM operational settings.

    ────────────────────────────────────────────────────────────────────────
    EDIT THE VALUES BELOW TO ROUTE EACH PHASE TO A DIFFERENT LLM.
    ────────────────────────────────────────────────────────────────────────
    Every route runs OpenAI ``gpt-5.6-luna``. On OpenAI the quality dial is
    ``reasoning_effort``, NOT the model tier — luna's output rate ($1.20/1M) buys
    roughly 8x more reasoning than gemini-2.5-pro's ($10.00/1M) at the same
    spend, so the pipeline buys quality with effort instead of with a bigger,
    pricier model.

    If a route needs more quality, walk the ladder in this order:
        effort high  ->  effort xhigh  ->  model "gpt-5.6-terra"
    Each step is one line. Escalate only against a measured A/B — terra is 10x
    luna's output price and a single terra doctor call costs more than an entire
    luna Phase 2 run.

    To A/B against the old provider, set ``provider="gemini"`` on ONE route (plus
    its ``model``/``temperature``/``thinking_budget``) and leave the rest alone.
    """

    # ---- Phase 1: Discovery ----
    # Idea variety comes from the prompt's Story Lenses + live trend seed + the
    # 2.5x over-provision, not from sampling temperature (which gpt-5.x rejects).
    discovery_ideation: PhaseModel = PhaseModel(
        model="gpt-5.6-luna", reasoning_effort="low", verbosity="medium",
    )
    # ~20 calls per run — the most volume-sensitive route, so effort stays low.
    discovery_scoring: PhaseModel = PhaseModel(
        model="gpt-5.6-luna", reasoning_effort="low", verbosity="low",
    )
    # ---- Phase 1: Extraction ----
    # One call per run and the whole video's factual accuracy rides on it, so this
    # is the one Phase 1 route worth paying medium effort for.
    extraction: PhaseModel = PhaseModel(
        model="gpt-5.6-luna", reasoning_effort="medium", verbosity="low",
    )
    # ---- Phase 2: Scripting ----
    # The old Gemini routing used thinking_budget as a STRUCTURE dial: a 7-card
    # sort_card needs 11 exact tags in exact order within per-segment char budgets,
    # and zero-thinking Flash dropped tags. reasoning_effort is that dial's analogue
    # (qualitative, not a token cap), which is why the draft gets medium.
    scripting_draft: PhaseModel = PhaseModel(
        model="gpt-5.6-luna", reasoning_effort="medium", verbosity="medium",
    )
    # Mechanical "cut N words" edit — verbosity is a better fit here than the old
    # temperature=0.2 ever was.
    scripting_rewrite: PhaseModel = PhaseModel(
        model="gpt-5.6-luna", reasoning_effort="low", verbosity="low",
    )
    # The doctor ELEVATES an already-valid script (flow, repetition, dangling ends).
    # That is a reasoning job, not a sampling job — hence high effort rather than a
    # bigger model.
    scripting_doctor: PhaseModel = PhaseModel(
        model="gpt-5.6-luna", reasoning_effort="high", verbosity="medium",
    )

    # ---- Shared LLM operational settings ----
    rpm_limit: int = Field(
        default=60, ge=1,
        description="Requests-per-minute ceiling for batched LLM calls (Phase 1 scoring). "
                    "Conservative: OpenAI Tier 1 already allows 500 RPM.",
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

    # --- Voice delivery (ElevenLabs voice_settings) ---------------------------
    # Previously NOTHING was sent, so every render fell back to whatever the voice
    # had saved in the ElevenLabs library — uncontrolled prosody/pacing. These are
    # tuned for natural, punchy Hinglish narration; override per-run if needed.
    stability: float = Field(default=0.45, ge=0.0, le=1.0,
                             description="Lower=more expressive, higher=more monotone. ~0.45 = natural.")
    similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0,
                                    description="How closely to match the original voice identity.")
    style: float = Field(default=0.0, ge=0.0, le=1.0,
                         description="Style exaggeration. Keep low for multilingual_v2 (high adds artifacts/long pauses).")
    speaker_boost: bool = Field(default=True, description="ElevenLabs use_speaker_boost (clarity).")
    speed: float = Field(default=1.0, ge=0.7, le=1.2,
                         description="Playback speed sent to ElevenLabs (1.0 = native; >1 = punchier).")


class AppConfig(BaseModel):
    """Top-level operational config hub."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)

    # Shared per-request HTTP timeout (seconds) for external calls
    # (Tavily, ElevenLabs). Excludes retry backoff.
    api_timeout_seconds: float = Field(default=60.0, gt=0)

    # LLM calls get their OWN, longer timeout, applied per-request inside
    # core/llm_client.py. A reasoning model at medium effort on a 5K-token prompt
    # routinely exceeds 60s; when the client gives up the server still finishes and
    # still bills the input + reasoning, then tenacity retries — turning one slow
    # call into six paid-for-and-discarded ones. Tavily/ElevenLabs stay at 60s.
    llm_timeout_seconds: float = Field(default=180.0, gt=0)

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
    # A flat buffer is too small for high-cull niches (finance/wealth ideates many
    # derived/dataless topics — ~70% get gated). Over-provision to a MULTIPLE of
    # top_n instead: ideation asks for max(top_n + buffer, ceil(top_n * multiplier)).
    # 2.5x balances fill-rate against per-idea scoring cost (~$0.001 each).
    discovery_ideation_multiplier: float = Field(default=2.5, ge=1.0)

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


# ===========================================================================
# A/B + rollback: the Gemini arm
# ===========================================================================
# The pipeline's routing EXACTLY as it stood before the OpenAI migration. This is
# the comparison arm for `--llm-provider gemini` — flipping to it reproduces the
# old behaviour end to end, including the thinking budgets that were load-bearing
# for Phase 2's tag structure.
#
# Delete this table (and the Gemini adapter) once OpenAI output has been signed
# off on sort_card and vs_card.
GEMINI_ROUTES: dict[str, PhaseModel] = {
    "discovery_ideation": PhaseModel(
        provider="gemini", model="gemini-2.5-flash", temperature=0.6),
    "discovery_scoring": PhaseModel(
        provider="gemini", model="gemini-2.5-flash", temperature=0.1),
    "extraction": PhaseModel(
        provider="gemini", model="gemini-2.5-flash", temperature=0.1),
    "scripting_draft": PhaseModel(
        provider="gemini", model="gemini-2.5-flash", temperature=0.4, thinking_budget=1024),
    "scripting_rewrite": PhaseModel(
        provider="gemini", model="gemini-2.5-flash", temperature=0.2, thinking_budget=512),
    "scripting_doctor": PhaseModel(
        provider="gemini", model="gemini-2.5-pro", temperature=0.3, thinking_budget=512),
}


def apply_provider_override(provider: str | None) -> None:
    """Point EVERY LLM route at ``provider`` for the rest of this process.

    Run-scoped only — it mutates the in-memory ``APP_CONFIG`` and writes nothing.
    Intended for A/B runs (``--llm-provider gemini``); the durable routing stays
    in :class:`LLMConfig` above, per the "operational settings live in config.py"
    rule.

    Passing ``None`` (the default when the flag is absent) is a no-op.
    """
    if provider is None:
        return
    if provider == "gemini":
        for route, phase_model in GEMINI_ROUTES.items():
            setattr(APP_CONFIG.llm, route, phase_model.model_copy(deep=True))
    elif provider == "openai":
        for route, phase_model in LLMConfig().__dict__.items():
            if isinstance(phase_model, PhaseModel):
                setattr(APP_CONFIG.llm, route, phase_model.model_copy(deep=True))
    else:
        raise ValueError(f"Unknown LLM provider override: {provider!r}")
