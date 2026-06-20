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


def resolve_job_csv(default_name: str, data_dir: str | None = None) -> str:
    """Resolve THIS job's data CSV path — the renderer-side fix for templates that
    used to read a hardcoded global CSV and ignore the job's own data.

    Order: job.json's ``data_csv`` (resolved against the job dir) ->
    ``<job_dir>/data/<default_name>`` -> legacy ``<data_dir>/<default_name>``.
    Reads JOB_JSON_PATH/JOB_DIR (set by main.py). Never raises; always returns a
    string path (the legacy fallback if nothing job-specific is found).
    """
    legacy = os.path.join(data_dir, default_name) if data_dir else default_name
    job_json = os.environ.get(JOB_ENV, "").strip()
    job_dir_env = os.environ.get("JOB_DIR", "").strip()

    job_dir = job_dir_env or (os.path.dirname(job_json) if job_json else "")
    if not job_dir:
        return legacy

    try:
        candidates = []
        rel = ""
        if job_json and os.path.exists(job_json):
            with open(job_json, "r", encoding="utf-8") as f:
                rel = str((json.load(f) or {}).get("data_csv", "")).strip()
        if rel:
            candidates.append(rel if os.path.isabs(rel) else os.path.join(job_dir, rel))
        candidates.append(os.path.join(job_dir, "data", default_name))
        for c in candidates:
            if c and os.path.exists(c):
                return os.path.abspath(c)
    except Exception as e:
        _log.warning("resolve_job_csv: failed (%s); using legacy %s", e, legacy)
    return legacy
