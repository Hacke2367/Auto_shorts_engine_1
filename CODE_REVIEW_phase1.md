# Code Review — `phase1_discovery/` + `phase1_extraction/` — Expert Level

**Reviewed on:** 2026-05-22  
**Level:** 🔴 Expert (Production-grade audit)  
**Files Reviewed:** 8 (`archive_manager.py`, `candidate_score.py`, `discovery_runner.py`, `scourer.py`, `api_clients.py`, `graph.py`, `runner.py`, + `__init__.py` ×2)

---

## 📄 `archive_manager.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 35%  
**Verdict:** Solid atomic-write pattern and backward-compatible migration, but completely unprotected against concurrent processes — a silent data-loss risk.

### ✅ What's Good
- `_save()` uses `tempfile.mkstemp` → `os.replace` — crash-safe atomic writes, same as `job_manager`.
- Three-state model (produced / rejected / saved_queue) with TTL enforcement is well-designed.
- `_migrate_entries` handles three different legacy schema formats gracefully.
- `is_duplicate` does lazy expiry — avoids stale entries accumulating silently.
- `mark_rejected` reconciles state by removing from `_produced` before adding to rejected.

### ⚠️ Issues Found

🔴 **High Priority**
- **No file-level locking — concurrent processes silently overwrite each other.** `mark_produced` and `mark_rejected` do: read in-memory state → mutate → `_save()`. If two CLI processes run simultaneously (e.g., two discovery runs), both load the archive from disk into separate `ArchiveManager` instances, both mutate their in-memory copy, and the last `_save()` wins — erasing the other's changes. Fix: use a cross-process lock file (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) wrapping every `_save()` + memory-mutate cycle, or enforce single-writer by design in the CLI layer.
- **`expire_stale_entries()` called in `__init__` causes write on every instantiation.** If the archive has expired entries, every `ArchiveManager()` constructor call triggers `_save()`. The discovery runner instantiates `ArchiveManager()` inside `run_discovery` on every invocation. In high-frequency CLI usage, this means disk writes on every pipeline startup. Decouple expiry from construction — call it explicitly only at session start, not in `__init__`.

🟡 **Medium Priority**
- **`normalize_topic` does not strip punctuation.** Topics `"AI/ML History"` and `"AI ML History"` normalize to different strings (`"ai/ml history"` vs `"ai ml history"`), allowing duplicate detection bypass. Add `re.sub(r"[^\w\s]", "", topic)` before whitespace normalization.
- **`_save()` rewrites the ENTIRE archive on every single mutation.** `add_to_queue`, `mark_produced`, `pop_queue` all call `_save()` which serializes all entries. For an archive with 200+ topics, a single `pop_queue(1)` rewrites the full file. Consider dirty-flag + explicit `flush()` pattern, or only save when the caller is done with a batch of mutations.

🟢 **Low Priority**
- Development comment `# ADDED:` on line 55 should be removed before production.
- `normalize_topic` is `@staticmethod` but called as `self.normalize_topic()` internally — inconsistent with external callers using `ArchiveManager.normalize_topic()`. Pick one convention.

---

## 📄 `candidate_score.py` — Expert Review

**Code Quality:** 4/10  
**Improvement Chance:** 55%  
**Verdict:** ❌ Contains a production-breaking bug that silently discards ALL scored candidates. Also has a security issue (API key in URL) and a misplaced import.

### ✅ What's Good
- Two-tier retry strategy (429-aware outer + transient-error inner) — correct architecture for Gemini rate limiting.
- `_safe_parse_score` clamps LLM output to `[1, 10]` — prevents out-of-range scores.
- `asyncio.Semaphore` acquired AFTER `limiter.acquire()` — prevents holding the concurrency pool while waiting for a rate limit token (correct ordering).
- Balanced brace parser in `_strip_markdown_json` is more robust than regex-based JSON extraction.

### ⚠️ Issues Found

🔴 **High Priority**
- **`_parse_scoring_response` line 194: `.replace("_", "-")` breaks ALL template names.** The code does:
  ```python
  best_fit = str(data.get("best_fit_template", "")).strip().lower().replace("_", "-")
  ```
  All valid templates use underscores (`"bar_chart"`, `"butterfly_chart"`, etc.). This replacement converts them to `"bar-chart"`, `"butterfly-chart"` — which are NOT in `VALID_TEMPLATES`. The subsequent check `if best_fit not in VALID_TEMPLATES: return None` then discards EVERY candidate, including valid ones. This means `score_candidates_batch` always returns an empty list in production. Fix: remove `.replace("_", "-")` entirely. The LLM is shown template names with underscores in the prompt and returns them the same way.
- **API key exposed in URL query string (line 267: `?key={key}`).** The Gemini API key is appended to the URL. It will appear in server-side access logs, proxy logs, and any HTTP exception tracebacks. Use the `x-goog-api-key` header instead:
  ```python
  url = f"https://.../{model_name}:generateContent"
  headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
  async with session.post(url, json=payload, headers=headers) as resp:
  ```
- **`import re` at line 117 is inside the module body, not at the top.** Static analysis tools (mypy, ruff) flag mid-module imports. Move to the top-level imports section.

🟡 **Medium Priority**
- **`score_candidates_batch` creates a fresh `TokenBucketRateLimiter(rpm=settings.gemini_rpm_limit)` on every call (line 357).** If called twice in a session (e.g., two discovery phases), each call gets a new full-bucket limiter. The RPM limit is not enforced across calls — effectively doubling the allowed request rate. Pass the limiter as a parameter or create it once at the session level.
- **Temperature hardcoded at `0.1` in `score_single_candidate` payload (line 284)** instead of using `settings.gemini_temperature`. Inconsistent with `gemini_extract` in `api_clients.py` which reads from settings.
- **429 retry + `limiter.apply_penalty` are redundant and can stack wait times.** The `tenacity` `_get_429_retry_policy()` waits 60–120s between retries. But `apply_penalty(60.0)` also imposes a 60s global pause on the rate limiter. All concurrent candidates hitting 429 simultaneously will wait 60s from the limiter PLUS 60–120s from tenacity — stacking to 2–3 minutes of total wait. These two mechanisms should be unified.

🟢 **Low Priority**
- Typo in prompt (line 93): `"actally"` → `"actually"`.
- `norm = re.sub(r"\s+", " ", norm)` (line 210) is a copy of `ArchiveManager.normalize_topic()`. DRY violation — import and call the shared function.

---

## 📄 `discovery_runner.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 35%  
**Verdict:** Good pipeline orchestration with thorough archive filtering, but critical writes are non-atomic and the idempotency check ignores changed parameters.

### ✅ What's Good
- Double archive filter (pre-search AND post-search at lines 163–195) — prevents scoring duplicates that Tavily might surface.
- Emergency fallback hypotheses if ideation returns nothing — robust degradation.
- Source URL deduplication and merge into scored candidates — good audit trail.
- Queue injection with score-based sorting — prevents stale topics from blocking fresh discoveries.
- Idempotency check at start using cached `candidates.json`.

### ⚠️ Issues Found

🔴 **High Priority**
- **`candidates_path.write_text(batch.model_dump_json(...))` at line 326 is NOT atomic.** A crash mid-write leaves a corrupt `candidates.json`. On the next run, the idempotency check reads it, `DiscoveryBatch.model_validate` fails, logs a warning, and reruns discovery — silently discarding the previous partial result. Use `tempfile.mkstemp` → `os.replace` (same pattern as `_save()` in `archive_manager.py`).
- **`_ideate_hypotheses` has no retry on transient failures.** The HTTP call is wrapped in a bare `except Exception: log.warning(...); return []`. A temporary Gemini 503 or network blip causes ideation to silently fail, falling back to hardcoded generic topics. Add the same `_get_retry_policy()` retry wrapper used in `scourer.py`.
- **API key in URL (line 73: `?key={key}`).** Same security issue as `candidate_score.py` — Gemini API key in query string appears in server logs. Fix: use `x-goog-api-key` header.

🟡 **Medium Priority**
- **Idempotency cache ignores `niche_hint` and `top_n` changes.** If `candidates.json` exists from a run with `niche_hint=None`, calling again with `niche_hint="AI"` returns the stale broad batch silently. The cache key should include `niche_hint` and `top_n` as a content hash or version tag.
- **Queue-injected `TopicCandidate` inflates sub-scores (lines 263–275).** Every sub-score is set to `q_item.final_score` (e.g., `hook_potential_score = 7.0`). `compute_final_score()` then recalculates using the new ideation-first weights and produces `hook(0.30) + novelty(0.20) + ... = 7.0 × 1.0 = 7.0`. This happens to be correct only because all sub-scores are equal. If any weight changes, the reconstructed score will silently drift from the stored `final_score`.
- **`raw_path.write_text(json.dumps(raw_candidates, ...))` at line 334** — also non-atomic. Not critical for pipeline correctness (it's only an audit file), but inconsistent with the codebase's own standards.

🟢 **Low Priority**
- Comment `# ---------------- ADD THIS BLOCK ----------------` at line 184 is a development artifact — remove before production.
- Comment `# CHANGE raw_candidates to novel_raw_candidates here` at line 207 — applied but not cleaned up.

---

## 📄 `scourer.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 25%  
**Verdict:** Clean and focused, correct concurrency pattern. Missing timeout enforcement and one URL deduplication detail.

### ✅ What's Good
- Hypothesis-focused search (not broad buckets) — correct Idea-First approach.
- `asyncio.Semaphore` for concurrent Tavily calls — prevents API flooding.
- `_dedupe_raw_candidates` merges source URLs AND keeps the longer snippet — smart merge.
- `asyncio.gather(*tasks, return_exceptions=True)` handles individual failures gracefully.
- Response parsing guards for missing title/content/url fields.

### ⚠️ Issues Found

🔴 **High Priority**
- **No timeout on Tavily HTTP calls in the discovery path.** `scourer.py` is called from `discovery_runner.py` which creates no `aiohttp.ClientSession` timeout. The `session` passed in has no timeout configured. A hanging Tavily request blocks the Semaphore slot indefinitely, stalling all concurrent hypothesis validations. Fix: `scourer.py` should create its own timeout: `timeout = aiohttp.ClientTimeout(total=30.0)` and pass it when constructing the session, or accept a `timeout` parameter.

🟡 **Medium Priority**
- **`list(set(urls))` at line 101 destroys URL insertion order.** Later, `api_clients.py`'s `tavily_extract` processes URLs in the order received. Randomizing order means high-authority URLs (which Tavily tends to rank first) may be processed later. Use `dict.fromkeys(urls)` to deduplicate while preserving order.
- **Snippet combination strategy is over-aggressive.** `"\n\n".join(snippets)` can produce 8+ KB of combined text. Downstream, `candidate_score.py` truncates to `snippet[:2000]` — so most of the combined text is never used. Truncate per-source before combining: `f"Source: {title}\n{content[:500]}"` for a more useful 2KB total.
- **`_dedupe_raw_candidates` imports `ArchiveManager` inside the function body (line 113)** to avoid a circular import. This is a code smell — if the import is safe, move it to the top. If it causes a circular import, move the `normalize_topic` logic to a shared `src/agents/core/utils.py` function.

🟢 **Low Priority**
- `_get_retry_policy` returns `min=1, max=5` backoff — too short for Tavily's occasional server-side delays. Use `min=2, max=15`.
- Search query appends `"statistics data market share ranking comparison"` regardless of template type — not template-aware. `vs_card` topics would benefit from `"versus comparison specifications"` instead.

---

## 📄 `api_clients.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 35%  
**Verdict:** Consistent retry pattern and good telemetry, but contains dead code, a duplicate function, a security issue, and an authority tier heuristic that over-matches.

### ✅ What's Good
- All three clients (`tavily_search`, `tavily_extract`, `gemini_extract`) use identical retry policy — consistent failure handling.
- `log_api_call` on every request — correct observability.
- Brace-balanced JSON parser in `gemini_extract` — robust against Gemini markdown wrapping.
- Pydantic validation of extracted data before returning — correct schema enforcement at the boundary.
- Schema examples in the prompt are template-specific — reduces LLM hallucination rate.

### ⚠️ Issues Found

🔴 **High Priority**
- **API key in URL (line 219: `?key={key}`).** Same issue as `candidate_score.py` — Gemini API key in query string. Use `x-goog-api-key` header.
- **`tavily_search_snippets` (line 93) is dead code — never called anywhere.** `scourer.py` reimplements the same Tavily search-with-snippets logic in `_validate_hypothesis`. One of these must be deleted. If `tavily_search_snippets` is the canonical version, migrate `scourer.py` to call it and delete `_validate_hypothesis`. If `_validate_hypothesis` is preferred, delete `tavily_search_snippets`.
- **`return []` at the end of `tavily_search`, `tavily_search_snippets`, `tavily_extract` is unreachable dead code.** `reraise=True` in the tenacity policy means the last exception is re-raised when retries are exhausted. These silent empty returns mask what would otherwise be an explicit `RuntimeError`. Remove them — or change to `raise RuntimeError("Exhausted retries for ...")` to make the failure explicit.

🟡 **Medium Priority**
- **Authority domain check uses `"gov"` as a substring (line 182), not a domain suffix.** `any(x in lower_url for x in settings.primary_authority_domains)` where one entry is `"gov"` matches ANY URL containing `"gov"` — including `"government-agency.com"`, `"govtrack.us"`, `"shoppinggoverni.it"`. Change to domain-suffix matching: check `urlparse(u).netloc.endswith(".gov")` or use a proper domain comparison.
- **`gemini_extract` prompt truncates per-source to `src.raw_snippet[:5000]` (line 266).** With 5 sources × 5000 chars = 25000 chars, the prompt can exceed Gemini Flash's effective context for JSON generation. Limit total context: sum chars and stop adding sources once total exceeds 12000 chars.
- **Brace parser in `gemini_extract` (lines 313–333): if the brace loop ends without finding a balanced close**, `json_str` remains `raw_text.strip()` (set on line 309). `json.loads` on the full raw text might succeed on malformed JSON or fail with a confusing error rather than a clear "unbalanced JSON" message. Add explicit: `if brace_count != 0: raise ValueError(f"parse_failure: Unbalanced JSON in Gemini response")`.
- **`schema_examples` dict (lines 227–235) must be manually updated when a new template is added.** This duplicates knowledge already in `models.py`. Consider deriving the example from `TEMPLATE_ROW_MAP[template_name].model_fields`.

🟢 **Low Priority**
- `_get_retry_policy` is copy-pasted in `api_clients.py`, `scourer.py`, and `candidate_score.py` — three identical definitions. Move to `src/agents/core/retry.py` and import from there.

---

## 📄 `graph.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 30%  
**Verdict:** Clean LangGraph state machine with correct failure propagation, but state mutation inside a conditional edge function is an anti-pattern that risks stale failure state on retries.

### ✅ What's Good
- Short-circuit pattern in `node_scrape` and `node_extract` (`if state.get("failure_category"): return state`) — correct early termination.
- `should_retry_search` enforces max-retry cap (`if attempts < 2`) — prevents infinite search loops.
- Semantic query pivots (`_build_smart_query`) — intelligent retry strategy.
- Weak-context guard in `node_extract` (< 150 chars) — prevents wasting a Gemini API call on empty content.
- Explicit `failure_category` strings for structured error routing.

### ⚠️ Issues Found

🔴 **High Priority**
- **`should_retry_search` mutates `state` by calling `state.pop("failure_category", None)` (lines 232–233).** In LangGraph, conditional edge functions are routing functions — they should return a routing key, not modify state. Mutating state inside an edge function is not guaranteed to persist to the next node in all LangGraph implementations. The proper fix: clear `failure_category` inside `node_search` at the start of each invocation (since it's the node that sets it), not in the routing function.

🟡 **Medium Priority**
- **`_build_smart_query` defines pivots for attempts 0–4, but `should_retry_search` allows max 2 retries** (the `attempts < 2` guard). Pivots at `attempt == 3` and `attempt == 4` are dead code. Remove them.
- **`failure_category` values are plain strings** (`"search_failure"`, `"scrape_failure"`, etc.) — if a typo is introduced in any node, it silently bypasses the routing logic. Define as a `Literal` type or `Enum`:
  ```python
  FailureCategory = Literal["search_failure", "scrape_failure", "parse_failure", "schema_failure", "weak_context", "extraction_failure"]
  ```
- **`aiohttp.ClientSession` in `ExtractionState`** — if LangGraph checkpointing is ever enabled, `ClientSession` is not JSON-serializable and will cause serialization errors. Document this constraint explicitly in the docstring.

🟢 **Low Priority**
- `should_retry_search` log message says `"Retrying (Attempt %d/2)...", attempts + 1` — off-by-one in the display. When `attempts=0`, it shows "Attempt 1/2" but this is actually the first retry (second attempt overall). Reword: `"Search failed (attempt %d). Retrying...", attempts`.

---

## 📄 `runner.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 25%  
**Verdict:** Excellent orchestration with real fallback support and quality gates, but dataset/CSV writes are non-atomic and the shared session timeout creates an unfair time budget between best-fit and fallback attempts.

### ✅ What's Good
- Best-fit → fallback attempt cascade with independent isolated directories.
- Quality gate (`_validate_dataset_quality`) blocks low-signal datasets from propagating.
- `attempt_num` stored in metadata and restored on restart — correct idempotency.
- `set_template` called after success in auto-mode — locks in the template for downstream phases.
- `_write_data_manifest` correctly moved out of `JobManager` (SRP respected).
- Failure artifacts written per-attempt — excellent debuggability.

### ⚠️ Issues Found

🔴 **High Priority**
- **`json_path.write_text(dataset.model_dump_json(indent=2), ...)` at line 344 is NOT atomic.** A crash mid-write corrupts the dataset JSON. On restart, the idempotency check (line 237–240) catches the parse error and falls back to rerun — BUT the AuditTrail (`trail.save_to_file()`) at line 341 has already been written atomically. The audit trail and the dataset are now out of sync. Fix: write both atomically. Use `tempfile.mkstemp` → `os.replace` for the JSON write (same as `_write_data_manifest`).
- **`aiohttp.ClientTimeout(total=settings.api_timeout_seconds)` shared across ALL attempts (line 253).** If best-fit extraction uses 55 of 60 timeout seconds, the fallback has only 5 seconds. Each attempt should reset its own independent timeout. Fix: move the `aiohttp.ClientSession` creation inside the `for idx, attempt in enumerate(attempts)` loop, or create a separate `ClientTimeout` per attempt.

🟡 **Medium Priority**
- **`_write_csv` is not atomic (line 121).** CSV write uses `path.open("w", ...)` directly. A crash produces a truncated CSV. Fix: write to a temp file and `os.replace` to the final path.
- **Comment artifact `# BUG-C2:` on line 371** — development note that should be cleaned up before production.
- **`fail_artifact.write_text(...)` at lines 304, 327 is not atomic.** Low risk (it's a debug `.log` file), but inconsistent.

🟢 **Low Priority**
- `_validate_dataset_quality` calls `row.model_dump()` on every row (line 163) — full serialization to check nulls. For 10-row datasets this is negligible, but consider checking field values directly from the Pydantic model attributes.

---

## 📊 Overall Project Report — Expert Review

**Files Reviewed:** 8  
**Overall Quality Score:** 6/10  
**Overall Improvement Chance:** 35%  
**Verdict:** ❌ Not production-ready. One production-breaking bug (`candidate_score.py`) silently discards ALL Gemini-scored candidates. Multiple security issues (API key in URL), non-atomic writes, and a state mutation anti-pattern in LangGraph.

### Score Breakdown

| File | Score | Production Ready? |
|------|-------|-------------------|
| `archive_manager.py` | 6/10 | ⚠️ Concurrent-write unsafe |
| `candidate_score.py` | **4/10** | ❌ Breaking bug + security |
| `discovery_runner.py` | 6/10 | ⚠️ Non-atomic writes |
| `scourer.py` | 7/10 | ⚠️ Missing timeout |
| `api_clients.py` | 6/10 | ⚠️ Dead code + security |
| `graph.py` | 6/10 | ⚠️ Edge mutation anti-pattern |
| `runner.py` | 7/10 | ⚠️ Non-atomic dataset write |
| `__init__.py` ×2 | 8/10 | ✅ Clean |

### Common Issues (Across the Codebase)

- **API key in URL query string** — `candidate_score.py:267`, `discovery_runner.py:73`, `api_clients.py:219` — all three use `?key={key}` in Gemini URLs. Every Gemini consumer has this security issue.
- **Non-atomic file writes** — `discovery_runner.py:326` (candidates.json), `runner.py:344` (dataset.json), `runner.py:121` (CSV) — the codebase established the correct pattern in `archive_manager.py` and `job_manager.py` but didn't apply it consistently to output artifacts.
- **`_get_retry_policy` copy-pasted** in `api_clients.py`, `scourer.py`, `candidate_score.py` — three identical functions with slightly different parameters. Needs a shared `src/agents/core/retry.py`.

---

### 🔴 Critical Fixes (Do First)

1. **`candidate_score.py:194`** — Remove `.replace("_", "-")`. This single-line bug silently discards ALL Gemini-scored candidates and makes the entire scoring pipeline return empty results in production.
2. **`candidate_score.py:267`, `discovery_runner.py:73`, `api_clients.py:219`** — Move Gemini API key from URL to `x-goog-api-key` request header in all three files.
3. **`runner.py:344`** — Make dataset JSON write atomic (tempfile → os.replace). The current non-atomic write can desync the dataset from its already-written AuditTrail on crash.
4. **`runner.py:253`** — Move `aiohttp.ClientSession` timeout inside the per-attempt loop so best-fit and fallback each get a full independent `api_timeout_seconds` budget.
5. **`graph.py:232`** — Remove `state.pop(...)` from `should_retry_search`. Clear `failure_category` at the START of `node_search` instead, so state cleanup is owned by the node, not the edge function.

---

### 🟡 Important Improvements

1. **`archive_manager.py`** — Add a cross-process file lock (e.g., a `.lock` file) around the read→mutate→save cycle to prevent concurrent-process data loss.
2. **`discovery_runner.py:326`** — Make `candidates.json` write atomic (tempfile → os.replace) — consistent with the rest of the codebase.
3. **`discovery_runner.py` idempotency** — Include `niche_hint` + `top_n` in the cache key check so stale discovery results are not served when parameters change.
4. **`scourer.py`** — Enforce a timeout on Tavily calls in the discovery path (30s per hypothesis). Currently there is no timeout — a hanging request stalls all concurrent validations.
5. **`api_clients.py`** — Delete `tavily_search_snippets` (dead code). Consolidate with `scourer._validate_hypothesis` into a single canonical Tavily search+snippet function.
6. **`api_clients.py:182`** — Fix authority domain check to use domain-suffix matching instead of substring: `"gov"` substring incorrectly classifies `"government-agency.com"` as PRIMARY.
7. **`candidate_score.py:357`** — Pass `TokenBucketRateLimiter` as a parameter instead of creating a new one per call, so RPM is enforced across all scoring invocations in a session.

---

### 🟢 Nice to Have

1. **Move `_get_retry_policy`** to `src/agents/core/retry.py` — remove 3 copies from `api_clients.py`, `scourer.py`, `candidate_score.py`.
2. **`archive_manager.py`** — Add punctuation stripping to `normalize_topic` for more robust deduplication.
3. **`graph.py`** — Define `FailureCategory` as a `Literal` type for type-safe routing.
4. **`candidate_score.py`** — Move `norm = re.sub(...)` to call `ArchiveManager.normalize_topic()` instead of duplicating the logic.
5. **`api_clients.py` `schema_examples`** — Derive example rows from `TEMPLATE_ROW_MAP[template_name].model_fields` to auto-update when templates change.
6. **Cleanup dev artifacts** — `# ADD THIS BLOCK`, `# CHANGE raw_candidates`, `# BUG-C2:` comments in `discovery_runner.py` and `runner.py`.
