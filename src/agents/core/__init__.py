"""
AutoShorts Phase 0 — Core Infrastructure Package
==================================================
Re-exports the three foundational modules for convenient imports::

    from src.agents.core import JobManager, setup_job_logger, timed_operation
    from src.agents.core.models import BarChartRow, AuditTrail, ...
"""

from src.agents.core.job_manager import JobManager
from src.agents.core.logger import log_api_call, setup_job_logger, timed_operation
from src.agents.core.models import (
    ArchiveEntry,
    AuditTrail,
    AuthorityTier,
    BarChartRow,
    ButterflyChartRow,
    DiscoveryBatch,
    DiscoveryDecision,
    DonutBreakdownRow,
    GeoUniversalRow,
    QueuedTopic,
    ScanRaceRow,
    SortCardRow,
    SourceAudit,
    TemplateCapacity,
    TemplateDataset,
    TemplateRow,
    TemplateSpec,
    TopicCandidate,
    SCORING_WEIGHTS,
    TEMPLATE_FALLBACKS,
    VALID_TEMPLATES,
    VsCardRow,
)

__all__ = [
    # Job Manager
    "JobManager",
    # Logger
    "setup_job_logger",
    "timed_operation",
    "log_api_call",
    # Models — Audit
    "SourceAudit",
    "AuditTrail",
    "AuthorityTier",
    # Models — Registry
    "TemplateCapacity",
    "TemplateSpec",
    "VALID_TEMPLATES",
    "TEMPLATE_FALLBACKS",
    "SCORING_WEIGHTS",
    # Models — Data Rows
    "BarChartRow",
    "ButterflyChartRow",
    "ScanRaceRow",
    "GeoUniversalRow",
    "DonutBreakdownRow",
    "SortCardRow",
    "VsCardRow",
    "TemplateRow",
    "TemplateDataset",
    # Models — Discovery
    "ArchiveEntry",
    "QueuedTopic",
    "TopicCandidate",
    "DiscoveryBatch",
    "DiscoveryDecision",
]
