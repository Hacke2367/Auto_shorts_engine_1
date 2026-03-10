"""
AutoShorts Phase 3 Audio Engine
================================
Produces raw physical spoken word files from Phase 2 Scripts, natively
identifying dead-air silences and rejecting output structurally failing
the visual under-run length limits.
"""

from src.agents.phase3_audio.contracts import (
    AudioSegment,
    AudioSynthesisSettings,
    Phase3Payload,
    TTSError,
    AudioTrimError,
    UnderRunError,
    PayloadAssemblyError
)
from src.agents.phase3_audio.tts_client import synthesize, ElevenLabsRateLimitError
from src.agents.phase3_audio.trimming import trim_silence
from src.agents.phase3_audio.duration import duration_ms, duration_sec
from src.agents.phase3_audio.packager import update_script_with_audio, build_job_json, atomic_write_json
from src.agents.phase3_audio.runner import run_phase3

__all__ = [
    "AudioSegment",
    "AudioSynthesisSettings",
    "Phase3Payload",
    "TTSError",
    "AudioTrimError",
    "UnderRunError",
    "PayloadAssemblyError",
    "ElevenLabsRateLimitError",
    "synthesize",
    "trim_silence",
    "duration_ms",
    "duration_sec",
    "update_script_with_audio",
    "build_job_json",
    "atomic_write_json",
    "run_phase3"
]
