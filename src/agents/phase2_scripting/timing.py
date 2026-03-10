"""
AutoShorts Phase 2 Scripting — Timing Truth
============================================
The sole source of truth for script segment ordering and text capacity limitations.
Python does all timing math based on provided mnd_sec and voice_cps.
"""

import math
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.agents.core.config import settings
from src.agents.core.job_manager import PROJECT_ROOT
from src.agents.core.models import TemplateDataset
from src.agents.phase2_scripting.contracts import SegmentPlan, SegmentSpec

# ---------------------------------------------------------------------------
# Constants & Paths
# ---------------------------------------------------------------------------
CONTEXT_DIR = PROJECT_ROOT / ".agent" / "context"

SEGMENT_TRUTH_PATH = CONTEXT_DIR / "template_segment_truth.yaml"
TIMING_REGISTRY_PATH = CONTEXT_DIR / "template_timing_registry.yaml"
VOICE_PROFILES_PATH = CONTEXT_DIR / "voice_profiles.yaml"
VISUAL_RULES_PATH = CONTEXT_DIR / "template_visual_rules.md"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Dict[str, Any]:
    """Safely loads a YAML dictionary."""
    if not path.exists():
        raise FileNotFoundError(f"Missing mandatory YAML context: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


# ---------------------------------------------------------------------------
# Core Timing Math
# ---------------------------------------------------------------------------

def build_segment_plan(
    job_id: str,
    template_name: str,
    persona_id: str,
    dataset: TemplateDataset,
) -> SegmentPlan:
    """
    Construct the definitive list of segments, applying dynamic row expansion,
    visual rules, and hard timing math.
    """
    # 1. Load context arrays
    segment_truth = _load_yaml(SEGMENT_TRUTH_PATH)
    timing_truth = _load_yaml(TIMING_REGISTRY_PATH)
    voice_profiles = _load_yaml(VOICE_PROFILES_PATH)

    # 2. Extract truth objects for this specific template
    if template_name not in segment_truth:
        raise ValueError(f"Template '{template_name}' missing from {SEGMENT_TRUTH_PATH.name}")
    if template_name not in timing_truth:
        raise ValueError(f"Template '{template_name}' missing from {TIMING_REGISTRY_PATH.name}")

    raw_order: List[str] = segment_truth[template_name].get("order", [])
    if not raw_order:
        raise ValueError(f"Empty segment order for {template_name}")

    template_timings = timing_truth[template_name]
    defaults = timing_truth.get("defaults", {})
    buffer_sec = float(defaults.get("buffer_sec", 0.6))
    max_extra_sec = float(defaults.get("max_extra_sec", 1.5))

    # 3. Determine CPS (Characters per second)
    global_cps = float(voice_profiles.get("defaults", {}).get("voice_cps", 18.0))
    persona_cps = float(voice_profiles.get("per_persona", {}).get(persona_id, {}).get("voice_cps", global_cps))

    # 4. Expand tags and calculate limits
    # e.g., ["HOOK", "SETUP", "ITEM_1..ITEM_N", "WINNER", "OUTRO"]
    expanded_tags: List[str] = []
    for raw_tag in raw_order:
        if ".._N" in raw_tag or "_1.." in raw_tag:
            # Dynamic expansion. example: "ITEM_1..ITEM_N"
            prefix = raw_tag.split("_")[0]  # "ITEM"
            num_rows = len(dataset.rows)
            for i in range(1, num_rows + 1):
                expanded_tags.append(f"{prefix}_{i}")
        else:
            expanded_tags.append(raw_tag)

    # 5. Extract Visual Rules for prompting later
    visual_rules = _load_visual_rules(template_name)

    # 6. Build final SegmentSpecs using Python timing math
    segments: List[SegmentSpec] = []
    
    for idx, tag in enumerate(expanded_tags):
        # Resolve base tag for timing lookup (e.g. "ITEM_1" -> "ITEM")
        base_tag = tag.split("_")[0] if any(char.isdigit() for char in tag) else tag
        
        # Some dynamic tags might just be Lap_1 which is base LAP
        # Check against template_timings keys directly:
        # We need to map things like "ITEM" from "ITEM_1"
        if base_tag not in template_timings:
            # Maybe the whole tag matches (e.g., HOOK)
            if tag in template_timings:
                base_tag = tag
            else:
                raise ValueError(
                    f"Timing data missing for tag '{tag}' (base '{base_tag}') "
                    f"in {template_name} section of {TIMING_REGISTRY_PATH.name}."
                )

        mnd_sec = float(template_timings[base_tag])
        
        # The Contract Math
        target_sec = mnd_sec + buffer_sec
        max_sec = target_sec + max_extra_sec
        min_chars = math.ceil(target_sec * persona_cps)
        max_chars = math.floor(max_sec * persona_cps)

        segments.append(
            SegmentSpec(
                tag=tag,
                order_index=idx,
                min_chars=min_chars,
                max_chars=max_chars,
                visual_rule=visual_rules.get(base_tag),
                required=True
            )
        )

    return SegmentPlan(
        job_id=job_id,
        template_name=template_name,
        persona_id=persona_id,
        voice_cps=persona_cps,
        segments=segments
    )


def _load_visual_rules(template_name: str) -> Dict[str, str]:
    """Parse the markdown visual rules file to attach as hints for the LLM."""
    if not VISUAL_RULES_PATH.exists():
        return {}

    rules = {}
    lines = VISUAL_RULES_PATH.read_text(encoding="utf-8").splitlines()
    
    in_target_block = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
            
        if stripped.endswith(":") and not stripped.startswith(" "):
            # We hit a top-level block (e.g., "bar_chart:")
            if stripped == f"{template_name}:":
                in_target_block = True
            else:
                in_target_block = False
            continue

        if in_target_block and ":" in stripped:
            # "  HOOK: 'description...'"
            parts = stripped.split(":", 1)
            tag = parts[0].strip()
            desc = parts[1].strip().strip("\"'")
            rules[tag] = desc

    return rules
