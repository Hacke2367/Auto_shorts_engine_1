from __future__ import annotations

"""AutoShorts Phase 3 Audio Engine — Contracts
==========================================
Pydantic schemas and typed boundaries for Audio Synthesis and payload assembly.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TTSError(Exception):
    """Raised when the TTS Provider fails to synthesize audio."""
    pass


class AudioTrimError(Exception):
    """Raised when audio trimming fails."""
    pass


class UnderRunError(Exception):
    """Raised when physical audio duration is shorter than the visual requirement (MND)."""
    pass


class PayloadAssemblyError(Exception):
    """Raised when the final render payload (job.json/script.json) assembly fails."""
    pass


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class AudioSegment(BaseModel):
    """Represents a processed chunk of audio mapped to a script tag."""
    tag: str = Field(..., description="Template script tag (e.g. HOOK, SETUP, ITEM_1).")
    text: str = Field(..., description="Spoken text synthesized.")
    audio_relpath: str = Field(..., description="Relative path to the final trimmed audio file within the job package.")
    duration_ms: int = Field(..., ge=0, description="Physical duration (ms) calculated after trim.")
    duration_sec: float = Field(..., ge=0.0, description="Physical duration represented in seconds.")


class AudioSynthesisSettings(BaseModel):
    """Configuration defining how ElevenLabs should serialize the script."""
    provider: Literal["elevenlabs"] = Field(default="elevenlabs", description="The backend TTS provider.")
    voice_id: str = Field(..., description="Provider voice ID.")
    model_id: str = Field(..., description="Provider model ID.")
    output_format: str = Field(default="mp3_44100_128", description="ElevenLabs output_format string.")

    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)
    style: float | None = Field(default=None, ge=0.0, le=1.0)
    speaker_boost: bool | None = Field(default=None)
    speed: float | None = Field(default=None, ge=0.7, le=1.2,
                                description="ElevenLabs voice_settings.speed (1.0 = native pace).")

    concurrency_limit: int = Field(default=3, ge=1, description="Bounded concurrency for synthesis (enforced by runner).")


class Phase3Payload(BaseModel):
    """Final payload emitted by Phase 3 containing audio files and matched durations."""
    job_id: str = Field(..., description="ID mapping back to JobManager context.")
    template_name: str = Field(..., description="Visual template to be rendered.")
    persona_id: str = Field(..., description="Persona ID used.")
    segments: list[AudioSegment] = Field(..., description="Ordered list of synthesized segments with durations.")
    tts_settings: AudioSynthesisSettings = Field(..., description="Synthesis parameters utilized.")
    under_run_retries_used: int = Field(default=0, ge=0, description="How many rewrite attempts occurred before passing MND gate.")
    inputs_hash: str = Field(..., description="Hash protecting idempotency from silent mutation.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this payload was assembled — aids cache-hit debugging.",
    )
