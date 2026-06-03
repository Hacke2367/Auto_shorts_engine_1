# Code Review — `src/agents/phase3_audio/`

**Level:** Expert  
**Date:** 2026-05-26  
**Reviewer:** Claude Code  
**Files Reviewed:** 8 (`contracts.py`, `duration.py`, `trimming.py`, `packager.py`, `tts_client.py`, `runner.py`, `offline_e2e.py`, `tests_offline.py`)

---

## 📄 `contracts.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 20%  
**Verdict:** Solid type contracts with good exception hierarchy, but legacy typing imports and a dead `rpm_limit` field that is defined but never enforced.

### ✅ What's Good
- Exception hierarchy (`TTSError`, `AudioTrimError`, `UnderRunError`, `PayloadAssemblyError`) clearly maps to each failure domain.
- `AudioSynthesisSettings` correctly models all ElevenLabs voice parameters as optional with `ge`/`le` bounds.
- `Phase3Payload.inputs_hash` enables deterministic idempotency checking.

### ⚠️ Issues Found

🟡 Medium Priority
- **`rpm_limit` field defined but never enforced anywhere** (`contracts.py`, line 61). `AudioSynthesisSettings` declares `rpm_limit: Optional[int]`, but `runner.py` only uses `concurrency_limit` (via `asyncio.Semaphore`). `rpm_limit` is read from config but silently ignored — callers who set it believe rate-limiting is active when it is not. Either implement token-bucket enforcement in the runner or remove the field.

🟢 Low Priority
- **`List`, `Optional`, `Literal` from `typing`** (`contracts.py`, line 6). All files in Phase 1/2 use `from __future__ import annotations` with built-in generics. This file does not. Modernize to `list[...]`, `X | None`, and add `from __future__ import annotations`.
- **`Phase3Payload` has no `created_at` timestamp** — when debugging a cache hit, there is no record of when synthesis ran. Consistent with Phase 2 `ScriptPayload` fix already applied.

---

## 📄 `duration.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 20%  
**Verdict:** Correct and safe, but the function pair encourages a double pydub decode per segment in the caller.

### ✅ What's Good
- Wraps pydub decode in a clear `AudioTrimError` with the original exception chained — stack traces are readable.
- `duration_sec` correctly rounds to 3 decimal places.

### ⚠️ Issues Found

🟡 Medium Priority
- **Double pydub decode per segment** (`runner.py`, lines 160–161). `runner.py` calls `duration_ms(trimmed_bytes)` then `duration_sec(trimmed_bytes)` back-to-back. Each call independently decodes the MP3 bytes through pydub (which calls ffmpeg). For a 10-segment job this is 20 ffmpeg decode passes instead of 10. Add a `duration_both(audio_bytes) -> tuple[int, float]` helper that decodes once and returns both values.

🟢 Low Priority
- **`int(len(audio))` relies on implicit pydub convention** (`duration.py`, line 21). `len()` on a pydub `AudioSegment` returns milliseconds — this is correct but undocumented. Add a one-line comment: `# pydub len() returns duration in ms`.

---

## 📄 `trimming.py` — Expert Review

**Code Quality:** 8/10  
**Improvement Chance:** 15%  
**Verdict:** Well-designed threshold-based trimming with good fallback behavior. Minor performance and typing issues only.

### ✅ What's Good
- `_compute_silence_thresh_dbfs` handles pure-silence audio (`-inf dBFS`) correctly — returns a safe floor rather than crashing or producing `NaN`.
- `_trim_bounds` returns full audio when no speech is detected — safe fallback, no truncation.
- `TrimConfig` as a frozen dataclass makes the configuration immutable and hashable.

### ⚠️ Issues Found

🟡 Medium Priority
- **`seek_step=1` in `detect_nonsilent`** (`trimming.py`, line 51). This checks every 1 ms. For a 3-second audio segment this means ~3,000 iterations through the audio. With `min_silence_len_ms=120`, `seek_step=10` gives identical results 10× faster — the silence window is 120ms so checking every 10ms cannot miss it.

🟢 Low Priority
- **`Tuple` from `typing` in `_trim_bounds` signature** (`trimming.py`, line 47). Use `tuple[int, int]` with `from __future__ import annotations` (already imported).
- **Degenerate `end <= start` case returns full audio silently** (`trimming.py`, line 61–62). This should log a `logger.warning("Degenerate trim bounds for audio — returning full length.")` so abnormal inputs surface during debugging.

---

## 📄 `packager.py` — Expert Review

**Code Quality:** 8/10  
**Improvement Chance:** 15%  
**Verdict:** The `atomic_write_json` implementation is the strongest in the codebase — it includes `fsync` before `os.replace`. Minor shallow-copy fragility in `update_script_with_audio`.

### ✅ What's Good
- `atomic_write_json` does `tmp.flush()` + `os.fsync(tmp.fileno())` before `os.replace` — correct durability guarantee even on power loss.
- `update_script_with_audio` raises `ValueError` rather than silently writing an incomplete payload when an audio segment is missing.
- `build_job_json` accepts an `extra` dict for extensibility without requiring callers to know the full schema.

### ⚠️ Issues Found

🟡 Medium Priority
- **`dict(script_payload)` is a shallow copy** (`packager.py`, line 58). `out = dict(script_payload)` copies the top-level keys but any nested dict values (e.g., if the payload ever contains nested objects beyond `segments`) are still shared references. For the current payload this is safe, but it is fragile against schema growth. Use `copy.deepcopy(script_payload)` for correctness guarantee.

🟢 Low Priority
- **`os.remove` used in exception cleanup** (`packager.py`, line 44) instead of `os.unlink` which is the convention used across the rest of the codebase. They are functionally identical but inconsistency makes the code harder to audit.

---

## 📄 `tts_client.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 35%  
**Verdict:** Retry structure is solid, but the module-level API key resolution silently swallows config errors, and HTTP 5xx responses are not retried despite being transient.

### ✅ What's Good
- Two-layer retry strategy (429-aware outer + transient-error inner) is correct and matches the Phase 1 pattern.
- Voice settings are only injected into the payload when not `None` — avoids sending `null` fields to the API.
- ElevenLabs key is in the `xi-api-key` header (correct placement).

### ⚠️ Issues Found

🔴 High Priority
- **`except Exception: _ELEVENLABS_KEY = os.getenv(...)` swallows ALL import errors silently** (`tts_client.py`, lines 39–40). If `settings` fails to import due to a misconfigured `.env`, a missing package, or a syntax error in `config.py`, the exception is caught and the code silently falls back to the env var. A real config error is hidden. Narrow the catch: `except ImportError:` only — all other errors should propagate.

- **HTTP 5xx from ElevenLabs raises `TTSError` which bypasses the retry policy** (`tts_client.py`, line 124). `_get_standard_retry()` only retries `aiohttp.ClientError` and `asyncio.TimeoutError`. A transient `HTTP 500` or `HTTP 503` from ElevenLabs raises `TTSError` and immediately propagates to the caller with no retry. Add a 5xx check before the 4xx one:
  ```python
  if resp.status >= 500:
      raise aiohttp.ClientResponseError(
          resp.request_info, resp.history, status=resp.status
      )
  ```

🟡 Medium Priority
- **`_ELEVENLABS_KEY` is resolved once at module import time** (`tts_client.py`, lines 32–40). If the env var is set after import (common in tests using `monkeypatch` or `os.environ`), the constant is stale. Read the key inside `synthesize()` on each call, or use a `@functools.lru_cache`-decorated getter function.

🟢 Low Priority
- **`payload: dict = {...}` type annotation** (`tts_client.py`, line 87). Should be `payload: dict[str, Any]` for precision. The bare `dict` annotation is uninformative.

---

## 📄 `runner.py` — Expert Review

**Code Quality:** 5/10  
**Improvement Chance:** 40%  
**Verdict:** Good architecture (concurrent synthesis, hash-based idempotency with file integrity checks) severely undermined by a production→test import, non-atomic audio file writes, uncancelled sibling tasks on failure, and multiple dev artifact comments.

### ✅ What's Good
- Cache validation goes beyond hash comparison — it re-reads each audio file and checks the decoded duration against the cached value (within 10% tolerance). This catches partial writes and corrupt files.
- `_validate_phase3_inputs` checks each segment for empty `text` before any TTS call.
- `_compute_inputs_hash` correctly strips Phase 3-derived fields (`audio_relpath`, `duration_ms`) from the script before hashing to avoid false cache busts.
- The offline/online mode split via env var is clean and testable.

### ⚠️ Issues Found

🔴 High Priority
- **Production code imports from `tests_offline.py`** (`runner.py`, line 36): `from src.agents.phase3_audio.tests_offline import _fake_tts`. This is a critical architectural violation — `tests_offline.py` has `logging.basicConfig(level=logging.INFO)` at module level, which configures the root logger silently on every import of `runner.py`. Move `_fake_tts` to a proper module (e.g., `src/agents/phase3_audio/_offline_tts.py`) and import from there in both the runner and the offline harness.

- **Audio file written non-atomically** (`runner.py`, lines 164–165):
  ```python
  with open(audio_file_path, "wb") as f:
      f.write(trimmed_bytes)
  ```
  A crash or `KeyboardInterrupt` mid-write leaves a truncated `.mp3`. The cache check tries to detect 0-byte files but cannot detect partial writes (a truncated MP3 will have non-zero size). Apply the same atomic pattern: write to a temp file in `audio_dir` then `os.replace`. Since `packager.py` already provides `atomic_write_json`, add a parallel `atomic_write_bytes(path, data)` helper there.

- **`asyncio.gather(*tasks)` doesn't cancel sibling tasks on first failure** (`runner.py`, lines 307 and 326). Without `return_exceptions=True`, the first `UnderRunError` or `TTSError` raises immediately — but all other running tasks continue consuming ElevenLabs API quota and writing audio files for a job that will be aborted. Use `return_exceptions=True`, then inspect results and re-raise:
  ```python
  results = await asyncio.gather(*tasks, return_exceptions=True)
  errors = [r for r in results if isinstance(r, BaseException)]
  if errors:
      raise errors[0]
  ```
  Or use `asyncio.TaskGroup` (Python 3.11+) which cancels siblings automatically.

🟡 Medium Priority
- **`# BUG-C5:`, `# BUG-C3:`, `# BUG-C4:` dev artifact comments** (`runner.py`, lines 200, 231, 331). Same cleanup issue fixed in Phase 1/2. Replace with plain descriptions.
- **f-strings in `logger.*()` calls** (`runner.py`, lines 150, 156, 175). `logger.info(f"[{tag}] Synthesizing OFFLINE tone wrapper...")` evaluates the string eagerly. Use `logger.info("[%s] Synthesizing OFFLINE tone wrapper...", tag)`.
- **`results.sort(key=lambda x: x[0])` is redundant** (`runner.py`, line 328). `asyncio.gather` guarantees results in the same order as the input coroutines. The `(idx, segment)` tuple pattern adds complexity without benefit — remove `idx` from `_process_segment`'s return type and let `gather`'s natural ordering apply.
- **Hardcoded 300-second timeout** (`runner.py`, line 309): `aiohttp.ClientTimeout(total=300)`. Should use `settings.api_timeout_seconds` for consistency with other phases. If TTS synthesis legitimately needs a longer timeout, define it in `AudioSynthesisSettings`.

🟢 Low Priority
- **`session = None` passed to `_process_segment` in offline mode** (`runner.py`, line 291). The offline code path receives a `None` session and the function guards against it inside the online branch. The type signature allows `None` only to support offline mode — a cleaner design would have the offline path call a different function or use a duck-typed TTS callable injected as a parameter.
- **Double pydub decode per segment** (`runner.py`, lines 160–161). `duration_ms(trimmed_bytes)` + `duration_sec(trimmed_bytes)` = 2 separate ffmpeg decode passes per segment. Use a combined helper (see `duration.py` recommendation).

---

## 📄 `offline_e2e.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 25%  
**Verdict:** Useful integration harness, but the relative path for the test job directory is dangerous and the module-level `logging.basicConfig` contaminates any importer's logging config.

### ✅ What's Good
- Covers the critical idempotency path (Run 1 → Run 2) explicitly.
- Asserts both presence and content of the written `script.json` and `job.json`.

### ⚠️ Issues Found

🟡 Medium Priority
- **`_TEST_JOB_DIR = Path("jobs/test_job")` is a relative path** (`offline_e2e.py`, line 23). This resolves to whatever the CWD is when the script runs. If run from a subdirectory or an IDE, the test job is created in the wrong location and pollutes unintended directories. Use `Path(__file__).resolve().parents[4] / "jobs" / "test_job"` to anchor to the project root.
- **`logging.basicConfig(level=logging.INFO)` at module level** (`offline_e2e.py`, line 20). Any code that imports from this file (currently `runner.py` imports `_fake_tts` indirectly) reconfigures the root logger silently. Move `basicConfig` inside `if __name__ == "__main__"` guard only.

🟢 Low Priority
- **`open()` without `encoding` parameter** (`offline_e2e.py`, lines 83, 94). `open(_TEST_JOB_DIR / "job.json", "r")` should specify `encoding="utf-8"`.
- **`assert len(files) == 7` hardcoded** (`offline_e2e.py`, line 80). The assertion count is tied to the dummy payload's segment count. Use `assert len(files) == len(dummy_payload["segments"])` so the assertion auto-updates if the payload changes.

---

## 📄 `tests_offline.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 15%  
**Verdict:** Clean and focused offline TTS stub, but `_fake_tts` is imported by production `runner.py` — it must be relocated.

### ✅ What's Good
- `_fake_tts` correctly generates tone + silence padding that exercises the trim pipeline.
- Test covers both raw and trimmed duration, and validates `trim_ms < raw_ms`.

### ⚠️ Issues Found

🔴 High Priority
- **`_fake_tts` is in a test file but imported by production `runner.py`** (`runner.py`, line 36). Move `_fake_tts` to `src/agents/phase3_audio/_offline_tts.py` (or inline it into `tts_client.py` behind a provider check). `tests_offline.py` then imports from that module. This removes the test→production circular dependency.

🟢 Low Priority
- **`ok = (trim_ms > 0) and (trim_ms < raw_ms)` check is weak** (`tests_offline.py`, line 51). A trimmed result equal to `raw_ms` (no silence detected) would be flagged as `FAIL` even though the audio is valid — the tone has `300ms` head + `300ms` tail silence which should always be detected. This is acceptable for offline testing, but the check could verify `trim_ms >= secs * 1000 * 0.8` to confirm the tone itself wasn't trimmed.

---

## 📊 Overall Project Report — Expert Review

**Files Reviewed:** 8  
**Overall Quality Score:** 6/10  
**Overall Improvement Chance:** 28%  
**Verdict:** ❌ Not production-ready — production code imports from a test file (which misconfigures the root logger on every import), audio files are written non-atomically, `asyncio.gather` leaks API calls on first failure, and HTTP 5xx from ElevenLabs is never retried.

### Score Breakdown

| File | Score | Expert OK? |
|------|-------|------------|
| `packager.py` | 8/10 | ✅ |
| `trimming.py` | 8/10 | ✅ |
| `duration.py` | 7/10 | ✅ with caveats |
| `contracts.py` | 7/10 | ✅ with caveats |
| `tests_offline.py` | 7/10 | ✅ (once relocated) |
| `offline_e2e.py` | 6/10 | ⚠️ |
| `tts_client.py` | 6/10 | ⚠️ |
| `runner.py` | 5/10 | ❌ |

---

### Common Issues (Across the Codebase)

- **f-strings in `logger.*()` calls** — `runner.py` uses `logger.info(f"[{tag}] ...")`. Use `%s` lazy formatting to avoid eager string evaluation.
- **Legacy `typing` imports** — `contracts.py` and `trimming.py` use `List`, `Optional`, `Tuple` from `typing` instead of built-in generics. Add `from __future__ import annotations` and use `list[...]`, `tuple[...]`, `X | None`.
- **Dev artifact comments** — `# BUG-C3:`, `# BUG-C4:`, `# BUG-C5:` in `runner.py` need cleanup like Phase 1/2 fixes.

---

### 🔴 Critical Fixes (Do First)

1. **`runner.py` line 36** — Remove `from src.agents.phase3_audio.tests_offline import _fake_tts`. Create `src/agents/phase3_audio/_offline_tts.py` with the `_fake_tts` function and import from there. This also fixes the root logger contamination from `offline_e2e.py`'s `logging.basicConfig`.

2. **`runner.py` lines 164–165** — Make per-segment audio file write atomic:  
   Write to `tempfile.mkstemp(dir=str(audio_dir), suffix=".tmp")` then `os.replace` to the final path. Add `atomic_write_bytes(path: Path, data: bytes) -> None` helper to `packager.py`.

3. **`runner.py` lines 307 / 326** — Add `return_exceptions=True` to both `asyncio.gather` calls, inspect results, and re-raise the first exception. This prevents leaking ElevenLabs API calls when one segment fails.

4. **`tts_client.py` line 39** — Change `except Exception:` to `except ImportError:` so real config errors are not silently swallowed.

5. **`tts_client.py` line 122–124** — Add retry for HTTP 5xx before the generic non-2xx handler:
   ```python
   if resp.status >= 500:
       raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
   ```

---

### 🟡 Important Improvements

1. **`tts_client.py` lines 32–40** — Move `_ELEVENLABS_KEY` resolution inside `synthesize()` so env-var changes after import (e.g., in tests) take effect.
2. **`runner.py` lines 160–161** — Replace `duration_ms()` + `duration_sec()` separate calls with a single `duration_both()` helper to avoid 2 ffmpeg decodes per segment.
3. **`contracts.py` line 61** — Either implement `rpm_limit` enforcement in the runner (token bucket) or remove the field.
4. **`offline_e2e.py` line 23** — Change `_TEST_JOB_DIR` to an absolute path anchored to the project root.
5. **`offline_e2e.py` line 20** — Move `logging.basicConfig(...)` inside `if __name__ == "__main__":`.
6. **`runner.py` lines 200, 231, 331** — Remove `# BUG-C5:`, `# BUG-C3:`, `# BUG-C4:` dev artifact comments.
7. **`runner.py` line 309** — Replace hardcoded `300` with `settings.api_timeout_seconds`.

---

### 🟢 Nice to Have

1. **`trimming.py` line 51** — Change `seek_step=1` to `seek_step=10` for 10× faster silence detection with no perceptible accuracy loss.
2. **`packager.py` line 58** — Change `dict(script_payload)` to `copy.deepcopy(script_payload)` for correctness against future schema growth.
3. **`runner.py` line 328** — Remove the `(idx, seg)` tuple pattern and `results.sort()` — `asyncio.gather` already preserves order.
4. **`contracts.py`** — Add `from __future__ import annotations`, modernize `List` → `list`, `Optional` → `X | None`.
5. **`trimming.py` line 61** — Add `logger.warning(...)` when degenerate trim bounds are detected.
