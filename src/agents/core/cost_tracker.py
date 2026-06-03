import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def record_cost(job_dir: Path | str, record: dict[str, Any]) -> None:
    """Record cost/usage info for a single pipeline step in JSONL format.

    This function is fire-and-forget: failures are logged as warnings and
    never propagate to the caller. The pipeline must never crash due to
    cost-tracking errors.

    Args:
        job_dir: Path to the job directory. A ``logs/`` subdirectory will
                 be created if missing.
        record: Arbitrary dict of cost/usage data. A ``recorded_at`` ISO-8601
                timestamp is injected automatically if not already present.
                Unserializable values (e.g. Path objects) are coerced via
                ``str()`` rather than raising TypeError.
    """
    try:
        job_dir = Path(job_dir)
        logs_dir = job_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Inject timestamp if caller did not provide one
        if "recorded_at" not in record:
            record = {**record, "recorded_at": datetime.now(timezone.utc).isoformat()}

        cost_file = logs_dir / "cost.jsonl"
        with open(cost_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    except Exception as exc:
        logger.warning(
            "Cost record failed (non-fatal): %s — job_dir=%s",
            exc,
            job_dir,
        )
