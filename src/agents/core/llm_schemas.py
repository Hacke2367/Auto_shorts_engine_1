"""
AutoShorts Core — Structured Output Schemas
===========================================
JSON Schemas for the three Phase-1 routes that must return JSON.

OpenAI's strict Structured Outputs GUARANTEES the response matches the schema,
which removes a whole class of failure the hand-written brace-scanners in
``candidate_score`` / ``api_clients`` exist to survive. Those parsers are
deliberately KEPT — the Gemini adapter only has best-effort JSON mode, and they
are the fallback when a route is pinned back to it.

Strict-mode rules these schemas must satisfy
--------------------------------------------
* root must be an object (never a bare array or anyOf)
* every object needs ``additionalProperties: false``
* EVERY property must be listed in ``required`` — even ones with defaults
* supported: string, number, boolean, integer, object, array, enum, anyOf,
  ``minimum`` / ``maximum`` / ``minItems`` / ``maxItems`` / ``pattern``
* NOT supported: ``minLength``, ``maxLength``, ``allOf``, ``if``

Two shapes that strict mode cannot express
------------------------------------------
``ScanRaceRow.entities`` and ``TemplateDataset.image_sourcing_guide`` are
open-key maps (arbitrary entity names / filenames). Strict mode requires named
properties, so the schema asks for an ARRAY OF PAIRS and
:func:`normalize_structured_payload` folds them back into dicts before pydantic
validation.

The minItems trap
-----------------
``minItems`` is supported and it is tempting to set it to the template's minimum
row count. **Never do that.** The extraction prompt explicitly says "NEVER
invent, pad, or duplicate rows to reach the target… extract only what is real" —
a schema-level minimum would override that instruction and force the model to
fabricate rows, sending hallucinated data straight to the renderer. Only
``maxItems`` is ever set.
"""

from __future__ import annotations

from typing import Any

from src.agents.core.models import (
    TEMPLATE_CAPACITIES,
    TEMPLATE_META_KEYS,
    VALID_TEMPLATES,
)


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    """Build a strict-mode object: every property required, nothing extra."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_NUM = {"type": "number"}
_INT = {"type": "integer"}


# ---------------------------------------------------------------------------
# Phase 1A — Ideation
# ---------------------------------------------------------------------------
# The route wants a flat list of topic strings, but a strict-mode root MUST be an
# object, so the array is wrapped. `_extract_json_array` unwraps {"topics": [...]}
# as well as a bare array, so both providers land in the same parser.
IDEATION_SCHEMA: dict[str, Any] = {
    "name": "topic_ideas",
    "schema": _obj({"topics": {"type": "array", "items": _STR}}),
}


# ---------------------------------------------------------------------------
# Phase 1A — Scoring
# ---------------------------------------------------------------------------
# Field order mirrors the prompt's "fields in THIS ORDER" block.
#
# `best_fit_template` as an enum is a real quality win: today an out-of-vocabulary
# template name makes _parse_scoring_response discard the whole candidate
# (candidate_score.py), silently throwing away a search + a scoring call you paid
# for. The enum makes that outcome impossible on OpenAI.
_SCORE_1_10 = {"type": "integer", "minimum": 1, "maximum": 10}

SCORING_SCHEMA: dict[str, Any] = {
    "name": "candidate_score",
    "schema": _obj({
        "data_summary": _STR,
        "template_reasoning": _STR,
        "best_fit_template": {"type": "string", "enum": sorted(VALID_TEMPLATES)},
        "rationale": _STR,
        "validation_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "hook_potential_score": _SCORE_1_10,
        "novelty_score": _SCORE_1_10,
        "visual_fit_score": _SCORE_1_10,
        "data_feasibility_score": _SCORE_1_10,
        "freshness_score": _SCORE_1_10,
        "source_hint": _STR,
    }),
}


# ---------------------------------------------------------------------------
# Phase 1B — Extraction
# ---------------------------------------------------------------------------
# Row shapes mirror the pydantic models in core/models.py. Every field is
# required even where pydantic has a default — strict mode demands it, and the
# model simply emits "" / 0 for the optional ones.
#
# The two enums below encode the RENDERER DATA CONTRACT (see
# validate_template_semantics): sort_card is a two-group "A vs B" sorter whose
# category is the integer 1 or 2, and vs_card's winner is 0/1/2. These are exactly
# the values that used to arrive as descriptive labels and fail the quality gate.
_ROW_PROPERTIES: dict[str, dict[str, Any]] = {
    "bar_chart": {"name": _STR, "value": _NUM},
    "butterfly_chart": {"attribute": _STR, "p1_value": _NUM, "p2_value": _NUM},
    "scan_race": {
        "year": _STR,
        # Open-key map -> pair array. Folded back by normalize_structured_payload.
        "entities": {
            "type": "array",
            "items": _obj({"name": _STR, "value": _NUM}),
        },
    },
    "geo_universal": {"country": _STR, "group": _STR, "value": _NUM},
    "donut_breakdown": {
        "category": _STR, "value": _NUM, "color": _STR,
        "group": _STR, "order": _INT, "note": _STR,
    },
    "sort_card": {
        "image": _STR,
        "category": {"type": "string", "enum": ["1", "2"]},
        "reason": _STR,
    },
    "vs_card": {
        "metric": _STR, "p1_value": _STR, "p2_value": _STR,
        "winner": {"type": "string", "enum": ["0", "1", "2"]},
        "emoji": _STR, "notes": _STR, "weight": _NUM, "category": _STR,
    },
}


def extraction_schema(template_name: str, has_images: bool = False) -> dict[str, Any]:
    """Strict JSON Schema for one template's extraction payload.

    ``meta`` gets exactly the template's declared keys as required properties, so
    a missing TITLE/SUB becomes impossible — which matters because the Phase 2
    topic block and the script-doctor's anti-hallucination guard both read them.
    """
    if template_name not in _ROW_PROPERTIES:
        raise ValueError(f"No extraction schema for template {template_name!r}")

    meta_keys = TEMPLATE_META_KEYS.get(template_name, ["TITLE", "SUB"])
    capacity = TEMPLATE_CAPACITIES.get(template_name)

    rows_schema: dict[str, Any] = {
        "type": "array",
        "items": _obj(_ROW_PROPERTIES[template_name]),
    }
    # maxItems ONLY. See the module docstring on why minItems would be harmful.
    if capacity is not None:
        rows_schema["maxItems"] = capacity.max

    properties: dict[str, Any] = {
        "meta": _obj({k: _STR for k in meta_keys}),
        "rows": rows_schema,
    }
    if has_images:
        # Open-key map -> pair array, same treatment as scan_race entities.
        properties["image_sourcing_guide"] = {
            "type": "array",
            "items": _obj({"filename": _STR, "description": _STR}),
        }

    return {"name": f"{template_name}_dataset", "schema": _obj(properties)}


# ---------------------------------------------------------------------------
# Pair-array -> dict normalization
# ---------------------------------------------------------------------------


def _pairs_to_dict(value: Any, key_field: str, val_field: str) -> Any:
    """Fold ``[{key_field: k, val_field: v}, ...]`` into ``{k: v}``.

    Idempotent: anything that is already a dict (or an unexpected shape) is
    returned untouched, so this is safe to run on Gemini output too.
    """
    if not isinstance(value, list):
        return value
    folded: dict[str, Any] = {}
    for item in value:
        if isinstance(item, dict) and key_field in item:
            folded[str(item[key_field])] = item.get(val_field)
    return folded


def normalize_structured_payload(parsed: Any, template_name: str) -> Any:
    """Convert strict-schema pair arrays back into the dicts pydantic expects.

    Runs BEFORE ``TemplateDataset.model_validate``. A no-op for templates with no
    open-key maps, and for payloads that already use dicts.
    """
    if not isinstance(parsed, dict):
        return parsed

    guide = parsed.get("image_sourcing_guide")
    if guide is not None:
        parsed["image_sourcing_guide"] = _pairs_to_dict(guide, "filename", "description")

    if template_name == "scan_race":
        rows = parsed.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and "entities" in row:
                    row["entities"] = _pairs_to_dict(row["entities"], "name", "value")

    return parsed
