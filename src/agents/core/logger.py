"""
AutoShorts Phase 0 — Structured Job Logger
============================================
Dual-output logging: human-readable console + JSON-lines file.

Design Principles:
  - Every job gets its own ``pipeline_execution.log`` inside job_dir.
  - Console output is coloured and concise for developer UX.
  - File output is machine-parseable JSON-lines for post-mortem analysis.
  - ``timed_operation`` context manager auto-tracks durations.
  - ``log_api_call`` emits structured records for API observability.
  - Duplicate-handler guard: calling setup twice with same job_id is safe.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Internal registry: prevents duplicate handlers on repeated setup calls
# ---------------------------------------------------------------------------
_INITIALISED_LOGGERS: dict[str, logging.Logger] = {}


# ---------------------------------------------------------------------------
# Custom JSON-lines formatter (file handler)
# ---------------------------------------------------------------------------


class _JSONLineFormatter(logging.Formatter):
    """Emits each log record as a single JSON object per line.

    Schema:
        {"ts": "...", "level": "...", "logger": "...", "msg": "...",
         "job_id": "...", "extra": {...}}
    """

    def __init__(self, job_id: str) -> None:
        super().__init__()
        self._job_id = job_id

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "job_id": self._job_id,
        }

        # Attach any structured extras the caller passed via ``extra={"data": ...}``
        extra_data: dict[str, Any] = {}
        # Ignore Python's internal logging keys, grab everything else automatically
        standard_keys = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info",
                         "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated",
                         "thread", "threadName", "processName", "process", "message", "asctime"}

        for key, val in record.__dict__.items():
            if key not in standard_keys and key != "job_id" and not key.startswith("_"):
                extra_data[key] = val
        if extra_data:
            entry["extra"] = extra_data

        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Custom console formatter (coloured, human-readable)
# ---------------------------------------------------------------------------

_LEVEL_COLOURS: dict[str, str] = {
    "DEBUG": "\033[90m",       # grey
    "INFO": "\033[36m",        # cyan
    "WARNING": "\033[33m",     # yellow
    "ERROR": "\033[31m",       # red
    "CRITICAL": "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class _ConsoleFormatter(logging.Formatter):
    """Human-readable coloured console output."""

    def format(self, record: logging.LogRecord) -> str:
        colour = _LEVEL_COLOURS.get(record.levelname, "")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        prefix = f"{colour}[{record.levelname:<8}]{_RESET}"
        source = f"\033[90m{record.name}\033[0m"
        msg = record.getMessage()

        # Append duration if present
        duration = getattr(record, "duration_ms", None)
        if duration is not None:
            msg += f" ({duration:.0f}ms)"

        line = f"{ts} {prefix} {source} | {msg}"

        if record.exc_info and record.exc_info[1] is not None:
            line += "\n" + self.formatException(record.exc_info)

        return line


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def setup_job_logger(
    job_dir: Path,
    job_id: str,
    *,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> logging.Logger:
    """Create (or retrieve) a logger for a specific pipeline job.

    Args:
        job_dir: Absolute path to the job directory. Created if missing.
        job_id: Unique job identifier (used as logger name suffix).
        console_level: Minimum severity for console output.
        file_level: Minimum severity for file output.

    Returns:
        A configured ``logging.Logger`` instance.

    Idempotency:
        Multiple calls with the same ``job_id`` return the **same** logger
        without adding duplicate handlers.
    """
    if job_id in _INITIALISED_LOGGERS:
        return _INITIALISED_LOGGERS[job_id]

    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    log_name = f"autoshorts.pipeline.{job_id}"
    log = logging.getLogger(log_name)
    log.setLevel(logging.DEBUG)  # handlers filter from here
    log.propagate = False  # avoid duplicate output from root logger

    # --- File handler (JSON-lines) -----------------------------------------
    log_file = job_dir / "pipeline_execution.log"
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(file_level)
    fh.setFormatter(_JSONLineFormatter(job_id))
    log.addHandler(fh)

    # --- Console handler (human-readable) ----------------------------------
    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(_ConsoleFormatter())
    log.addHandler(ch)

    _INITIALISED_LOGGERS[job_id] = log
    log.info("Logger initialised — log file: %s", log_file)
    return log


# ---------------------------------------------------------------------------
# Convenience utilities
# ---------------------------------------------------------------------------


@contextmanager
def timed_operation(
    log: logging.Logger,
    operation_name: str,
    **extra: Any,
) -> Generator[None, None, None]:
    """Context manager that logs start/end of an operation with duration.

    Usage::

        with timed_operation(logger, "phase1_discovery"):
            await scrape_data(...)

    On success, emits an INFO log with ``duration_ms``.
    On exception, emits an ERROR log with the traceback, then re-raises.
    """
    log.info(
        "▶ START  %s",
        operation_name,
        extra={"operation": operation_name, **extra},
    )
    t0 = time.perf_counter()
    try:
        yield
    except BaseException as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.error(
            "✖ FAILED %s after %.0fms — %s: %s",
            operation_name,
            elapsed_ms,
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={
                "operation": operation_name,
                "duration_ms": elapsed_ms,
                "error": str(exc),
                **extra,
            },
        )
        raise
    else:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "✔ DONE   %s (%.0fms)",
            operation_name,
            elapsed_ms,
            extra={
                "operation": operation_name,
                "duration_ms": elapsed_ms,
                **extra,
            },
        )


def log_api_call(
    log: logging.Logger,
    *,
    service: str,
    status_code: int,
    retry_count: int = 0,
    duration_ms: float = 0.0,
) -> None:
    """Emit a structured log entry for an external API call.

    Args:
        log: The job logger.
        service: API name (e.g. ``"elevenlabs"``, ``"tavily"``).
        status_code: HTTP status code received.
        retry_count: How many retries were needed (0 = first attempt).
        duration_ms: Round-trip time in milliseconds.
    """
    level = logging.INFO if 200 <= status_code < 400 else logging.WARNING
    log.log(
        level,
        "API %s → %d (retries=%d, %.0fms)",
        service,
        status_code,
        retry_count,
        duration_ms,
        extra={
            "service": service,
            "status_code": status_code,
            "retry_count": retry_count,
            "duration_ms": duration_ms,
        },
    )


if __name__ == "__main__":
    import shutil

    # --- ISOLATED MANUAL TESTING ---
    print("🚀 Starting Logger Independent Test...\n")

    test_dir = Path("test_job_logs")
    test_id = "test_123"

    # 1. Test Setup
    print("Testing 1: Initializing logger...")
    log = setup_job_logger(test_dir, test_id)
    print(f"✅ Logger created. Check folder: {test_dir}\n")

    # 2. Test Timed Operation
    print("Testing 2: Running a timed operation (simulating a 1-second task)...")
    with timed_operation(log, "fake_api_call"):
        time.sleep(1)  # Simulate work
    print("✅ Check your console, it should show ▶ START and ✔ DONE with ~1000ms duration.\n")

    # 3. Test The Flaw (Silent Data Drop)
    print("Testing 3: Logging a custom extra variable (Triggering the flaw)...")
    log.info("I found a cool topic!", extra={"my_secret_topic": "AI History"})

    # Let's read the JSON file to see if 'my_secret_topic' actually got saved
    log_file = test_dir / "pipeline_execution.log"
    print(f"Reading {log_file} to verify...")

    found_secret = False
    with open(log_file, "r") as f:
        for line in f:
            if "my_secret_topic" in line:
                found_secret = True

    if found_secret:
        print("✅ SUCCESS: Custom data was saved.")
    else:
        print(
            "❌ FATAL FLAW EXPOSED: The JSON log file completely ignored 'my_secret_topic' because it wasn't in the hardcoded tuple! You just lost critical debugging data.")

    # Cleanup test dir
    shutil.rmtree(test_dir, ignore_errors=True)
