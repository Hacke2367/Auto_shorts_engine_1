"""
AutoShorts Phase 2 Scripting — Contracts
==========================================
Defines the runtime truth models and standard exceptions for the Phase 2
Scripting Engine.

Core Responsibilities:
  - Strongly typed Pydantic models for script structuring.
  - Centralized whitespace normalization and character counting helpers.
  - Standardized scripting error definitions.
"""

import re
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ScriptParsingError(Exception):
    """Raised when the LLM output completely fails structural extraction."""
    pass


class ScriptValidationError(Exception):
    """Raised when the LLM output violates constraints (missing tags, empty, length)."""
    pass


class ScriptGenerationError(Exception):
    """Raised when all retry attempts are exhausted without yielding a valid script."""
    pass


# ---------------------------------------------------------------------------
# Centralized Char Counting Core
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Standardize whitespace for character counting.
    - Strips leading and trailing whitespace.
    - Collapses all internal whitespace sequences (newlines, tabs, multiple spaces) into a single space.
    """
    if not text:
        return ""
    # Strip ends
    text = text.strip()
    # Collapse internals
    return re.sub(r'\s+', ' ', text)


def count_chars(text: str) -> int:
    """
    Count the strictly normalized characters in a string.
    """
    return len(normalize_text(text))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SegmentSpec(BaseModel):
    """Represents one required script segment and its char limits."""
    tag: str
    order_index: int
    min_chars: int
    max_chars: int
    visual_rule: Optional[str] = None
    required: bool = True


class SegmentPlan(BaseModel):
    """Represents the full script structure truth for a specific job."""
    job_id: str
    template_name: str
    persona_id: str
    voice_cps: float
    segments: List[SegmentSpec]


class ParsedSegment(BaseModel):
    """Represents one validated, extracted written segment."""
    tag: str
    text: str
    char_count: int
    target_min_chars: int
    target_max_chars: int


class ScriptPayload(BaseModel):
    """Represents the final persisted Phase 2 output."""
    job_id: str
    template_name: str
    persona_id: str
    voice_cps: float
    inputs_hash: str
    segments: List[ParsedSegment]

