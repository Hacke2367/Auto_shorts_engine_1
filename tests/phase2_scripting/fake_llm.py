from src.agents.phase2_scripting.contracts import SegmentPlan

def build_fake_monologue(plan: SegmentPlan, persona_id: str) -> str:
    """Returns a valid XML monologue that safely satisfies all minimum/maximum char requirements."""
    lines = ["<MONOLOGUE>"]
    for seg in plan.segments:
        # Target the midpoint of min and max limits
        target_chars = (seg.min_chars + seg.max_chars) // 2
        # Repeat a short word plus space
        text = "word " * (target_chars // 5 + 1)
        text = text[:target_chars]
        lines.append(f"<{seg.tag}>{text}</{seg.tag}>")
    lines.append("</MONOLOGUE>")
    return "\n".join(lines)

def build_bad_monologue_missing_tag(plan: SegmentPlan) -> str:
    """Omits the first required tag to simulate structural deletion."""
    lines = ["<MONOLOGUE>"]
    for seg in plan.segments[1:]:
        lines.append(f"<{seg.tag}>valid enough text</{seg.tag}>")
    lines.append("</MONOLOGUE>")
    return "\n".join(lines)

def build_bad_monologue_unknown_tag(plan: SegmentPlan) -> str:
    """Injects a rogue tag that doesn't belong in the plan."""
    lines = ["<MONOLOGUE>", "<ROGUE_TAG>text</ROGUE_TAG>"]
    for seg in plan.segments:
        lines.append(f"<{seg.tag}>valid enough text</{seg.tag}>")
    lines.append("</MONOLOGUE>")
    return "\n".join(lines)

def build_bad_monologue_too_short(plan: SegmentPlan) -> str:
    """Makes the first tag extremely short to force a char limit violation."""
    lines = ["<MONOLOGUE>"]
    lines.append(f"<{plan.segments[0].tag}>A</{plan.segments[0].tag}>")
    for seg in plan.segments[1:]:
        target_chars = (seg.min_chars + seg.max_chars) // 2
        text = "word " * (target_chars // 5 + 1)
        text = text[:target_chars]
        lines.append(f"<{seg.tag}>{text}</{seg.tag}>")
    lines.append("</MONOLOGUE>")
    return "\n".join(lines)
