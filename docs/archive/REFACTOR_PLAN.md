# Refactor Plan — `src/agents/phase3_audio/`

**Target:** `src/agents/phase3_audio/` (8 files)  
**Source:** `CODE_REVIEW.md` — Expert-level review  
**Total Changes:** 11  
**Estimated Risk:** Medium (3 structural, 8 isolated)  
**Estimated Time:** 2–3 hours

---

## Refactor Summary

The Phase 3 audio engine has three categories of debt:

1. **Architectural violations** — production code imports a test file; audio writes are not atomic; concurrency errors are silently leaking API calls.
2. **Correctness gaps** — HTTP 5xx is never retried; API key is stale after import; double ffmpeg decode per segment.
3. **Polish** — dev-artifact comments, eager f-string logging, legacy typing, relative test path.

The plan fixes them in an order that minimizes risk: isolated/independent changes first, structural changes in the middle, and runner cleanup last.

---

## 🔴 High Priority (Do First)

### REFACTOR-01: Relocate `_fake_tts` out of test file
**Type:** Module Split  
**Location:** `tests_offline.py` (entire file) → new `_offline_tts.py` + `runner.py:36`

**Current Problem:**  
`runner.py` line 36 imports `_fake_tts` directly from `tests_offline.py`:
```python
from src.agents.phase3_audio.tests_offline import _fake_tts
```
`tests_offline.py` has `logging.basicConfig(level=logging.INFO)` at module level. Every import of `runner.py` (in production, in tests) silently reconfigures the root logger.

**Solution:**
1. Create `src/agents/phase3_audio/_offline_tts.py` — move `_fake_tts` function body here.
2. In `runner.py` line 36 — change import to `from src.agents.phase3_audio._offline_tts import _fake_tts`.
3. In `tests_offline.py` — replace the `_fake_tts` definition with `from src.agents.phase3_audio._offline_tts import _fake_tts`.
4. In `offline_e2e.py` line 20 — move `logging.basicConfig(...)` inside `if __name__ == "__main__":` block.

**Risk:** Low — pure extraction, zero logic change.  
**Behavior Change:** None.

---

### REFACTOR-02: Make per-segment audio writes atomic
**Type:** Extract Function + Pattern Application  
**Location:** `runner.py:164–165` + `packager.py`

**Current Problem:**  
```python
with open(audio_file_path, "wb") as f:
    f.write(trimmed_bytes)
```
A crash mid-write leaves a truncated `.mp3`. The cache integrity check detects 0-byte files but a truncated non-zero file passes the existence check and crashes Phase 4.

**Solution:**
1. Add `atomic_write_bytes(path: Path, data: bytes) -> None` to `packager.py` — mirrors the existing `atomic_write_json` pattern: `mkstemp → write → fsync → os.replace → unlink on error`.
2. In `runner.py` lines 164–165 — replace the `open().write()` block with `atomic_write_bytes(audio_file_path, trimmed_bytes)`.
3. Add `atomic_write_bytes` to the `packager.py` import in `runner.py`.

**Risk:** Low — adds durability, no interface change.  
**Behavior Change:** None (same file is written, atomically now).

---

### REFACTOR-03: Fix `asyncio.gather` to use `return_exceptions=True`
**Type:** Concurrency Correctness Fix  
**Location:** `runner.py:307` (offline path) and `runner.py:326` (online path)

**Current Problem:**  
```python
results = await asyncio.gather(*tasks)
```
Without `return_exceptions=True`, the first `UnderRunError` or `TTSError` raises immediately but all other running tasks continue to the end — consuming ElevenLabs API quota and writing audio files for a job that will be aborted.

**Solution:**
1. Replace both `asyncio.gather(*tasks)` calls with `asyncio.gather(*tasks, return_exceptions=True)`.
2. After each gather, add:
   ```python
   errors = [r for r in results if isinstance(r, BaseException)]
   if errors:
       raise errors[0]
   ```
3. Since `asyncio.gather` preserves input order, also remove the `(idx, seg)` tuple return pattern from `_process_segment` and the `results.sort(key=lambda x: x[0])` line — they are redundant complexity.

**Risk:** Low-Medium — gather semantics change; test with offline harness after.  
**Behavior Change:** On failure, first exception raised is same type/message. Side effect: sibling tasks no longer continue after first failure (correct behavior).

---

### REFACTOR-04: Fix silent error swallowing in `tts_client.py`
**Type:** Error Handling Fix (two sub-fixes)  
**Location:** `tts_client.py:39` + `tts_client.py:122–124`

**Current Problem A:**  
```python
except Exception:
    _ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")
```
Any config error (missing `.env`, syntax error in `config.py`, missing pydantic package) is silently swallowed. The caller gets an empty API key and a confusing `TTSError("API key missing")` instead of the real error.

**Current Problem B:**  
`_get_standard_retry()` only retries `aiohttp.ClientError` and `asyncio.TimeoutError`. A transient ElevenLabs HTTP 500 or 503 raises `TTSError` and immediately propagates with no retry.

**Solution A:**
1. Change `except Exception:` to `except ImportError:` — only the case where the config module isn't installed should silently fall back to env var.

**Solution B:**
1. Add a 5xx check BEFORE the generic non-2xx handler:
   ```python
   if resp.status >= 500:
       raise aiohttp.ClientResponseError(
           resp.request_info, resp.history, status=resp.status
       )
   ```
   `aiohttp.ClientResponseError` IS caught by `_get_standard_retry()`, so this enables 3-attempt retry for transient server errors.

**Risk:** Low for A, Low for B.  
**Behavior Change:** A — config errors now surface immediately (correct). B — 5xx now retried 3× before failing (correct).

---

## 🟡 Medium Priority

### REFACTOR-05: Move API key resolution into `synthesize()` call scope
**Type:** Deferred Resolution (Testability)  
**Location:** `tts_client.py:32–40` + `synthesize()`

**Current Problem:**  
`_ELEVENLABS_KEY` is resolved at module import time. If a test sets `os.environ["ELEVENLABS_API_KEY"]` after import, the key is stale.

**Solution:**
1. Remove the module-level `try/except` block that sets `_ELEVENLABS_KEY`.
2. Create a `_get_elevenlabs_key() -> str` helper function that does the resolution:
   ```python
   def _get_elevenlabs_key() -> str:
       try:
           from src.agents.core.config import settings
           if hasattr(settings, "elevenlabs_api_key") and settings.elevenlabs_api_key:
               return settings.elevenlabs_api_key.get_secret_value()
       except ImportError:
           pass
       return os.getenv("ELEVENLABS_API_KEY", "")
   ```
3. In `synthesize()`, replace `if not _ELEVENLABS_KEY:` with `key = _get_elevenlabs_key(); if not key:`.
4. Replace `"xi-api-key": _ELEVENLABS_KEY` header with `"xi-api-key": key`.

**Risk:** Low — no API behavior change.  
**Behavior Change:** None in production; tests can now monkeypatch env vars correctly.

---

### REFACTOR-06: Add `duration_both()` to eliminate double ffmpeg decode
**Type:** Extract Helper Function  
**Location:** `duration.py` (new function) + `runner.py:160–161`

**Current Problem:**  
```python
d_ms = duration_ms(trimmed_bytes)    # ffmpeg decode #1
d_sec = duration_sec(trimmed_bytes)  # ffmpeg decode #2
```
For a 10-segment job this is 20 ffmpeg decode passes instead of 10.

**Solution:**
1. Add to `duration.py`:
   ```python
   def duration_both(audio_bytes: bytes, input_format: str = "mp3") -> tuple[int, float]:
       """Decode once and return (duration_ms, duration_sec)."""
       audio = PydubAudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
       ms = int(len(audio))  # pydub len() returns duration in ms
       return ms, round(ms / 1000.0, 3)
   ```
2. In `runner.py` lines 160–161 — replace with:
   ```python
   d_ms, d_sec = duration_both(trimmed_bytes)
   ```
3. Update `runner.py` import line.
4. Also update the cache check in `run_phase3` which calls `duration_ms(file_bytes)` alone — use `duration_both(file_bytes)[0]` for consistency.

**Risk:** Low.  
**Behavior Change:** None — identical calculation, one fewer decode.

---

### REFACTOR-07: Fix `offline_e2e.py` relative path and remove module-level logging
**Type:** Path Anchoring + Logging Guard  
**Location:** `offline_e2e.py:20`, `offline_e2e.py:23`

**Current Problem:**  
`_TEST_JOB_DIR = Path("jobs/test_job")` resolves relative to CWD. If the script is run from an IDE or subdirectory, test artifacts are created in the wrong location.

`logging.basicConfig(level=logging.INFO)` at module level is the root-logger contamination source (the secondary one after `tests_offline.py`).

**Solution:**
1. Replace line 23 with:
   ```python
   _PROJECT_ROOT = Path(__file__).resolve().parents[3]
   _TEST_JOB_DIR = _PROJECT_ROOT / "jobs" / "test_job"
   ```
2. Remove `logging.basicConfig(level=logging.INFO)` from module level.
3. Add it inside the `if __name__ == "__main__":` guard at the bottom.

**Risk:** Very Low.  
**Behavior Change:** Test artifacts always land in `<project_root>/jobs/test_job` regardless of invocation directory.

---

### REFACTOR-08: Clean up `runner.py` (dev artifacts + logging style + timeout)
**Type:** Code Quality Cleanup  
**Location:** `runner.py` — multiple lines

**Current Problem (four sub-issues):**  
A) `# BUG-C3:`, `# BUG-C4:`, `# BUG-C5:` dev artifact comments (lines 200, 231, 331).  
B) F-strings in `logger.*()` calls (lines 150, 156, 175) — eager string evaluation.  
C) Hardcoded `aiohttp.ClientTimeout(total=300)` (line 309).  
D) Redundant `results.sort(key=lambda x: x[0])` and `(idx, seg)` tuple pattern (lines 128, 328).

**Solution:**
A) Replace all three `# BUG-Cx:` prefixes with plain English descriptions.  
B) Change:
   ```python
   logger.info(f"[{tag}] Synthesizing OFFLINE tone wrapper...")
   ```
   to:
   ```python
   logger.info("[%s] Synthesizing OFFLINE tone wrapper...", tag)
   ```
   (3 occurrences)  
C) Change `aiohttp.ClientTimeout(total=300)` → `aiohttp.ClientTimeout(total=settings.api_timeout_seconds)`. Add `from src.agents.core.config import settings` import.  
D) Remove `idx: int` from `_process_segment` signature, change return type from `tuple[int, AudioSegment]` to `AudioSegment`, change `return idx, AudioSegment(...)` to `return AudioSegment(...)`, remove `results.sort(...)` and change `[seg for _, seg in results]` to `list(results)`.

**Risk:** Low — each sub-fix is mechanical.  
**Behavior Change:** C — timeout now respects `settings.api_timeout_seconds` (configurable via `.env`).

---

## 🟢 Low Priority

### REFACTOR-09: `trimming.py` — seek_step, typing, degenerate warning
**Type:** Performance + Code Quality  
**Location:** `trimming.py:47`, `trimming.py:51`, `trimming.py:61–62`

**Current Problem:**
- `seek_step=1` in `detect_nonsilent` — checks every 1 ms; ~3,000 iterations for a 3s clip.
- `Tuple` from `typing` in `_trim_bounds` return type — legacy import.
- Degenerate `end <= start` case returns full audio silently — no log.

**Solution:**
1. Change `seek_step=1` → `seek_step=10` (120ms silence window; 10ms step cannot miss it; 10× faster).
2. Change `Tuple[int, int]` → `tuple[int, int]` (already has `from __future__ import annotations`; remove `from typing import Tuple`).
3. Before `return 0, len(audio)` in the `end <= start` branch — add:
   ```python
   logger.warning("Degenerate trim bounds (end <= start) for audio — returning full length.")
   ```
4. Add `import logging; logger = logging.getLogger(__name__)` at top of file.

**Risk:** Very Low.  
**Behavior Change:** Trimming is 10× faster; degenerate cases are now logged.

---

### REFACTOR-10: `contracts.py` — modern typing + `created_at` timestamp
**Type:** Code Quality  
**Location:** `contracts.py:6–8`, `contracts.py:68–72`

**Current Problem:**
- `List`, `Optional` from `typing` — legacy.
- `Phase3Payload` has no `created_at` field — cache-hit debugging produces no timestamp.

**Solution:**
1. Add `from __future__ import annotations` at top.
2. Replace `from typing import List, Optional, Literal` with `from typing import Literal`.
3. Change `Optional[float]` → `float | None`, `List[AudioSegment]` → `list[AudioSegment]`, `Optional[int]` → `int | None`.
4. Add to `Phase3Payload`:
   ```python
   from datetime import datetime, timezone
   created_at: datetime = Field(
       default_factory=lambda: datetime.now(timezone.utc),
       description="UTC timestamp when this payload was assembled.",
   )
   ```
5. Update `rpm_limit` docstring to clarify it is defined but not yet enforced by the runner.

**Risk:** Very Low — pydantic resolves both `Optional[X]` and `X | None` identically.  
**Behavior Change:** `Phase3Payload` now carries a `created_at` field in JSON output.

---

### REFACTOR-11: `packager.py` — deepcopy + `os.unlink` consistency
**Type:** Code Quality  
**Location:** `packager.py:44`, `packager.py:58`

**Current Problem:**
- `os.remove` in exception cleanup (line 44) — inconsistent with `os.unlink` used everywhere else in the codebase.
- `out = dict(script_payload)` (line 58) — shallow copy; fragile against future schema growth with nested mutable values.

**Solution:**
1. Line 44 — change `os.remove(tmp_name)` → `os.unlink(tmp_name)`.
2. Line 58 — change `out = dict(script_payload)` → `out = copy.deepcopy(script_payload)`. Add `import copy` at top.

**Risk:** Very Low.  
**Behavior Change:** None observable; correctness guarantee improved for future schema growth.

---

## Execution Order

Execute in this order to avoid dependency breaks:

| Step | Refactor | Reason |
|------|----------|--------|
| 1 | **REFACTOR-10** | `contracts.py` typing — safe isolated change; other files import from it |
| 2 | **REFACTOR-11** | `packager.py` deepcopy + unlink — isolated, REFACTOR-02 adds a new function here next |
| 3 | **REFACTOR-02** | Add `atomic_write_bytes` to `packager.py` first, before runner uses it |
| 4 | **REFACTOR-01** | Create `_offline_tts.py`, update `runner.py` import — decouple test→production |
| 5 | **REFACTOR-09** | `trimming.py` seek_step — isolated performance fix |
| 6 | **REFACTOR-06** | Add `duration_both()` to `duration.py`, then update `runner.py` |
| 7 | **REFACTOR-04** | `tts_client.py` error handling — isolated to one file |
| 8 | **REFACTOR-05** | `tts_client.py` key resolution — isolated to one file |
| 9 | **REFACTOR-03** | `asyncio.gather` fix in `runner.py` — do after REFACTOR-06 stabilizes runner |
| 10 | **REFACTOR-07** | `offline_e2e.py` path + logging — isolated harness |
| 11 | **REFACTOR-08** | `runner.py` cleanup — final polish after all structural changes are stable |

**Logic:**
- Steps 1–2 are safe cosmetic/contract-level changes with no runtime risk.
- Steps 3–4 add new functions (`atomic_write_bytes`, `_offline_tts.py`) before any callers are updated.
- Steps 5–8 are isolated single-file fixes that don't depend on each other.
- Step 9 (`asyncio.gather`) changes concurrency semantics — do last among the structural fixes.
- Steps 10–11 are polish — safe to do last.

---

## Risk Assessment

| Refactor | Risk | What Can Break | Mitigation |
|----------|------|----------------|------------|
| REFACTOR-01 | Low | Import paths | Compile-check after + run `tests_offline.py` |
| REFACTOR-02 | Low | File write behavior | Run offline e2e — verify `.mp3` files created |
| REFACTOR-03 | Medium | Gather semantics | Run offline e2e — verify all segments complete |
| REFACTOR-04 | Low | Error propagation | Config error should now raise, not silently fallback |
| REFACTOR-05 | Low | None | Tests using env-var patching will now work correctly |
| REFACTOR-06 | Low | None | Verify `d_ms` and `d_sec` values match old separate calls |
| REFACTOR-07 | Low | None | Run `offline_e2e.py` from a different CWD to verify path |
| REFACTOR-08 | Low | Timeout value | `settings.api_timeout_seconds` must be set in `.env` |
| REFACTOR-09 | Low | None | Trimming result should be identical |
| REFACTOR-10 | Low | Pydantic schema | Existing callers get a new `created_at` field in payload |
| REFACTOR-11 | Low | None | Purely defensive |

**Overall Risk:** Low–Medium  
**Recommendation:** Feature branch (`features/phase3-refactor`). Each REFACTOR = one commit for clean rollback.

---

## Scope — What Will NOT Change

- **Business logic** — synthesis → trim → duration → persist → underrun-gate pipeline stays identical.
- **Public API** — `run_phase3(job_dir, tts_settings)` signature unchanged.
- **`job.json` / `script.json` schema** — only `Phase3Payload` gains `created_at`; existing fields unchanged.
- **Retry counts and backoff values** — 3 attempts, exponential 2–10s for standard; 4 attempts, 30–120s for 429.
- **Cache hit logic** — hash computation, file integrity check, tolerance math — all preserved.
- **`duration.py`/`trimming.py`/`packager.py` existing functions** — no signatures changed.

---

## Verify

After each REFACTOR, run these checks:

```bash
# 1. Compile smoke check (run after every single REFACTOR)
python -m py_compile src/agents/phase3_audio/_offline_tts.py \
  src/agents/phase3_audio/contracts.py \
  src/agents/phase3_audio/duration.py \
  src/agents/phase3_audio/trimming.py \
  src/agents/phase3_audio/packager.py \
  src/agents/phase3_audio/tts_client.py \
  src/agents/phase3_audio/runner.py \
  src/agents/phase3_audio/tests_offline.py \
  src/agents/phase3_audio/offline_e2e.py

# 2. Full test suite (after REFACTOR-01 and REFACTOR-03 especially)
python -m pytest tests/ -v --tb=short
# Expected: 23 passed, 1 pre-existing failure (line_chart template fixture)

# 3. Offline e2e harness (after REFACTOR-02, REFACTOR-03, REFACTOR-07)
PHASE3_OFFLINE=1 PHASE3_SKIP_UNDERRUN=1 python -m src.agents.phase3_audio.offline_e2e
# Expected: ✅ PHASE 3 E2E SIMULATION: PASS

# 4. Offline TTS harness (after REFACTOR-01)
python -m src.agents.phase3_audio.tests_offline
# Expected: PASS for all 3 tags, "Offline harness complete."
```
