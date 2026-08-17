"""
Offline tests for the Structured Outputs schemas.

Two jobs:

1. Prove every generated schema is legal under OpenAI strict mode. A schema that
   violates the rules is rejected at REQUEST time, so a mistake here breaks the
   route outright rather than degrading quietly.
2. Prove a schema-conformant payload survives the round trip
   ``normalize_structured_payload -> TemplateDataset.model_validate`` for all 7
   templates — which is what proves the pair-array workaround for
   ``scan_race.entities`` and ``image_sourcing_guide`` actually reassembles.

No network, no API keys.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.core.llm_schemas import (  # noqa: E402
    IDEATION_SCHEMA,
    SCORING_SCHEMA,
    extraction_schema,
    normalize_structured_payload,
)
from src.agents.core.models import (  # noqa: E402
    TEMPLATE_META_KEYS,
    TEMPLATE_CAPACITIES,
    VALID_TEMPLATES,
    TemplateDataset,
)

ALL_TEMPLATES = sorted(VALID_TEMPLATES)

# Keywords strict mode does not support.
_BANNED_KEYWORDS = {"minLength", "maxLength", "allOf", "if", "then", "else", "not"}


def _walk(node, path="$", depth=0):
    """Yield (path, node, depth) for every object/array schema node."""
    if not isinstance(node, dict):
        return
    yield path, node, depth
    for key, sub in (node.get("properties") or {}).items():
        yield from _walk(sub, f"{path}.{key}", depth + 1)
    items = node.get("items")
    if isinstance(items, dict):
        yield from _walk(items, f"{path}[]", depth + 1)


def _assert_strict(schema: dict, label: str):
    root = schema["schema"]
    assert root.get("type") == "object", f"{label}: strict root must be an object"

    for path, node, depth in _walk(root):
        assert depth <= 10, f"{label}: {path} exceeds 10 levels of nesting"

        for banned in _BANNED_KEYWORDS:
            assert banned not in node, f"{label}: {path} uses unsupported {banned!r}"

        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, (
                f"{label}: {path} must set additionalProperties=false"
            )
            props = set((node.get("properties") or {}).keys())
            required = set(node.get("required") or [])
            assert props == required, (
                f"{label}: {path} must list EVERY property as required "
                f"(missing: {sorted(props - required)})"
            )


# ---------------------------------------------------------------------------
# Strict-mode legality
# ---------------------------------------------------------------------------

def test_ideation_schema_is_strict_legal():
    _assert_strict(IDEATION_SCHEMA, "ideation")


def test_ideation_root_wraps_the_array():
    """A bare array root is illegal in strict mode, hence the {"topics": [...]} wrap."""
    assert IDEATION_SCHEMA["schema"]["properties"]["topics"]["type"] == "array"


def test_scoring_schema_is_strict_legal():
    _assert_strict(SCORING_SCHEMA, "scoring")


def test_scoring_pins_template_to_the_valid_set():
    """Removes the 'invalid best_fit_template -> discard a paid-for candidate' path."""
    prop = SCORING_SCHEMA["schema"]["properties"]["best_fit_template"]
    assert set(prop["enum"]) == set(VALID_TEMPLATES)


def test_scoring_scores_are_bounded_integers():
    for key in ("hook_potential_score", "novelty_score", "visual_fit_score",
                "data_feasibility_score", "freshness_score"):
        prop = SCORING_SCHEMA["schema"]["properties"][key]
        assert prop["type"] == "integer"
        assert prop["minimum"] == 1 and prop["maximum"] == 10


@pytest.mark.parametrize("template", ALL_TEMPLATES)
@pytest.mark.parametrize("has_images", [False, True])
def test_extraction_schema_is_strict_legal(template, has_images):
    _assert_strict(extraction_schema(template, has_images), f"{template}/images={has_images}")


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_extraction_schema_never_sets_min_items(template):
    """minItems would force the model to FABRICATE rows to satisfy the schema.

    The extraction prompt explicitly says "NEVER invent, pad, or duplicate rows
    to reach the target". A schema-level minimum overrides that instruction and
    sends hallucinated data to the renderer.
    """
    for _, node, _ in _walk(extraction_schema(template, True)["schema"]):
        assert "minItems" not in node, f"{template}: minItems must never be set"


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_extraction_schema_caps_rows_at_template_capacity(template):
    rows = extraction_schema(template, False)["schema"]["properties"]["rows"]
    assert rows["maxItems"] == TEMPLATE_CAPACITIES[template].max


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_extraction_meta_requires_exactly_the_declared_keys(template):
    """Guarantees the Phase 2 topic block never sees a missing TITLE/SUB."""
    meta = extraction_schema(template, False)["schema"]["properties"]["meta"]
    assert set(meta["properties"]) == set(TEMPLATE_META_KEYS[template])
    assert set(meta["required"]) == set(TEMPLATE_META_KEYS[template])


def test_renderer_contract_values_are_pinned_as_enums():
    """sort_card category and vs_card winner are the fields that used to arrive
    as descriptive labels and fail validate_template_semantics."""
    sort_row = extraction_schema("sort_card", True)["schema"]["properties"]["rows"]["items"]
    assert sort_row["properties"]["category"]["enum"] == ["1", "2"]

    vs_row = extraction_schema("vs_card", False)["schema"]["properties"]["rows"]["items"]
    assert vs_row["properties"]["winner"]["enum"] == ["0", "1", "2"]


def test_unknown_template_raises():
    with pytest.raises(ValueError, match="No extraction schema"):
        extraction_schema("not_a_template")


# ---------------------------------------------------------------------------
# Round trip: schema-conformant payload -> pydantic
# ---------------------------------------------------------------------------


def _synth(node):
    """Build a minimal value that conforms to ``node``."""
    if "enum" in node:
        return node["enum"][0]
    kind = node.get("type")
    if kind == "object":
        return {k: _synth(v) for k, v in (node.get("properties") or {}).items()}
    if kind == "array":
        return [_synth(node["items"]) for _ in range(3)]
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.5
    if kind == "boolean":
        return True
    return "x"


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_conformant_payload_survives_normalize_and_validate(template):
    has_images = template == "sort_card"
    payload = _synth(extraction_schema(template, has_images)["schema"])

    # scan_race entities and image_sourcing_guide arrive as PAIR ARRAYS.
    if template == "scan_race":
        assert isinstance(payload["rows"][0]["entities"], list)
    if has_images:
        assert isinstance(payload["image_sourcing_guide"], list)

    normalized = normalize_structured_payload(payload, template)

    if template == "scan_race":
        assert isinstance(normalized["rows"][0]["entities"], dict)
    if has_images:
        assert isinstance(normalized["image_sourcing_guide"], dict)

    dataset = TemplateDataset.model_validate({
        "template_name": template,
        "meta": normalized["meta"],
        "rows": normalized["rows"],
        "image_sourcing_guide": normalized.get("image_sourcing_guide", {}),
    })
    assert len(dataset.rows) == 3


def test_normalize_is_idempotent_on_dict_payloads():
    """Gemini emits real dicts, so normalization must be a no-op there."""
    payload = {
        "meta": {"TITLE": "t", "SUB": "s", "UNIT": "u"},
        "rows": [{"year": "2024", "entities": {"India": 1.0}}],
    }
    once = normalize_structured_payload(payload, "scan_race")
    twice = normalize_structured_payload(once, "scan_race")
    assert twice["rows"][0]["entities"] == {"India": 1.0}


def test_normalize_tolerates_garbage_without_raising():
    """Normalization sits in front of validation; it must never add a failure mode."""
    assert normalize_structured_payload("not a dict", "scan_race") == "not a dict"
    assert normalize_structured_payload({"rows": "nope"}, "scan_race") == {"rows": "nope"}
    weird = normalize_structured_payload({"image_sourcing_guide": 42}, "sort_card")
    assert weird["image_sourcing_guide"] == 42
