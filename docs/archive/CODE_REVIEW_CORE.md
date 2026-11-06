# Code Review — `src/agents/core/` — Expert Level

**Reviewed on:** 2026-05-22  
**Level:** 🔴 Expert (Production-grade audit)  
**Files Reviewed:** 7 (`config.py`, `cost_tracker.py`, `rate_limiter.py`, `logger.py`, `job_manager.py`, `models.py`, `__init__.py`)

---

## 📄 `config.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 25%  
**Verdict:** Secure and fail-fast by design, but the module-level singleton blocks testability and has no startup observability.

### ✅ What's Good
- `SecretStr` for API keys ensures they are redacted in logs and `repr()` output — correct security practice.
- `extra="ignore"` prevents accidental env var leakage into the settings object.
- Fail-fast on missing keys at import time is exactly right for a pipeline that can't run without them.
- Conditional `.env` loading (`if ENV_FILE.exists() else None`) avoids silent failures in containerized environments.

### ⚠️ Issues Found

🔴 **High Priority**
- **Module-level singleton kills unit testability.** `settings = SystemSettings()` at module level means any module that imports `config.py` (directly or transitively) will raise `ValidationError` in CI/CD environments and unit tests without real API keys. There is no way to inject a test configuration. Fix: use `functools.lru_cache` on a `get_settings()` factory function, and patch it in tests with `monkeypatch.setattr`. The singleton pattern is justified for production but blocks isolated testing of any consumer module.

🟡 **Medium Priority**
- **`primary_authority_domains` and `social_authority_domains` have no `validation_alias`.** These fields cannot be configured from environment variables — only from the hardcoded defaults. If a deployment needs to add a new authoritative domain without redeploying, there's no mechanism. Add `validation_alias` (e.g., `"PRIMARY_AUTHORITY_DOMAINS"`) with JSON string parsing via `json_schema_extra` or a custom validator.
- **No startup log.** There is no log statement confirming which `.env` file was loaded or which model/settings are active. In production, a startup summary to stderr (e.g., `gemini_model=..., rpm_limit=..., env_file=...`) aids debugging misconfigured deployments without exposing secret values.

🟢 **Low Priority**
- `api_timeout_seconds` is a single value — no distinction between connection timeout and read timeout. For API calls to Gemini (which can take 30–90s to stream), a single timeout can cause incorrect behavior. Consider `connect_timeout_seconds` and `read_timeout_seconds` separately.

---

## 📄 `cost_tracker.py` — Expert Review

**Code Quality:** 4/10  
**Improvement Chance:** 60%  
**Verdict:** Too fragile for its role. A cost-tracking failure silently crashes pipeline operations it should be invisible to.

### ✅ What's Good
- Append-only JSONL format is correct — no data loss risk from partial reads.
- `ensure_ascii=False` handles unicode characters in cost records correctly.

### ⚠️ Issues Found

🔴 **High Priority**
- **Zero error handling — cost-tracking failure crashes the pipeline.** `record_cost()` has no try/except. If `logs_dir.mkdir()` fails (disk full, permissions), or if `open()` fails, or if `json.dumps(record)` throws `TypeError` (unserializable value in `record`), the exception propagates raw to the caller. Cost tracking is a non-critical observability concern — it must never bring down the pipeline. Fix: wrap the entire body in `try/except Exception as e: logger.warning("Cost record failed: %s", e)`.
- **No type validation on `record`.** Any dict is accepted. An unserializable value (e.g., a `Path` object, a `datetime` without `default=str`) causes a `TypeError` with a stack trace pointing to `json.dumps`, not the caller. Add `default=str` to `json.dumps` as a minimum, or validate expected fields.

🟡 **Medium Priority**
- **No timestamp added by `record_cost` itself.** Every caller must manually include a `"recorded_at"` field — if any caller forgets, the JSONL file has unordered, undated records. The function should inject `"recorded_at": datetime.now(timezone.utc).isoformat()` automatically.
- **No atomic write.** Concurrent calls from multiple asyncio tasks writing to the same job's `cost.jsonl` can interleave lines (partial `\n` writes). Use `fcntl.flock` (Unix) or a file-level lock, or append via a queue. At minimum, the JSONL line should be written as a single `write()` call with `\n` already appended, which is already done — but `f.write(line)` isn't guaranteed atomic at the OS level across multiple processes.

🟢 **Low Priority**
- The function has no docstring. The module docstring says "Record cost/usage info" but the expected `record` schema (required vs. optional keys) is undocumented.

---

## 📄 `rate_limiter.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 30%  
**Verdict:** Solid token-bucket algorithm and circuit breaker, but missing production essentials: timeout support in `acquire()`, no observability, and a contradictory comment that survived from an earlier version.

### ✅ What's Good
- Correct async lock acquisition — all state mutation happens inside `async with self._lock`.
- Sleep happens **outside** the lock, allowing other coroutines to proceed.
- Circuit breaker correctly uses `max()` semantics (`if penalty_end > self.pause_until`) to extend the penalty window.
- Both token availability AND inter-request spacing are enforced — prevents burst exploitation.
- `__slots__` reduces memory overhead when many rate limiter instances are created.

### ⚠️ Issues Found

🔴 **High Priority**
- **`acquire()` can hang indefinitely.** If `apply_penalty(seconds=3600)` is called (or called multiple times), every `acquire()` call will loop forever with no timeout or cancellation escape hatch. A caller with `asyncio.wait_for(..., timeout=X)` will get `asyncio.TimeoutError`, which is correct — but the rate limiter itself has no `timeout` parameter on `acquire()`. In a production pipeline where a 429 penalty is applied, all downstream tasks will block silently. Fix: add `timeout: float | None = None` to `acquire()`, track elapsed time, and raise `asyncio.TimeoutError` if exceeded.

🟡 **Medium Priority**
- **Contradictory inline comment on line 26.** The line reads:  
  `self.tokens: float = self.capacity  # START FULL: No artificial waiting  # Cold-start: only 1 token available`  
  The second inline comment says "only 1 token available" which is the **opposite** of what the code does (starts full). This is a leftover from a previous iteration and will mislead future readers. Remove the second comment entirely.
- **No penalty escalation / backoff.** `apply_penalty(seconds=60.0)` always applies a flat 60-second pause. In production, successive 429 responses should trigger exponential backoff (60s → 120s → 240s). The rate limiter has no memory of how many penalties have been applied. Consider adding a `penalty_count: int` field and computing `min(60 * 2**self.penalty_count, 3600)`.
- **No observability.** There's no way for external code to inspect current token count, pause status, or cumulative wait time. In production, you'd want `@property` methods for `current_tokens`, `is_paused`, `pause_remaining_seconds` to feed metrics dashboards.

🟢 **Low Priority**
- `pause_until` is accessible directly (it's in `__slots__` without name mangling). It should be `_pause_until` to signal it's internal state. External callers reading it without the lock would see a race-condition-prone snapshot.
- The `__main__` test block uses `print()` instead of the project logger. Fine for manual testing, but the test block would be cleaner extracted into a `tests/` file.

---

## 📄 `logger.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 40%  
**Verdict:** Well-designed dual-output system with good patterns, but a module-level memory/FD leak and a thread-safety gap in the registry are production blockers.

### ✅ What's Good
- Idempotency guard (`_INITIALISED_LOGGERS`) prevents duplicate handlers on repeated setup calls — correctly solves the classic Python logging double-output bug.
- `timed_operation` catches `BaseException` and re-raises — correctly surfaces `KeyboardInterrupt` and `SystemExit` while still logging.
- UTC timestamps throughout — no timezone ambiguity.
- `log.propagate = False` prevents the root logger from duplicating output.
- `_JSONLineFormatter` dynamically captures custom `extra` keys without requiring a hardcoded whitelist — this is the right design.

### ⚠️ Issues Found

🔴 **High Priority**
- **File descriptor leak in `_INITIALISED_LOGGERS`.** Loggers are stored in a module-level dict but never removed and their `FileHandler`s are never closed. In a long-running process that creates many jobs (e.g., a discovery run over 100 topics), this accumulates open file handles until the OS limit is hit (`Too many open files`). Fix: add a `teardown_job_logger(job_id)` function that calls `handler.close()`, `logger.removeHandler(handler)`, and `del _INITIALISED_LOGGERS[job_id]`.
- **Thread-safety gap in the registry (TOCTOU race).** The check-then-set pattern on lines 140–164:
  ```python
  if job_id in _INITIALISED_LOGGERS:   # check
      return _INITIALISED_LOGGERS[job_id]
  ...
  _INITIALISED_LOGGERS[job_id] = log   # set
  ```
  is not protected by a lock. If two threads simultaneously call `setup_job_logger` with the same `job_id`, both pass the `if` check, both create and attach handlers, resulting in duplicate handlers (double output on every log line). Fix: protect with a `threading.Lock()` around the check-and-set block.

🟡 **Medium Priority**
- **`standard_keys` set is recomputed on every `format()` call.** The set of 21 standard logging attributes is rebuilt as a Python set literal on every single log record. For high-throughput logging, this is unnecessary allocation. Move it to a module-level constant:  
  `_STANDARD_LOG_KEYS: frozenset[str] = frozenset({...})`.
- **`log_api_call` conflates WARNING and ERROR.** Any `status_code >= 400` is logged as `WARNING`. But `5xx` server errors should be `ERROR` — they indicate the external service is down, not just a client mistake. Fix: `logging.ERROR if status_code >= 500 else logging.WARNING`.
- **`timed_operation` catches `BaseException` including `SystemExit`.** Logging a `SystemExit` as `✖ FAILED` is misleading — it's a controlled shutdown, not a failure. Add `if not isinstance(exc, (SystemExit, KeyboardInterrupt)):` before the error log, then always re-raise.

🟢 **Low Priority**
- `setup_job_logger`'s type hint says `job_dir: Path` but line 143 re-wraps with `Path(job_dir)`. Either accept `Path | str` in the signature (and note the conversion), or trust the type hint and remove the redundant wrap.
- `log.info("Logger initialised — log file: %s", log_file)` on line 165 fires on every first setup. If the logger is created inside `get_logger()` before `initialize()` runs (e.g., via `get_logger()` being called early), the log file path may not yet exist in the directory. This is cosmetically confusing in logs.

---

## 📄 `job_manager.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 30%  
**Verdict:** Excellent atomic write pattern and resilient state reading, but a TOCTOU race on concurrent step marking, a SRP violation (`write_data_manifest`), and a leaked development comment lower the production readiness.

### ✅ What's Good
- `_write_state` uses `tempfile.mkstemp` → `os.replace` — this is the correct crash-safe pattern.
- `_read_state` truly never raises — returns `None` on FileNotFoundError, JSONDecodeError, and OSError.
- UUID fragment in `_generate_job_id` prevents ID collisions even at the same millisecond.
- `get_attempt_dir` sanitizes `template_name` with `re.sub(r"[^a-zA-Z0-9_-]", "_", ...)` before using it in a path — correct path traversal prevention.
- Properties expose only computed paths, not mutable internals.
- Docstrings are thorough and reference the broader architecture correctly.

### ⚠️ Issues Found

🔴 **High Priority**
- **TOCTOU race condition on concurrent step marking.** `mark_step_completed` does: `state = self._read_state()` → mutate → `_write_state(state)` — without any file lock. If two processes (e.g., Phase 2 and Phase 3 running in parallel for different segments of the same job) call `mark_step_completed` simultaneously, both read the old state, both write their own step, and the last writer overwrites the first writer's step entry. The atomic write protects against **corruption**, but not against **lost updates**. Fix: use `fcntl.flock` (POSIX) or a `.pipeline_lock` file with `msvcrt.locking` (Windows) around the read-mutate-write cycle, or restructure to use a single-writer process model.

🟡 **Medium Priority**
- **`write_data_manifest` violates Single Responsibility Principle.** `JobManager`'s responsibility is job lifecycle and state tracking. Writing domain-specific artifacts (like `data_manifest.json`) is the responsibility of the extraction phase. This method bleeds Phase 1 extraction concerns into shared infrastructure. Move it to `phase1_extraction/runner.py` which already knows the manifest schema.
- **Module-level `logger = logging.getLogger(__name__)` on line 41 is dead code.** It is defined but never used — all logging goes through `self.get_logger()`. Either use it (for module-level warnings during import) or remove it to avoid confusion.
- **Development comment `# ADD THIS LINE` on line 270 must be removed before production.** It is a commit artifact that signals the code was added as a hotfix without cleanup. In a codebase with `git blame`, this is confusing.

🟢 **Low Priority**
- `_generate_job_id` truncates the microsecond timestamp with `[:19]` — the `%f` format produces 6 digits but only 3 are kept. The comment says "UTC timestamp + random fragment" but doesn't explain the truncation. Document the choice: `# Trim microseconds to 3 digits; UUID fragment handles uniqueness`.
- `set_template` writes `state["template"] = template_name` without schema validation. If `_read_state()` returns a malformed dict (e.g., missing the `"steps"` key), `state.setdefault("steps", {})` isn't called here (unlike in `mark_step_completed`). Add the same defensive pattern.
- `__repr__` uses `!r` for `template_name` and `job_id` but not for `job_dir`. Inconsistent: `f"dir={self._job_dir}"` should be `f"dir={self._job_dir!r}"` for safe repr output.

---

## 📄 `models.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 45%  
**Verdict:** Rich, well-structured Pydantic models with good invariants, but a known unfixed validator bypass, a scoring math bug, and unsafe mutation patterns in Pydantic v2 make this not yet production-ready.

### ✅ What's Good
- `VALID_TEMPLATES` as a `frozenset` is fast (`O(1)` lookup) and immutable — correct.
- `TemplateCapacity` enforces `ideal <= max` via `model_validator` — prevents silent misconfiguration.
- `AuditTrail.save_to_file` uses the same atomic write pattern as `JobManager` — consistent safety.
- `AuthorityTier` enum prevents magic strings for credibility tiers.
- `TEMPLATE_ROW_MAP` and `TEMPLATE_CAPACITIES` are consistent with `VALID_TEMPLATES` — no orphaned entries.
- `TemplateDataset._validate_rows` enforces both row-type correctness and capacity in one place.

### ⚠️ Issues Found

🔴 **High Priority**
- **Known validator bypass — empty string passes `best_fit_template` in `TopicCandidate`.** The validator at line 500 reads `if v and v not in VALID_TEMPLATES:` — the `if v` guard silently allows an empty string `""` through. The `__main__` test block (line 626) explicitly demonstrates this flaw and labels it "FLAW EXPOSED". This bug is documented but unfixed. A `TopicCandidate` with `best_fit_template=""` will crash Phase 1 extraction with a confusing KeyError rather than a clear validation error. Fix: change to `if v not in VALID_TEMPLATES:` (remove the `if v` guard), matching the stricter check in `QueuedTopic`.
- **Legacy scoring weights do not sum to 1.0 — producing systematically low scores.** In `compute_final_score`, the legacy branch uses:  
  `virality(0.25) + data_feasibility(0.20) + template_fit(0.20) + visual_potential(0.15) + source_quality(0.10) + fallback_strength(0.05) = 0.95`  
  A candidate with perfect scores of 10.0 across all dimensions would produce `final_score = 9.5`, not `10.0`. The `final_score` field has `le=10` but the actual ceiling is 9.5. Legacy queue topics are systematically scored lower than fresh ideation-first candidates by 5%, causing unfair ranking when both are in the same discovery batch.
- **`compute_final_score` mutates a Pydantic v2 model in place without `validate_assignment`.** Lines 525 and 534 do `self.final_score = ...` and `self.score_breakdown = ...` directly on a Pydantic `BaseModel`. In Pydantic v2, assignment on model instances bypasses field validators unless `model_config = ConfigDict(validate_assignment=True)` is set. If a validator is ever added to `final_score` (e.g., `ge=0, le=10`), the in-place mutation will silently skip it. Fix: set `model_config = ConfigDict(validate_assignment=True)` on `TopicCandidate`, or make `compute_final_score` a pure function returning `(score, breakdown)` and have the `model_validator` set both fields from its return value.

🟡 **Medium Priority**
- **`AuditTrail.save_to_file` has redundant and misleading datetime re-serialization.** Line 128 calls `self.model_dump(mode="json")` — Pydantic's `mode="json"` already converts `datetime` fields to ISO-8601 strings. Lines 130–133 then check `isinstance(src.get("scraped_at"), datetime)` on what are already strings, so the `isinstance` check always evaluates to `False` and the conversion never fires. The code works by accident. Remove lines 130–133 entirely — `model_dump(mode="json")` handles it correctly.
- **`SourceAudit.url` has no URL validation.** Any string is accepted, including empty strings, relative paths, or malformed URLs. At minimum, add a `field_validator` that checks the URL starts with `http://` or `https://` and is parseable by `urllib.parse.urlparse`. This prevents garbage data from being stored in the audit trail.

🟢 **Low Priority**
- `SCORING_WEIGHTS` mixes new and legacy weights in the same dict. A reader has to understand both systems to read this dict. Split into `_NEW_SCORING_WEIGHTS` and `_LEGACY_SCORING_WEIGHTS` for clarity, and use them explicitly in `compute_final_score`.
- The `DataSchemaSpec.format: Literal["csv"] = "csv"` field is hardcoded — it signals future extensibility but serves no purpose today. Either document why it exists or remove it until other formats are needed.
- `AuditTrail._validate_template` rejects `"auto"` as a template name. But audit trails could be created during auto-discovery mode before a template is chosen. Consider making `template_name` optional or allowing `"auto"` as a valid value.

---

## 📄 `__init__.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 20%  
**Verdict:** Clean re-export pattern with a complete `__all__`, but three useful symbols from `models.py` are missing from the public API.

### ✅ What's Good
- `__all__` is explicitly defined — prevents accidental star-import pollution.
- Imports are organized by category (Job Manager, Logger, Models) with inline comments.
- Re-exporting constants (`VALID_TEMPLATES`, `TEMPLATE_FALLBACKS`, `SCORING_WEIGHTS`) at the package level avoids callers needing to know the internal module structure.

### ⚠️ Issues Found

🟡 **Medium Priority**
- **`TEMPLATE_META_KEYS` is defined in `models.py` but not exported.** `from src.agents.core import TEMPLATE_META_KEYS` will raise `ImportError`. Other modules that need to look up expected meta keys must import directly from `models.py`, breaking the package's public API contract. Add it to both the import and `__all__`.
- **`TEMPLATE_ROW_MAP` and `TEMPLATE_CAPACITIES` are not exported.** These are needed by any code that dynamically dispatches by template name (e.g., validation in the extraction runner). Their absence forces callers to reach into `models.py` directly, bypassing the package's intended encapsulation layer.

🟢 **Low Priority**
- `config.py` (`settings`, `SystemSettings`) is not re-exported. Consumers must do `from src.agents.core.config import settings` rather than `from src.agents.core import settings`. This is a deliberate design choice (keeping config separate) but should be documented in the module docstring.

---

## 📊 Overall Project Report — Expert Review

**Files Reviewed:** 7  
**Overall Quality Score:** 6/10  
**Overall Improvement Chance:** 38%  
**Verdict:** ❌ Not yet production-ready. The core infrastructure has excellent patterns (atomic writes, token bucket, dual logging) but several issues would cause silent data loss or hard-to-debug failures under concurrent load.

### Score Breakdown

| File | Score | Production Ready? |
|------|-------|-------------------|
| `config.py` | 7/10 | ⚠️ With caveats |
| `cost_tracker.py` | 4/10 | ❌ |
| `rate_limiter.py` | 7/10 | ⚠️ With caveats |
| `logger.py` | 6/10 | ❌ |
| `job_manager.py` | 7/10 | ⚠️ With caveats |
| `models.py` | 6/10 | ❌ |
| `__init__.py` | 7/10 | ⚠️ With caveats |

### Common Issues (Across the Codebase)
- **Atomic writes are used correctly everywhere** (job_manager, models, cost_tracker for its temp pattern) but **locking is absent everywhere** — concurrent processes on the same job directory can produce lost updates.
- **Development artifacts** (`# ADD THIS LINE`, `__main__` test blocks that document unfixed flaws) indicate the codebase is in active development and hasn't been hardened for a production freeze.
- **No teardown/cleanup hooks** — file handles (logger), rate limiters, and temp state are never explicitly cleaned up.

---

### 🔴 Critical Fixes (Do First)

1. **`models.py` line 500** — Remove `if v` guard from `TopicCandidate._validate_best_fit`. An empty `best_fit_template` will crash Phase 1 extraction with a confusing error, not a validation error.
2. **`cost_tracker.py` lines 7–13** — Wrap `record_cost` body in `try/except Exception`. Cost tracking must never crash the pipeline.
3. **`logger.py` lines 140–164** — Add `threading.Lock()` around the registry check-and-set. Duplicate handlers cause double log output, which breaks JSONL parsing.
4. **`logger.py` — Add `teardown_job_logger(job_id)`** — Close file handlers and remove from registry to prevent FD exhaustion in long-running discovery sessions.
5. **`models.py` legacy scoring** — Fix weights to sum to 1.0 (`fallback_strength: 0.05 → 0.10`, removing the gap). Legacy queue topics are silently undercounted.

---

### 🟡 Important Improvements

1. **`job_manager.py` `write_data_manifest`** — Move to `phase1_extraction/runner.py`. Extraction concerns don't belong in job lifecycle infrastructure.
2. **`rate_limiter.py` `acquire()`** — Add a `timeout: float | None = None` parameter. Without it, a runaway penalty call can stall the entire async pipeline indefinitely.
3. **`config.py`** — Replace module-level `settings = SystemSettings()` with a `@lru_cache` `get_settings()` function for testability via `monkeypatch`.
4. **`job_manager.py` line 270** — Remove the `# ADD THIS LINE` development comment.
5. **`job_manager.py` line 41** — Remove the unused module-level `logger = logging.getLogger(__name__)`.

---

### 🟢 Nice to Have

1. **`rate_limiter.py`** — Add `current_tokens`, `is_paused`, `pause_remaining_seconds` properties for metrics/observability.
2. **`logger.py` `standard_keys`** — Extract to a module-level `frozenset` constant to avoid re-allocating on every log record.
3. **`__init__.py`** — Export `TEMPLATE_META_KEYS`, `TEMPLATE_ROW_MAP`, `TEMPLATE_CAPACITIES` to complete the public API.
4. **`models.py` `SourceAudit.url`** — Add URL format validation (`startswith("http")` at minimum).
5. **`config.py`** — Add a startup info log listing active model, RPM limit, and which `.env` file was loaded (without exposing secret values).
