import json
import os
from typing import Any, Dict

JOB_ENV = "JOB_JSON_PATH"

def load_job(default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    JOB_JSON_PATH env var se job.json read karega.
    Agar missing/error -> default return (no crash).
    """
    default = default or {}
    path = os.environ.get(JOB_ENV, "").strip()
    if not path:
        return dict(default)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else dict(default)
    except Exception:
        return dict(default)
