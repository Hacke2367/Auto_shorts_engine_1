import json
import logging
import os
from typing import Any, Dict

_log = logging.getLogger(__name__)

JOB_ENV = "JOB_JSON_PATH"

def load_job(default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Reads job.json from the JOB_JSON_PATH env var.
    If the var is unset, or the file is missing/unreadable, returns default (no crash).
    All errors are logged as warnings so the caller can see what went wrong.
    """
    default = default or {}
    path = os.environ.get(JOB_ENV, "").strip()
    if not path:
        return dict(default)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else dict(default)
    except Exception as e:
        _log.warning("load_job: failed to read %s: %s", path, e, exc_info=True)
        return dict(default)
