# Refactor Plan — `src/agents/core/`

**Target:** `src/agents/core/` (7 files)  
**Source:** `CODE_REVIEW.md` (Expert Level, 2026-05-22)  
**Total Changes:** 15 refactors  
**Estimated Risk:** Medium (2 high-risk structural changes, rest are Low)  
**Estimated Time:** ~4–6 hours total; 20 min for cleanup, 2 hrs for structural

---

## Refactor Summary

| ID | File | Type | Risk | Time |
|----|------|------|------|------|
| R-01 | `models.py` | Bug Fix — Validator | Low | 5 min |
| R-02 | `models.py` | Bug Fix — Scoring Math | Low | 10 min |
| R-03 | `cost_tracker.py` | Error Handling | Low | 10 min |
| R-04 | `logger.py` | Thread Safety + Resource | Medium | 20 min |
| R-05 | `logger.py` | Bug Fix — 5xx Severity | Low | 5 min |
| R-06 | `logger.py` | Bug Fix — BaseException | Low | 5 min |
| R-07 | `logger.py` | Performance — constant | Low | 5 min |
| R-08 | `job_manager.py` | Cleanup — dead code | Very Low | 5 min |
| R-09 | `rate_limiter.py` | Cleanup — comment | Very Low | 2 min |
| R-10 | `rate_limiter.py` | Feature — timeout safety | Low | 15 min |
| R-11 | `rate_limiter.py` | Feature — observability | Low | 15 min |
| R-12 | `__init__.py` | API Completeness | Low | 5 min |
| R-13 | `models.py` | Validation — URL | Low | 10 min |
| R-14 | `job_manager.py` → `runner.py` | SRP — structural move | Medium | 30 min |
| R-15 | `config.py` | Architecture — testability | High | 60 min |

---

## 🔴 High Priority (Do First)

---

### R-01: Fix `TopicCandidate._validate_best_fit` — Empty String Bypass

**Type:** Bug Fix — Validator  
**Location:** `src/agents/core/models.py`, line 500  

**Current Problem:**
```python
# Line 500 — `if v` allows "" to pass through silently
@field_validator("best_fit_template")
@classmethod
def _validate_best_fit(cls, v: str) -> str:
    if v and v not in VALID_TEMPLATES:   # ← BUG: "if v" skips empty strings
        raise ValueError(f"Unknown template '{v}'.")
    return v
```
`TopicCandidate(best_fit_template="")` is accepted silently. This crashes Phase 1 extraction with a confusing `KeyError` on `TEMPLATE_ROW_MAP[""]`, not a validation error. The flaw is even documented in the `__main__` test block (line 626).

**Solution:**
1. Open `src/agents/core/models.py`, go to line 500.
2. Change this exact line:
   ```python
   if v and v not in VALID_TEMPLATES:
   ```
   To:
   ```python
   if v not in VALID_TEMPLATES:
   ```
3. No other changes needed. `QueuedTopic` already uses the correct form — this makes `TopicCandidate` consistent with it.

**Risk:** Low — Makes validation **stricter**. Any code that was passing `best_fit_template=""` and relying on the bypass will now get a `ValidationError` at model construction time (the correct behavior).  
**Behavior Change:** None for valid data. Invalid data (`""`) now raises `ValidationError` instead of silently passing.

---

### R-02: Fix Legacy Scoring Weights — Math Bug

**Type:** Bug Fix — Scoring Math  
**Location:** `src/agents/core/models.py`, lines 383–395 (SCORING_WEIGHTS dict), lines 542–551 (legacy branch of `compute_final_score`)

**Current Problem:**
```python
# Legacy branch weights sum to 0.95, not 1.0
virality(0.25) + data_feasibility(0.20) + template_fit(0.20) 
+ visual_potential(0.15) + source_quality(0.10) + fallback_strength(0.05) = 0.95
```
Queue-based legacy candidates can only score max `9.5`, while new ideation-first candidates can score `10.0`. They are ranked in the same batch — legacy topics are unfairly disadvantaged by 5%.

**Solution:**

**Step 1 — Split `SCORING_WEIGHTS` into two explicit dicts** (lines 383–395 in `models.py`):

Replace this:
```python
SCORING_WEIGHTS: dict[str, float] = {
    "hook_potential": 0.30,
    "novelty": 0.20,
    "visual_fit": 0.20,
    "data_feasibility": 0.20,
    "freshness": 0.10,
    # Legacy weights for backward compatibility
    "virality_potential": 0.25,
    "template_fit": 0.20,
    "visual_potential": 0.15,
    "source_quality": 0.10,
    "fallback_strength": 0.05,
}
```

With:
```python
# Ideation-first scoring weights (sum = 1.0)
_NEW_SCORING_WEIGHTS: dict[str, float] = {
    "hook_potential": 0.30,
    "novelty": 0.20,
    "visual_fit": 0.20,
    "data_feasibility": 0.20,
    "freshness": 0.10,
}

# Legacy queue scoring weights (sum = 1.0 — fixed from 0.95)
_LEGACY_SCORING_WEIGHTS: dict[str, float] = {
    "virality_potential": 0.25,
    "data_feasibility": 0.20,
    "template_fit": 0.20,
    "visual_potential": 0.15,
    "source_quality": 0.10,
    "fallback_strength": 0.10,   # was 0.05 — fixed to make sum = 1.0
}

# Keep public alias for backward compatibility with any consumer that imports it
SCORING_WEIGHTS: dict[str, float] = {**_NEW_SCORING_WEIGHTS, **_LEGACY_SCORING_WEIGHTS}
```

**Step 2 — Update `compute_final_score` to use the split dicts** (lines 519–552):

```python
def compute_final_score(self) -> float:
    """Deterministic Python-side weighted score calculation."""
    if self.hook_potential_score > 0:
        # Ideation-first calculation
        w = _NEW_SCORING_WEIGHTS
        self.final_score = round(
            self.hook_potential_score * w["hook_potential"]
            + self.novelty_score * w["novelty"]
            + self.visual_fit_score * w["visual_fit"]
            + self.data_feasibility_score * w["data_feasibility"]
            + self.freshness_score * w["freshness"],
            2,
        )
        self.score_breakdown = {
            "hook": self.hook_potential_score,
            "novelty": self.novelty_score,
            "visuals": self.visual_fit_score,
            "data": self.data_feasibility_score,
            "freshness": self.freshness_score,
        }
    else:
        # Legacy calculation fallback (Queue items)
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
```

**Risk:** Low. Scoring values for legacy candidates will increase slightly (max goes from 9.5 to 10.0). Any hardcoded score thresholds in filtering logic should be verified, but this is a correction not a regression.  
**Behavior Change:** Legacy queue topics now score ~5% higher. Their ranking relative to ideation-first topics becomes fair.

---

### R-03: Make `cost_tracker.py` Pipeline-Safe

**Type:** Error Handling  
**Location:** `src/agents/core/cost_tracker.py`, lines 5–13

**Current Problem:**
```python
def record_cost(job_dir: Path | str, record: dict[str, Any]) -> None:
    job_dir = Path(job_dir)
    logs_dir = job_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)   # ← can raise PermissionError, OSError
    cost_file = logs_dir / "cost.jsonl"
    with open(cost_file, "a", encoding="utf-8") as f:   # ← can raise OSError
        f.write(json.dumps(record, ensure_ascii=False) + "\n")  # ← can raise TypeError
```
Any of these can crash the pipeline. The module has no logger and no error handling.

**Solution — Replace the entire file with:**

```python
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
```

**Risk:** Low. Wrapping in try/except only adds protection — no logic changes.  
**Behavior Change:** Pipeline no longer crashes on cost-tracking failures. Invalid `record` values (e.g. `Path` objects) are now serialized via `default=str` instead of raising `TypeError`.

---

### R-04: Fix Logger Thread Safety and File-Descriptor Leak

**Type:** Thread Safety + Resource Management  
**Location:** `src/agents/core/logger.py`, lines 28, 140–164

**Current Problem — Part A (thread safety):**
```python
_INITIALISED_LOGGERS: dict[str, logging.Logger] = {}  # Not protected by a lock
...
if job_id in _INITIALISED_LOGGERS:   # check — not atomic with the set below
    return _INITIALISED_LOGGERS[job_id]
...
_INITIALISED_LOGGERS[job_id] = log   # set — two threads can both reach here
```
Two threads calling `setup_job_logger("same_id")` simultaneously both pass the `if` check and both attach `FileHandler` + `StreamHandler` → every log line doubles.

**Current Problem — Part B (FD leak):**
`FileHandler` objects are created and stored but never closed. In a long-running discovery session creating hundreds of jobs, file descriptors accumulate until the OS limit.

**Solution — 3-part fix in `logger.py`:**

**Part 1 — Add a module-level lock** (after line 28):
```python
import threading
_INITIALISED_LOGGERS: dict[str, logging.Logger] = {}
_REGISTRY_LOCK: threading.Lock = threading.Lock()
```

**Part 2 — Protect `setup_job_logger` with the lock** (replace lines 140–166):
```python
def setup_job_logger(
    job_dir: Path,
    job_id: str,
    *,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> logging.Logger:
    """Create (or retrieve) a logger for a specific pipeline job.
    Thread-safe: multiple threads calling with the same job_id receive the
    same logger without duplicate handlers.
    """
    with _REGISTRY_LOCK:
        if job_id in _INITIALISED_LOGGERS:
            return _INITIALISED_LOGGERS[job_id]

        job_dir = Path(job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)

        log_name = f"autoshorts.pipeline.{job_id}"
        log = logging.getLogger(log_name)
        log.setLevel(logging.DEBUG)
        log.propagate = False

        log_file = job_dir / "pipeline_execution.log"
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setLevel(file_level)
        fh.setFormatter(_JSONLineFormatter(job_id))
        log.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch.setFormatter(_ConsoleFormatter())
        log.addHandler(ch)

        _INITIALISED_LOGGERS[job_id] = log

    log.info("Logger initialised — log file: %s", log_file)
    return log
```

**Part 3 — Add `teardown_job_logger` function** (add after `setup_job_logger`):
```python
def teardown_job_logger(job_id: str) -> None:
    """Close handlers and remove the logger for a completed job.

    Call this when a job finishes to release its file descriptor.
    Safe to call even if the logger was never initialised.

    Args:
        job_id: The same identifier used in ``setup_job_logger``.
    """
    with _REGISTRY_LOCK:
        log = _INITIALISED_LOGGERS.pop(job_id, None)
        if log is None:
            return

    for handler in list(log.handlers):
        try:
            handler.close()
        except Exception:
            pass
        log.removeHandler(handler)
```

Also add `teardown_job_logger` to `__init__.py` exports (see R-12).

**Risk:** Medium. The `threading.Lock` changes synchronization behavior. Test with: run `setup_job_logger` in a thread pool with the same `job_id` 10 times and verify only one set of handlers is attached and one file is created.  
**Behavior Change:** Thread-safe. Duplicate handler bug fixed. Jobs can now be cleanly torn down.

---

### R-05: Fix `log_api_call` — 5xx Must Be `ERROR`, Not `WARNING`

**Type:** Bug Fix — Observability  
**Location:** `src/agents/core/logger.py`, line 246

**Current Problem:**
```python
level = logging.INFO if 200 <= status_code < 400 else logging.WARNING
```
A `503 Service Unavailable` or `500 Internal Server Error` from Gemini is logged as `WARNING`. Alerting systems that watch for `ERROR` lines will miss critical failures.

**Solution — Replace line 246:**
```python
if 200 <= status_code < 400:
    level = logging.INFO
elif status_code >= 500:
    level = logging.ERROR     # Server-side failure — pipeline is in danger
else:
    level = logging.WARNING   # 4xx — client error (auth, rate limit, etc.)
```

**Risk:** Low. Additive change — no behavior change except log level on 5xx responses.  
**Behavior Change:** 5xx API responses now emit `ERROR` log entries. Monitoring/alerting systems will correctly detect them.

---

### R-06: Fix `timed_operation` — Don't Log `SystemExit`/`KeyboardInterrupt` as Failures

**Type:** Bug Fix — Correctness  
**Location:** `src/agents/core/logger.py`, lines 198–213

**Current Problem:**
```python
except BaseException as exc:
    ...
    log.error("✖ FAILED %s ...", ...)   # Fires even for Ctrl+C and sys.exit()
    raise
```
`Ctrl+C` during a pipeline run produces a spurious `✖ FAILED` log entry, polluting post-mortem logs.

**Solution — Replace the except block (lines 198–214):**
```python
    except BaseException as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # Don't log controlled shutdowns as failures
        if not isinstance(exc, (SystemExit, KeyboardInterrupt)):
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
```

**Risk:** Low. Purely additive guard — the re-raise is unchanged.  
**Behavior Change:** `SystemExit` and `KeyboardInterrupt` no longer produce `✖ FAILED` entries. All real exceptions still produce them.

---

## 🟡 Medium Priority

---

### R-07: Extract `standard_keys` to Module-Level Constant

**Type:** Performance — Constant Allocation  
**Location:** `src/agents/core/logger.py`, lines 60–62

**Current Problem:**
```python
def format(self, record: logging.LogRecord) -> str:
    ...
    standard_keys = {"name", "msg", "args", ...}   # rebuilt on EVERY log record
```
A Python set literal of 21 strings is allocated fresh for each log call. In a high-volume phase, this is unnecessary GC pressure.

**Solution:**

**Step 1** — Add module-level constant after line 27 (after the imports):
```python
# Standard logging.LogRecord attributes — excluded from the "extra" capture
_STANDARD_LOG_KEYS: frozenset[str] = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
})
```

**Step 2** — Replace lines 60–62 inside `_JSONLineFormatter.format()`:
```python
# Before
standard_keys = {"name", "msg", "args", ...}   # ← remove this

# After — just use the constant
for key, val in record.__dict__.items():
    if key not in _STANDARD_LOG_KEYS and key != "job_id" and not key.startswith("_"):
        extra_data[key] = val
```

**Risk:** Very Low. Semantically identical — just moves allocation from call-time to module-load-time.  
**Behavior Change:** None.

---

### R-08: Remove Dead Code and Dev Artifacts from `job_manager.py`

**Type:** Cleanup  
**Location:** `src/agents/core/job_manager.py`, lines 41 and 270

**Current Problem A — Dead module-level logger (line 41):**
```python
logger = logging.getLogger(__name__)   # never used; all logging via self.get_logger()
```

**Current Problem B — Development comment artifact (line 270):**
```python
self._job_dir.mkdir(parents=True, exist_ok=True) # ADD THIS LINE  ← development noise
```

**Solution:**

1. Delete line 41 entirely (the `logger = logging.getLogger(__name__)` line).
2. On line 270, remove the inline comment `# ADD THIS LINE`, keeping the code:
   ```python
   self._job_dir.mkdir(parents=True, exist_ok=True)
   ```

**Risk:** Very Low. These are zero-logic changes.  
**Behavior Change:** None.

---

### R-09: Fix Contradictory Comment in `rate_limiter.py`

**Type:** Cleanup — Documentation  
**Location:** `src/agents/core/rate_limiter.py`, line 26

**Current Problem:**
```python
self.tokens: float = self.capacity  # START FULL: No artificial waiting  # Cold-start: only 1 token available
```
Two inline comments that directly contradict each other — the second is a leftover from an older version where the bucket started with 1 token.

**Solution — Replace line 26:**
```python
self.tokens: float = self.capacity  # Start full — no cold-start wait on first requests
```

**Risk:** Very Low. Comment-only change.  
**Behavior Change:** None.

---

### R-10: Add `timeout` Parameter to `rate_limiter.acquire()`

**Type:** Feature — Safety  
**Location:** `src/agents/core/rate_limiter.py`, lines 41–74

**Current Problem:**
```python
async def acquire(self, tokens: int = 1) -> None:
    while True:   # ← infinite loop — no escape if penalty is 3600 seconds
        ...
        await asyncio.sleep(wait_time)
```
If `apply_penalty(3600)` is called, every `acquire()` call blocks silently forever. A hung pipeline produces no errors — it just stalls.

**Solution — Add `timeout` parameter (backward-compatible default `None`):**

```python
async def acquire(self, tokens: int = 1, *, timeout: float | None = None) -> None:
    """Acquire tokens from the bucket, blocking until they are available.

    Args:
        tokens: Number of tokens to acquire (must be <= capacity).
        timeout: Maximum seconds to wait. Raises ``asyncio.TimeoutError``
                 if the deadline is exceeded. ``None`` means wait forever
                 (original behaviour).

    Raises:
        ValueError: If ``tokens`` exceeds capacity.
        asyncio.TimeoutError: If ``timeout`` is set and the wait exceeds it.
    """
    if tokens > self.capacity:
        raise ValueError(f"Cannot acquire {tokens} tokens.")

    deadline: float | None = (time.monotonic() + timeout) if timeout is not None else None

    while True:
        async with self._lock:
            now = time.monotonic()

            if deadline is not None and now >= deadline:
                raise asyncio.TimeoutError(
                    f"rate_limiter.acquire() timed out after {timeout}s"
                )

            if now < self.pause_until:
                wait_time = self.pause_until - now
            else:
                elapsed_since_update = now - self.last_update
                self.tokens = min(
                    self.capacity,
                    self.tokens + elapsed_since_update * self.fill_rate,
                )
                self.last_update = now

                time_since_last_grant = now - self.last_grant if self.last_grant > 0 else float("inf")
                interval_ok = time_since_last_grant >= self.min_interval

                if self.tokens >= tokens and interval_ok:
                    self.tokens -= tokens
                    self.last_grant = now
                    return

                token_wait = (tokens - self.tokens) / self.fill_rate if self.tokens < tokens else 0.0
                interval_wait = (self.min_interval - time_since_last_grant) if not interval_ok else 0.0
                wait_time = max(token_wait, interval_wait, 0.01)

                if deadline is not None:
                    wait_time = min(wait_time, deadline - now)

        await asyncio.sleep(wait_time)
```

Also add `asyncio` import check — it's already imported at top of file.

**Risk:** Low. The `timeout=None` default preserves existing behavior. The only caller (`candidate_score.py:362`) calls `await limiter.acquire()` with no arguments — no change needed there.  
**Behavior Change:** Existing code is unchanged. New code can now call `await limiter.acquire(timeout=30.0)` and get a clean `asyncio.TimeoutError` instead of hanging forever.

---

### R-11: Add Observability Properties to `TokenBucketRateLimiter`

**Type:** Feature — Observability  
**Location:** `src/agents/core/rate_limiter.py`, after `apply_penalty` (line 43)

**Current Problem:**
There's no way to inspect rate limiter state externally. A stuck pipeline gives no clues about whether the limiter is waiting for tokens, waiting for interval, or serving a penalty.

**Solution — Add 3 read-only properties:**

```python
@property
def current_tokens(self) -> float:
    """Snapshot of available tokens (not lock-protected — advisory only)."""
    return self.tokens

@property
def is_paused(self) -> bool:
    """True if the circuit breaker is currently active."""
    return time.monotonic() < self.pause_until

@property
def pause_remaining_seconds(self) -> float:
    """Seconds remaining in the current circuit-breaker pause (0.0 if not paused)."""
    remaining = self.pause_until - time.monotonic()
    return max(0.0, remaining)
```

**Risk:** Low. Additive — no existing behavior is touched.  
**Behavior Change:** None. External code can now read `limiter.is_paused` and `limiter.pause_remaining_seconds` for logging/debugging.

---

### R-12: Complete `__init__.py` Public API Exports

**Type:** API Completeness  
**Location:** `src/agents/core/__init__.py`

**Current Problem:**
Three symbols defined in `models.py` are not exported, forcing callers to import directly from `models.py` and breaking the package's encapsulation:
- `TEMPLATE_META_KEYS` — expected meta tags per template
- `TEMPLATE_ROW_MAP` — template name → row class mapping
- `TEMPLATE_CAPACITIES` — template name → capacity config

**Solution:**

**Step 1** — In the `from src.agents.core.models import (...)` block, add:
```python
    TEMPLATE_META_KEYS,
    TEMPLATE_ROW_MAP,
    TEMPLATE_CAPACITIES,
```

**Step 2** — In `__all__`, add after `"TEMPLATE_FALLBACKS"`:
```python
    "TEMPLATE_META_KEYS",
    "TEMPLATE_ROW_MAP",
    "TEMPLATE_CAPACITIES",
```

**Step 3** — If R-04 is done (teardown_job_logger added), also add to imports and `__all__`:
```python
from src.agents.core.logger import log_api_call, setup_job_logger, timed_operation, teardown_job_logger
```
And `"teardown_job_logger"` in `__all__`.

**Risk:** Low. Additive — new exports do not break existing imports.  
**Behavior Change:** None.

---

### R-13: Add URL Validation to `SourceAudit.url`

**Type:** Validation  
**Location:** `src/agents/core/models.py`, `SourceAudit` class (after line 71)

**Current Problem:**
```python
url: str = Field(..., description="Exact URL the data was fetched from.")
```
Any string is accepted — empty strings, relative paths, or `"N/A"` strings stored silently in the audit trail.

**Solution — Add a field validator:**

```python
from urllib.parse import urlparse   # add to imports at top

class SourceAudit(BaseModel):
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
```

**Risk:** Low-Medium. If any existing code in the pipeline creates `SourceAudit(url="")` or `SourceAudit(url="N/A")`, those will now raise `ValidationError`. Grep for `SourceAudit(` before applying:  
```powershell
Select-String -Recurse -Pattern "SourceAudit\(" src/
```
Verify all call sites pass valid URLs before merging.  
**Behavior Change:** `SourceAudit` with invalid URLs now fails fast at construction instead of storing garbage.

---

## 🟢 Low Priority

---

### R-14: Move `write_data_manifest` Out of `JobManager` (SRP Fix)

**Type:** SRP — Structural Move  
**Location:** `src/agents/core/job_manager.py` (lines 242–259) → `src/agents/phase1_extraction/runner.py`

**Current Problem:**
`JobManager` is job lifecycle infrastructure. Writing `data_manifest.json` is extraction-phase domain logic. This method in `JobManager` means the extraction schema leaks into shared infrastructure.

**Callers:**
- `src/agents/phase1_extraction/runner.py:336` — the only caller (`job_manager.write_data_manifest(manifest)`)

**Solution:**

**Step 1** — In `src/agents/phase1_extraction/runner.py`, add a local helper function. Find the section around line 330 (just before the `job_manager.write_data_manifest(manifest)` call) and add:

```python
def _write_data_manifest(job_manager: "JobManager", manifest_data: dict) -> None:
    """Write extraction data manifest atomically. Extraction-phase concern only."""
    import os, tempfile, json
    data_dir = job_manager.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = data_dir / "data_manifest.json"

    fd, tmp_path = tempfile.mkstemp(dir=str(data_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        os.replace(tmp_path, str(manifest_path))
        job_manager.get_logger().info("Generated stable data_manifest.json contract.")
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

**Step 2** — Replace line 336 in `runner.py`:
```python
# Before
job_manager.write_data_manifest(manifest)

# After
_write_data_manifest(job_manager, manifest)
```

**Step 3** — Delete the `write_data_manifest` method from `job_manager.py` (lines 242–259).

**Step 4** — Run:
```powershell
Select-String -Recurse -Pattern "write_data_manifest" src/
```
Confirm zero remaining references.

**Risk:** Medium. Requires updating one caller and deleting a method. If any other caller exists that wasn't found, it will fail at runtime. Run the grep above before merging.  
**Behavior Change:** None — same logic, same atomic write, just moved to the right file.

---

### R-15: Replace `settings` Singleton with `get_settings()` Factory

**Type:** Architecture — Testability  
**Location:** `src/agents/core/config.py` (line 72) + 10 consumer files

**Current Problem:**
```python
settings = SystemSettings()   # module-level singleton
```
Any test that imports a module importing `config.py` fails without real API keys. 10 consumer files import `settings` directly.

**Consumer files impacted:**
```
src/cli/phase1.py
src/cli/autoshorts.py
src/agents/phase1_extraction/api_clients.py
src/agents/phase1_extraction/runner.py
src/agents/phase2_scripting/runner.py
src/agents/phase3_audio/tts_client.py
src/agents/phase2_scripting/timing.py
src/agents/phase2_scripting/llm_writer.py
src/agents/phase1_discovery/candidate_score.py
src/agents/phase1_discovery/discovery_runner.py
src/agents/phase1_discovery/scourer.py
```

**Solution:**

**Step 1** — In `src/agents/core/config.py`, replace line 72:
```python
# Before
settings = SystemSettings()

# After
from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> SystemSettings:
    """Return the global settings singleton (created on first call).

    Use ``get_settings.cache_clear()`` in tests to reset between runs.
    Patch with ``monkeypatch.setattr('src.agents.core.config.get_settings', ...)``
    for unit tests that don't have real API keys.
    """
    return SystemSettings()

# Backward-compatibility alias — existing ``from config import settings`` still works.
# Deprecated: prefer ``get_settings()`` in new code.
settings: SystemSettings = get_settings()
```

> **NOTE:** The backward-compatibility alias `settings = get_settings()` means all 10 consumer files continue to work **without any changes**. This makes R-15 the safest possible migration — no callers break.

**Step 2 (Optional — gradual migration):** Update consumer files one at a time to call `get_settings()` instead of using the `settings` module attribute. This enables `monkeypatch`-based testing. Each file is an independent commit.

**Risk:** High (wide surface area) → reduced to Low by the backward-compatibility alias. The alias ensures zero breaking changes at migration time.  
**Behavior Change:** None for production. Tests can now mock `get_settings` without real API keys.

---

## 📋 Execution Order

Do refactors **in this order** to minimize risk. Each one should be a separate commit.

```
Group 1 — Zero-risk cleanup (no logic, no API)
  1. R-09  — Fix contradictory comment in rate_limiter.py
  2. R-08  — Remove dead logger + dev comment from job_manager.py
  3. R-07  — Extract standard_keys to module-level constant

Group 2 — Isolated bug fixes (behavior improves, no API change)
  4. R-01  — Fix TopicCandidate validator bypass (1-line change)
  5. R-02  — Fix legacy scoring weights (3-dict change)
  6. R-03  — Wrap cost_tracker in try/except + timestamp + default=str
  7. R-05  — Fix log_api_call 5xx severity
  8. R-06  — Fix timed_operation BaseException guard

Group 3 — Additive changes (new functions/params, backward compatible)
  9. R-04  — Add threading.Lock + teardown_job_logger to logger.py
  10. R-10 — Add timeout param to acquire()
  11. R-11 — Add observability properties to rate_limiter
  12. R-12 — Fix __init__.py missing exports (include teardown_job_logger)
  13. R-13 — Add URL validation to SourceAudit (verify callers first)

Group 4 — Structural moves (require caller updates, do last)
  14. R-14 — Move write_data_manifest to phase1_extraction/runner.py
  15. R-15 — Replace settings singleton with get_settings() factory
```

**Logic behind the order:**
- Group 1 first: zero risk, builds confidence, cleans noise before real changes
- Group 2 before Group 3: fix bugs in stable code before adding new code on top
- R-04 (threading.Lock) after R-07 (standard_keys): logger internals stabilized first, then synchronization changed
- R-12 after R-04: export `teardown_job_logger` only after it exists
- R-13 late: URL validation could reject existing data — confirm callers are clean first
- R-14 before R-15: remove SRP violation while API surface is still the same
- R-15 last: widest surface area, but lowest actual risk due to backward-compat alias

---

## 🛡️ Risk Assessment

| Change | Risk | What Can Break | Mitigation |
|--------|------|----------------|------------|
| R-01 | Low | Code passing `best_fit_template=""` | Grep for `best_fit_template=""` before applying |
| R-02 | Low | Hardcoded score thresholds in filters | Review any `if final_score > X` logic |
| R-03 | Low | Nothing — only adds protection | Review `record` schemas at call sites |
| R-04 | Medium | Logger output format if Lock adds overhead | Test with `threading.Thread` x 10 same job_id |
| R-05 | Low | Alert rules watching log levels | Intentional improvement |
| R-06 | Low | Nothing | — |
| R-07 | Low | Nothing | — |
| R-08 | Very Low | Nothing | — |
| R-09 | Very Low | Nothing | — |
| R-10 | Low | Nothing (default=None) | Verify `candidate_score.py:362` still works |
| R-11 | Low | Nothing (additive) | — |
| R-12 | Low | Nothing (additive) | — |
| R-13 | Low-Med | Call sites passing invalid URLs | Grep `SourceAudit(` before applying |
| R-14 | Medium | `runner.py:336` call + any hidden callers | `Select-String write_data_manifest src/` |
| R-15 | High → Low | All 10 consumer files | Backward-compat alias makes it zero-breaking |

**Overall Risk:** Medium (individual changes are Low; R-14 and R-15 need care)  
**Recommendation:** Feature branch per group. Merge Group 1+2 first, validate, then Group 3, then Group 4.

---

## 🚧 Scope — What Will NOT Change

- **Business logic** — scoring algorithms (only fixing math bugs), extraction flow, discovery flow
- **Public method signatures** — `JobManager`, `setup_job_logger`, `timed_operation`, `record_cost` all keep the same call signatures
- **`job.json` schema** — the renderer contract is untouched
- **`VALID_TEMPLATES` contents** — no template names are added or removed
- **`AuditTrail` and `TemplateDataset` schemas** — Pydantic model fields are unchanged (only validators added/fixed)
- **Files outside `src/agents/core/`** — only `phase1_extraction/runner.py` is touched (R-14), and only the `write_data_manifest` call site

---

## ✅ Verify

Run these after each group to confirm nothing regressed:

**After Group 1 (cleanup):**
```powershell
python -m py_compile src/agents/core/rate_limiter.py
python -m py_compile src/agents/core/job_manager.py
python -m py_compile src/agents/core/logger.py
```
Expected: No output (no syntax errors).

**After Group 2 (bug fixes):**
```powershell
python -m pytest tests/phase1 -v
python -m py_compile src/agents/core/models.py
```
Expected: All tests pass; no compile errors.

**After R-01 specifically — verify the flaw is gone:**
```powershell
python -c "
from src.agents.core.models import TopicCandidate
try:
    c = TopicCandidate(topic='T', normalized_topic='t', best_fit_template='')
    print('FAIL: empty string still allowed')
except Exception as e:
    print(f'PASS: ValidationError raised — {e}')
"
```
Expected: `PASS: ValidationError raised`

**After R-02 specifically — verify legacy scoring ceiling:**
```powershell
python -c "
from src.agents.core.models import TopicCandidate
c = TopicCandidate(
    topic='T', normalized_topic='t', best_fit_template='bar_chart',
    virality_score=10, data_feasibility_score=10, template_fit_score=10,
    visual_potential_score=10, source_quality_score=10, fallback_strength_score=10,
)
assert c.final_score == 10.0, f'Expected 10.0, got {c.final_score}'
print(f'PASS: legacy final_score = {c.final_score}')
"
```
Expected: `PASS: legacy final_score = 10.0`

**After R-04 (threading fix):**
```powershell
python -c "
import threading, tempfile
from pathlib import Path
from src.agents.core.logger import setup_job_logger

results = []
def setup(): results.append(setup_job_logger(Path(tempfile.gettempdir()), 'test_race'))
threads = [threading.Thread(target=setup) for _ in range(10)]
[t.start() for t in threads]; [t.join() for t in threads]
log = results[0]
handler_count = len(log.handlers)
print(f'PASS' if handler_count == 2 else f'FAIL: {handler_count} handlers (expected 2)')
"
```
Expected: `PASS`

**After R-14 (write_data_manifest moved):**
```powershell
Select-String -Recurse -Pattern "write_data_manifest" src/
```
Expected: Zero matches (method and all call sites gone).

**After R-15 (settings factory):**
```powershell
python -c "from src.agents.core.config import settings, get_settings; assert settings is get_settings(); print('PASS')"
```
Expected: `PASS`

**Full pipeline smoke test (after all groups):**
```powershell
python -m pytest tests/ -v --tb=short
```
Expected: All existing tests pass.
