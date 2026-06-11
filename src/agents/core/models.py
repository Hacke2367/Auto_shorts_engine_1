"""
AutoShorts Phase 0 — Pydantic Data Models & Audit Trail
========================================================
Source of truth for every data structure flowing through the pipeline.

Design Principles:
  - Strict typing on every field (zero hallucination).
  - SourceAudit tracks provenance of every scraped data point.
  - AuditTrail persists atomically (write-to-temp → rename).
  - Template row models enforce column schemas from templates_registry.md.
  - Capacity validation prevents visual overflow at the model layer.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Sequence, Union
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — known template names (from templates_registry.md)
# ---------------------------------------------------------------------------

VALID_TEMPLATES: frozenset[str] = frozenset(
    {
        "bar_chart",
        "butterfly_chart",
        "scan_race",
        "geo_universal",
        "donut_breakdown",
        "sort_card",
        "vs_card",
    }
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AuthorityTier(str, Enum):
    """Source credibility ranking — used for conflict resolution.

    Bloomberg / UN  >  Wikipedia  >  Social Media
    """

    PRIMARY = "primary"  # Bloomberg, UN, Govt sources
    SECONDARY = "secondary"  # Wikipedia, established news
    SOCIAL = "social"  # Reddit, Twitter, forums


# ---------------------------------------------------------------------------
# Audit Models (solves the audit-trail gap)
# ---------------------------------------------------------------------------


class SourceAudit(BaseModel):
    """A single evidence record for one scraped data point."""

    url: str = Field(..., description="Exact URL the data was fetched from.")

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"SourceAudit.url must start with http:// or https://, got: {v!r}"
            )
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError(f"SourceAudit.url has no domain: {v!r}")
        return v

    raw_snippet: str = Field(
        ..., description="Verbatim text extracted from the source."
    )
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the scrape occurred.",
    )
    authority_tier: AuthorityTier = Field(
        default=AuthorityTier.SECONDARY,
        description="Credibility tier of this source.",
    )
    context: str = Field(
        default="",
        description="Optional extra context (search query, section title, etc.).",
    )


class AuditTrail(BaseModel):
    """Full audit history for a single pipeline job."""

    job_id: str = Field(..., description="Unique job identifier.")
    template_name: str = Field(..., description="Template type for this job.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this audit trail was initialised.",
    )
    sources: list[SourceAudit] = Field(
        default_factory=list,
        description="Ordered list of every source consulted.",
    )

    @field_validator("template_name")
    @classmethod
    def _validate_template(cls, v: str) -> str:
        if v not in VALID_TEMPLATES:
            raise ValueError(
                f"Unknown template '{v}'. Valid: {sorted(VALID_TEMPLATES)}"
            )
        return v

    # -- Mutation helpers ---------------------------------------------------

    def add_source(self, source: SourceAudit) -> None:
        """Append a source record to the trail."""
        self.sources.append(source)

    # -- Persistence (atomic write) -----------------------------------------

    def save_to_file(self, directory: Path) -> Path:
        """Persist the audit trail as ``sources_audit.json``.

        Uses atomic write (temp file → rename) so a mid-write crash can
        never leave a half-written file behind.
        """
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "sources_audit.json"

        payload = self.model_dump(mode="json")
        # Serialise datetimes to ISO-8601 strings for JSON compat
        payload["created_at"] = self.created_at.isoformat()
        for src in payload.get("sources", []):
            if isinstance(src.get("scraped_at"), datetime):
                src["scraped_at"] = src["scraped_at"].isoformat()

        fd, tmp_path = tempfile.mkstemp(
            dir=str(directory), suffix=".tmp", prefix=".audit_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
            # Atomic rename (POSIX guarantees; on Windows this replaces)
            os.replace(tmp_path, str(target))
        except BaseException:
            # Clean up the temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.info("Audit trail saved -> %s (%d sources)", target, len(self.sources))
        return target


# ---------------------------------------------------------------------------
# Template Registry Models
# ---------------------------------------------------------------------------


class TemplateCapacity(BaseModel):
    """Min/max item capacity for a template."""

    max: int = Field(..., ge=1, description="Absolute maximum items.")
    ideal: int = Field(..., ge=1, description="Recommended item count.")

    @model_validator(mode="after")
    def _ideal_lte_max(self) -> "TemplateCapacity":
        if self.ideal > self.max:
            raise ValueError(
                f"ideal ({self.ideal}) must be ≤ max ({self.max})"
            )
        return self


class DataSchemaSpec(BaseModel):
    """Expected data format for a template."""

    format: Literal["csv"] = "csv"
    expected_columns: list[str] = Field(
        ..., min_length=1, description="Required column headers."
    )


class TemplateSpec(BaseModel):
    """Full specification for a single template type from the registry."""

    description: str = Field(..., description="Human-readable template purpose.")
    capacity: TemplateCapacity
    data_schema: DataSchemaSpec
    mnd_sec: dict[str, float] = Field(
        ...,
        description=(
            "Minimum non-droppable durations per segment in seconds. "
            "Keys vary by template (hook, item_n, winner, lap_n, etc.)."
        ),
    )


# ---------------------------------------------------------------------------
# Template Data Row Models (strict column enforcement)
# ---------------------------------------------------------------------------


class BarChartRow(BaseModel):
    """Single row: Name → Value ranking."""

    name: str = Field(..., min_length=1, description="Entity label.")
    value: float = Field(..., ge=0, description="Numeric metric.")


class ButterflyChartRow(BaseModel):
    """Single row: Attribute compared across 2 players."""

    attribute: str = Field(..., min_length=1, description="Comparison dimension.")
    p1_value: float = Field(..., ge=0, description="Player 1 metric.")
    p2_value: float = Field(..., ge=0, description="Player 2 metric.")


class ScanRaceRow(BaseModel):
    """Single time-series data point (one year/period)."""

    year: str = Field(..., min_length=1, description="Time period label.")
    entities: dict[str, float] = Field(
        ...,
        min_length=1,
        description="Entity name → value for this time period.",
    )


class GeoUniversalRow(BaseModel):
    """Single geographic data point."""

    country: str = Field(..., min_length=1, description="Country or region.")
    group: str = Field(..., min_length=1, description="Alliance / grouping.")
    value: float = Field(..., ge=0, description="Numeric metric.")


class DonutBreakdownRow(BaseModel):
    """Single slice of a donut/pie breakdown."""

    category: str = Field(..., min_length=1, description="Slice label.")
    value: float = Field(..., ge=0, description="Percentage or absolute value.")
    color: str = Field(default="", description="Hex colour override.")
    group: str = Field(default="", description="Optional grouping.")
    order: int = Field(default=0, ge=0, description="Display order.")
    note: str = Field(default="", description="Annotation for the slice.")


class SortCardRow(BaseModel):
    """Single card in a tier-list / sort ranking."""

    image: str = Field(default="", description="Image path or URL for the card.")
    category: str = Field(..., min_length=1, description="Tier / category label.")
    reason: str = Field(..., min_length=1, description="Why this tier?")


class VsCardRow(BaseModel):
    """Single round in a head-to-head VS comparison."""

    metric: str = Field(..., min_length=1, description="What is being compared.")
    p1_value: str = Field(..., description="Player 1 display value.")
    p2_value: str = Field(..., description="Player 2 display value.")
    winner: str = Field(..., description="Which player won this round.")
    emoji: str = Field(default="", description="Visual emoji for the metric.")
    notes: str = Field(default="", description="Extra commentary.")
    weight: float = Field(default=1.0, ge=0, description="Round weight/importance.")
    category: str = Field(default="", description="Metric category grouping.")


# ---------------------------------------------------------------------------
# Discriminated Union — TemplateDataset
# ---------------------------------------------------------------------------

# Type alias for any valid row
TemplateRow = Union[
    BarChartRow,
    ButterflyChartRow,
    ScanRaceRow,
    GeoUniversalRow,
    DonutBreakdownRow,
    SortCardRow,
    VsCardRow,
]

# Mapping from template name → expected row type
TEMPLATE_ROW_MAP: dict[str, type[BaseModel]] = {
    "bar_chart": BarChartRow,
    "butterfly_chart": ButterflyChartRow,
    "scan_race": ScanRaceRow,
    "geo_universal": GeoUniversalRow,
    "donut_breakdown": DonutBreakdownRow,
    "sort_card": SortCardRow,
    "vs_card": VsCardRow,
}

# Default capacity limits per template (from templates_registry.md)
TEMPLATE_CAPACITIES: dict[str, TemplateCapacity] = {
    "bar_chart": TemplateCapacity(max=10, ideal=6),
    "butterfly_chart": TemplateCapacity(max=10, ideal=5),
    "scan_race": TemplateCapacity(max=10, ideal=6),
    "geo_universal": TemplateCapacity(max=10, ideal=8),
    "donut_breakdown": TemplateCapacity(max=8, ideal=5),
    "sort_card": TemplateCapacity(max=8, ideal=5),
    "vs_card": TemplateCapacity(max=10, ideal=6),
}


# Human-readable data-shape descriptions for each template. Used to build the
# Phase 1 scoring/routing prompt so the LLM picks a template from the DATA's
# nature (Summary-First routing) instead of defaulting to a familiar name.
TEMPLATE_DESCRIPTIONS: dict[str, str] = {
    "bar_chart": "vertical ranked comparison of numeric values; best for 5-8 comparable "
    "items; do NOT use for fewer than 4 items",
    "vs_card": "strict 1-versus-1 between EXACTLY 2 entities across several shared metrics",
    "sort_card": "countdown / ranked reveal, one card at a time, each with a short reason; "
    "best for 'Top N' lists with qualitative reasons",
    "donut_breakdown": "parts-of-a-whole percentage split of ONE total; use only when "
    "values sum to ~100%",
    "butterfly_chart": "two GROUPS mirrored left/right across shared rows; best for "
    "'Group A vs Group B across the same dimensions'",
    "scan_race": "animated race / progression of change or ranking movement over time or stages",
    "geo_universal": "values plotted on a map, tied to countries / locations",
}


TEMPLATE_META_KEYS: dict[str, list[str]] = {
    "bar_chart": ["TITLE", "SUB", "METRIC", "UNIT"],
    "butterfly_chart": ["TITLE", "SUB", "P1", "P2"],
    "scan_race": ["TITLE", "SUB", "UNIT"],
    "geo_universal": ["TITLE", "SUB", "METRIC", "UNIT", "MODE"],
    "donut_breakdown": ["TITLE", "SUB", "UNIT"],
    "sort_card": ["TITLE", "SUB", "METRIC"],
    "vs_card": ["TITLE", "SUB", "P1_NAME", "P2_NAME"],
}


class TemplateDataset(BaseModel):
    """Validated container of rows for a specific template.

    Enforces:
    - Correct row type for the template.
    - Row count does not exceed template capacity ``max``.
    """

    template_name: str = Field(..., description="Which template this data is for.")
    meta: dict[str, str] = Field(default_factory=dict, description="Contextual meta tags generated by LLM.")
    rows: Sequence[TemplateRow] = Field(
        ..., min_length=1, description="Data rows (at least 1 required)."
    )

    @field_validator("template_name")
    @classmethod
    def _validate_template(cls, v: str) -> str:
        if v not in VALID_TEMPLATES:
            raise ValueError(
                f"Unknown template '{v}'. Valid: {sorted(VALID_TEMPLATES)}"
            )
        return v

    @model_validator(mode="after")
    def _validate_rows(self) -> "TemplateDataset":
        """Ensure all rows match the expected type and honour capacity."""
        expected_type = TEMPLATE_ROW_MAP.get(self.template_name)
        if expected_type is None:
            raise ValueError(f"No row type mapped for '{self.template_name}'.")

        for idx, row in enumerate(self.rows):
            if not isinstance(row, expected_type):
                raise ValueError(
                    f"Row {idx} is {type(row).__name__}, "
                    f"expected {expected_type.__name__} for "
                    f"template '{self.template_name}'."
                )

        cap = TEMPLATE_CAPACITIES.get(self.template_name)
        if cap and len(self.rows) > cap.max:
            raise ValueError(
                f"Template '{self.template_name}' allows max {cap.max} rows, "
                f"got {len(self.rows)}."
            )

        return self


# ---------------------------------------------------------------------------
# Template Fallback Map (from templates_registry.md v2.0)
# ---------------------------------------------------------------------------

TEMPLATE_FALLBACKS: dict[str, list[str]] = {
    "bar_chart": ["donut_breakdown", "vs_card", "butterfly_chart"],
    "butterfly_chart": ["vs_card", "bar_chart"],
    "scan_race": ["bar_chart", "geo_universal"],
    "geo_universal": ["bar_chart", "donut_breakdown"],
    "donut_breakdown": ["bar_chart", "geo_universal"],
    "sort_card": ["vs_card", "bar_chart"],
    "vs_card": ["butterfly_chart", "bar_chart"],
}


# Ideation-first scoring weights (sum = 1.0)
_NEW_SCORING_WEIGHTS: dict[str, float] = {
    "hook_potential": 0.30,
    "novelty": 0.20,
    "visual_fit": 0.20,
    "data_feasibility": 0.20,
    "freshness": 0.10,
}

# Legacy queue scoring weights (sum = 1.0 — was 0.95, fallback_strength fixed 0.05→0.10)
_LEGACY_SCORING_WEIGHTS: dict[str, float] = {
    "virality_potential": 0.25,
    "data_feasibility": 0.20,
    "template_fit": 0.20,
    "visual_potential": 0.15,
    "source_quality": 0.10,
    "fallback_strength": 0.10,   # Fixed: was 0.05 — caused legacy max score of 9.5 not 10.0
}

# Public alias: merged dict for backward compatibility with any consumer that imports SCORING_WEIGHTS
SCORING_WEIGHTS: dict[str, float] = {**_NEW_SCORING_WEIGHTS, **_LEGACY_SCORING_WEIGHTS}


# ---------------------------------------------------------------------------
# Discovery Models — Phase 1A
# ---------------------------------------------------------------------------


class ArchiveEntry(BaseModel):
    """Single timestamped archive record for produced/rejected topics."""

    topic: str = Field(..., description="Original topic string.")
    normalized_topic: str = Field(..., description="Normalised key for dedup.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this entry was recorded.",
    )
    reason: str | None = Field(
        default=None, description="Why produced/rejected (optional)."
    )


class QueuedTopic(BaseModel):
    """A strong topic saved for later re-serve (not rejected)."""

    topic: str = Field(..., description="Original topic string.")
    normalized_topic: str = Field(..., description="Normalised key for dedup.")
    best_fit_template: str = Field(..., description="Best template match.")
    fallback_template: str | None = Field(
        default=None, description="Second-choice template."
    )
    final_score: float = Field(
        ..., ge=0, le=10, description="Composite weighted score."
    )
    fit_reason: str = Field(default="", description="Why this template fits.")
    source_hint: str | None = Field(
        default=None, description="Hint about likely data sources."
    )
    saved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this topic was queued.",
    )

    @field_validator("best_fit_template")
    @classmethod
    def _validate_best_fit(cls, v: str) -> str:
        if v not in VALID_TEMPLATES:
            raise ValueError(f"Unknown template '{v}'.")
        return v

    @field_validator("fallback_template")
    @classmethod
    def _validate_fallback(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TEMPLATES:
            raise ValueError(f"Unknown template '{v}'.")
        return v


class TopicCandidate(BaseModel):
    """A fully scored discovery candidate — the output unit of Phase 1A."""

    topic: str = Field(..., min_length=1, description="Topic title.")
    normalized_topic: str = Field(..., description="Normalised key.")
    why_it_matters: str = Field(
        default="", description="Short explanation of audience relevance."
    )

    # --- Idea-First Scoring Dimensions (New) ---
    hook_potential_score: float = Field(default=0.0, ge=0, le=10)
    novelty_score: float = Field(default=0.0, ge=0, le=10)
    visual_fit_score: float = Field(default=0.0, ge=0, le=10)
    freshness_score: float = Field(default=0.0, ge=0, le=10)

    # --- Rich Metadata (New) ---
    rationale: str = Field(default="", description="Deep why-interesting breakdown")
    validation_confidence: str = Field(default="low", description="high/medium/low confidence")
    score_breakdown: dict[str, float] = Field(default_factory=dict, description="Granular viewing of scoring metrics")

    # --- Legacy 6 scoring dimensions (Kept for runtime compatibility) ---
    virality_score: float = Field(default=5.0, ge=1, le=10)
    data_feasibility_score: float = Field(default=5.0, ge=1, le=10)
    template_fit_score: float = Field(default=5.0, ge=1, le=10)
    visual_potential_score: float = Field(default=5.0, ge=1, le=10)
    source_quality_score: float = Field(default=5.0, ge=1, le=10)
    fallback_strength_score: float = Field(default=5.0, ge=1, le=10)

    final_score: float = Field(
        default=0.0, ge=0, le=10,
        description="Weighted composite score computed in Python.",
    )

    best_fit_template: str = Field(..., description="Best template.")
    fallback_template: str | None = Field(default=None)
    fit_reason: str = Field(default="", description="Why this template works.")
    data_summary: str | None = Field(
        default=None,
        description="Summary-First routing bridge: a 1-2 sentence description of the "
        "data's nature that the LLM used to deduce best_fit_template. Persisted for audit.",
    )
    source_hint: str | None = Field(
        default=None, description="Hint about likely data sources."
    )
    candidate_sources: list[str] = Field(
        default_factory=list, description="URLs or titles that informed scoring."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @field_validator("best_fit_template")
    @classmethod
    def _validate_best_fit(cls, v: str) -> str:
        # Do NOT guard with `if v` — empty strings must also be rejected
        if v not in VALID_TEMPLATES:
            raise ValueError(f"Unknown template '{v}'. Valid: {sorted(VALID_TEMPLATES)}")
        return v

    @field_validator("fallback_template")
    @classmethod
    def _validate_fallback(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TEMPLATES:
            raise ValueError(f"Unknown template '{v}'.")
        return v

    @model_validator(mode="after")
    def _ensure_final_score(self) -> "TopicCandidate":
        """Compute final score immediately upon validation."""
        self.compute_final_score()
        return self

    def compute_final_score(self) -> float:
        """Deterministic Python-side weighted score calculation.

        Uses _NEW_SCORING_WEIGHTS when hook_potential_score > 0 (ideation-first path).
        Falls back to _LEGACY_SCORING_WEIGHTS for queue-sourced candidates.
        Both weight sets sum to exactly 1.0, so max achievable score is always 10.0.
        """
        if self.hook_potential_score > 0:
            # Ideation-first calculation (weights sum = 1.0)
            w = _NEW_SCORING_WEIGHTS
            self.final_score = round(
                self.hook_potential_score * w["hook_potential"]
                + self.novelty_score * w["novelty"]
                + self.visual_fit_score * w["visual_fit"]
                + self.data_feasibility_score * w["data_feasibility"]
                + self.freshness_score * w["freshness"],
                2,
            )
            # Sync metadata representation
            self.score_breakdown = {
                "hook": self.hook_potential_score,
                "novelty": self.novelty_score,
                "visuals": self.visual_fit_score,
                "data": self.data_feasibility_score,
                "freshness": self.freshness_score,
            }
        else:
            # Legacy calculation fallback for queue-sourced topics (weights sum = 1.0)
            w = _LEGACY_SCORING_WEIGHTS
            self.final_score = round(
                self.virality_score * w["virality_potential"]
                + self.data_feasibility_score * w["data_feasibility"]
                + self.template_fit_score * w["template_fit"]
                + self.visual_potential_score * w["visual_potential"]
                + self.source_quality_score * w["source_quality"]
                + self.fallback_strength_score * w["fallback_strength"],
                2,
            )
        return self.final_score


class DiscoveryBatch(BaseModel):
    """Container for a scored batch of discovery candidates."""

    candidates: list[TopicCandidate] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    niche_hint: str | None = Field(
        default=None, description="Optional domain/niche filter used."
    )
    raw_candidate_count: int = Field(
        default=0, description="How many raw snippets were fetched from the web."
    )
    queued_candidate_count: int = Field(
        default=0, description="How many saved queue topics were injected for scoring."
    )
    returned_candidate_count: int = Field(
        default=0, description="How many scored candidates are returned."
    )
    error: str | None = Field(
        default=None,
        description="Machine-readable failure reason when the batch is empty "
        "due to an upstream failure (e.g. 'ideation_unavailable'), as opposed "
        "to simply finding no candidates.",
    )


class DiscoveryDecision(BaseModel):
    """Records a user's decision on a single candidate."""

    topic: str
    normalized_topic: str
    decision: Literal["selected", "rejected", "queued"] = Field(
        ..., description="One of: selected, rejected, queued."
    )
    chosen_template: str | None = Field(
        default=None, description="Template chosen for extraction (if selected)."
    )
    fallback_used: bool = Field(default=False)
    reason: str | None = Field(default=None)
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @field_validator("chosen_template")
    @classmethod
    def _validate_chosen_template(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TEMPLATES:
            raise ValueError(f"Unknown template '{v}'.")
        return v


if __name__ == "__main__":
    # --- ISOLATED MANUAL TESTING ---
    print("🚀 Starting Models Independent Test...\n")

    # 1. Test Capacity Enforcement on TemplateDataset
    print("Testing 1: Sending too many rows to Donut Breakdown...")

    # Donut Breakdown max capacity is 8
    too_many_rows = [
        DonutBreakdownRow(category=f"Item {i}", value=10.0)
        for i in range(10)  # We are generating 10 rows
    ]

    try:
        dataset = TemplateDataset(
            template_name="donut_breakdown",
            rows=too_many_rows
        )
        print("❌ FAILED: The model accepted 10 rows, but the max is 8!")
    except ValueError as e:
        print(f"✅ SUCCESS: Pydantic blocked the overflow. Error: {e}\n")

    # 2. Test The Flaw (Empty String Template)
    print("Testing 2: Empty string template bypass (Triggering the flaw)...")
    try:
        candidate = TopicCandidate(
            topic="Test Topic",
            normalized_topic="test_topic",
            # best_fit_template is allowed to default to "" which bypasses validation
        )
        print(
            f"✅ FLAW EXPOSED: Candidate created with best_fit_template='{candidate.best_fit_template}'. This will break extraction later.")
    except Exception as e:
        print(f"❌ Handled correctly. Error: {e}")

