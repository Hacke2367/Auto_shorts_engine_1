"""
AutoShorts Phase 2 Scripting — XML Parser
==========================================
Enforces the strict structural contract of LLM monologues.
Extracts exact segment tags, validates ordering against SegmentPlan,
computes normalized character limits, and bubbles up errors for LLM retry.
"""

import re
from typing import List

from src.agents.phase2_scripting.contracts import (
    ParsedSegment,
    ScriptParsingError,
    SegmentPlan,
    count_chars,
    normalize_text,
)


def parse_monologue(raw_output: str, plan: SegmentPlan) -> List[ParsedSegment]:
    """
    Parses the LLM output into validated ParsedSegment objects.
    
    Validates:
      1. Presence of <MONOLOGUE> wrapper
      2. All plan tags exist
      3. No empty tags
      4. Exact ordering matched
      5. No unknown/unplanned tags
    
    Important: Character limit validation is left out of this structural parser,
    so that `llm_writer.py` can receive the parsed object and retry *only* the failing tags.
    """
    
    # 1. Verify Outer Wrapper.
    mono_match = re.search(r"<MONOLOGUE>(.*)</MONOLOGUE>", raw_output, re.DOTALL | re.IGNORECASE)
    if not mono_match:
        raise ScriptParsingError("Raw output missing <MONOLOGUE>...</MONOLOGUE> wrapper.")
        
    mono_content = mono_match.group(1).strip()
    
    # 2. Extract all tags linearly using a Regex parser
    # Match strings shaped like <TAG>content</TAG>
    # Note: re.finditer catches them in the exact order they appeared in the text.
    tag_pattern = re.compile(r"<([A-Z0-9_]+)>(.*?)</\1>", re.DOTALL)
    
    found_elements = []
    for match in tag_pattern.finditer(mono_content):
        tag_name = match.group(1).strip()
        tag_text = normalize_text(match.group(2))
        found_elements.append((tag_name, tag_text))

    if not found_elements:
        raise ScriptParsingError("No valid XML tags found inside <MONOLOGUE>.")

    # 3. Check for structural failures against the Plan
    expected_tags = [spec.tag for spec in plan.segments]
    found_tags = [tag for tag, _ in found_elements]

    # Rule: No missing tags
    missing = set(expected_tags) - set(found_tags)
    if missing:
        raise ScriptParsingError(f"Missing expected tags: {sorted(missing)}")

    # Rule: No extra/unknown tags
    extra = set(found_tags) - set(expected_tags)
    if extra:
        raise ScriptParsingError(f"Found unplanned/unknown tags: {sorted(extra)}")

    # Rule: No duplicates
    if len(found_tags) != len(set(found_tags)):
        # find specifically which ones duplicated
        from collections import Counter
        dupes = [tag for tag, count in Counter(found_tags).items() if count > 1]
        raise ScriptParsingError(f"Found duplicate tags: {sorted(dupes)}")

    # Rule: Exact strict ordering
    if found_tags != expected_tags:
        raise ScriptParsingError(f"Incorrect tag ordering. Expected: {expected_tags}, Got: {found_tags}")

    # 4. Build output models, enforcing 'no empty tags'
    parsed_segments: List[ParsedSegment] = []
    for spec in plan.segments:
        # We know they match 1:1 in order now
        idx = expected_tags.index(spec.tag)
        _, text = found_elements[idx]
        
        if not text:
            raise ScriptParsingError(f"Tag <{spec.tag}> is empty.")

        parsed_segments.append(
            ParsedSegment(
                tag=spec.tag,
                text=text,
                char_count=count_chars(text),
                target_min_chars=spec.min_chars,
                target_max_chars=spec.max_chars
            )
        )

    return parsed_segments

