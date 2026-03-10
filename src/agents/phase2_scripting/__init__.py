"""
AutoShorts Phase 2 Scripting Engine
===================================
Exports the public runner orchestration entry point, which safely reads
Phase 1 extracted datasets and produces the timing-counted Monologue script
ready for Phase 3 Audio.
"""

from src.agents.phase2_scripting.contracts import (
    ParsedSegment,
    ScriptGenerationError,
    ScriptParsingError,
    ScriptPayload,
    ScriptValidationError,
    SegmentPlan,
    SegmentSpec,
    count_chars,
    normalize_text,
)
from src.agents.phase2_scripting.runner import run_scripting

__all__ = [
    "run_scripting",
    "ScriptPayload",
    "SegmentPlan",
    "SegmentSpec",
    "ParsedSegment",
    "ScriptGenerationError",
    "ScriptParsingError",
    "ScriptValidationError",
    "count_chars",
    "normalize_text",
]
