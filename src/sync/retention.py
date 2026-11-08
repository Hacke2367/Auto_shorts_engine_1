# src/sync/retention.py
# Backward-compatible re-export shim.
# All implementation lives in retention_base.py.
# Templates import from here unchanged: `from src.sync.retention import hold_breathing, ...`
from src.sync.retention_base import (  # noqa: F401
    hold_breathing,
    sync_hold,
    banner_scan_hold,
    register_template_accent,
)

__all__ = ["hold_breathing", "sync_hold", "banner_scan_hold", "register_template_accent"]
