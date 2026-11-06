# Refactor Plan — `phase1_discovery/` + `phase1_extraction/`

**Target:** `src/agents/phase1_discovery/` + `src/agents/phase1_extraction/`  
**Source:** `CODE_REVIEW.md` (Expert Level, 2026-05-22)  
**Total Changes:** 20 refactors  
**Estimated Risk:** Medium (R-01 is critical/urgent; R-19 is highest structural risk)  
**Estimated Time:** ~5–8 hours total

---

## Refactor Summary Table

| ID | File | Type | Risk | Time |
|----|------|------|------|------|
| R-01 | `candidate_score.py` | Bug Fix — Breaking | **Critical** | 2 min |
| R-02 | 3 files | Security — API key | Low | 15 min |
| R-03 | `candidate_score.py` | Cleanup — import | Very Low | 2 min |
| R-04 | `candidate_score.py`, `discovery_runner.py` | Cleanup — dev artifacts | Very Low | 5 min |
| R-05 | `graph.py` | Bug Fix — state mutation | Low | 10 min |
| R-06 | `graph.py` | Cleanup — dead code | Very Low | 5 min |
| R-07 | `api_clients.py` | Cleanup — dead code | Low | 10 min |
| R-08 | `api_clients.py` | Bug Fix — brace parser | Low | 10 min |
| R-09 | `runner.py` | Bug Fix — atomic write | Low | 15 min |
| R-10 | `runner.py` | Bug Fix — atomic write | Low | 10 min |
| R-11 | `discovery_runner.py` | Bug Fix — atomic write | Low | 10 min |
| R-12 | `runner.py` | Bug Fix — timeout | Low | 15 min |
| R-13 | `discovery_runner.py` | Feature — retry | Low | 20 min |
| R-14 | `scourer.py` | Bug Fix — timeout | Low | 10 min |
| R-15 | `scourer.py` | Bug Fix — URL dedup | Very Low | 5 min |
| R-16 | `api_clients.py` | Bug Fix — domain check | Low | 10 min |
| R-17 | `candidate_score.py` | Bug Fix — temperature | Very Low | 3 min |
| R-18 | `src/agents/core/retry.py` | DRY — new file | Low | 20 min |
| R-19 | `archive_manager.py` | Architecture — file lock | Medium | 45 min |
| R-20 | `archive_manager.py` | Architecture — decouple | Low | 15 min |

---

## 🔴 High Priority (Do First)

---

### R-01: Fix `.replace("_", "-")` — Production-Breaking Template Name Bug

**Type:** Bug Fix — Breaking  
**Location:** `src/agents/phase1_discovery/candidate_score.py`, line 194

**Current Problem:**
```python
best_fit = str(data.get("best_fit_template", "")).strip().lower().replace("_", "-")
```
`VALID_TEMPLATES` uses underscores: `"bar_chart"`, `"butterfly_chart"`, etc. This conversion transforms every valid template name to `"bar-chart"`, `"butterfly-chart"` — which are NOT in `VALID_TEMPLATES`. The next line `if best_fit not in VALID_TEMPLATES: return None` then silently discards **every single scored candidate**. `score_candidates_batch` always returns `[]` in production.

**Solution:**
1. Open `src/agents/phase1_discovery/candidate_score.py`, line 194.
2. Replace:
   ```python
   best_fit = str(data.get("best_fit_template", "")).strip().lower().replace("_", "-")
   ```
   With:
   ```python
   best_fit = str(data.get("best_fit_template", "")).strip().lower()
   ```
3. That's the entire fix. One word removed.

**Risk:** Very Low — makes scoring work correctly. Before this fix, 0 candidates were returned.  
**Behavior Change:** Scoring pipeline now returns actual candidates instead of always returning empty list.

---

### R-02: Move Gemini API Key from URL to Header (Security Fix)

**Type:** Security — API Key Exposure  
**Location:** 3 files:
- `src/agents/phase1_discovery/candidate_score.py` — line 267
- `src/agents/phase1_discovery/discovery_runner.py` — line 73
- `src/agents/phase1_extraction/api_clients.py` — line 219

**Current Problem (same pattern in all 3):**
```python
key = settings.gemini_api_key.get_secret_value()
url = f"https://.../{model_name}:generateContent?key={key}"   # ← key in URL
...
async with session.post(url, json=payload) as resp:
```
The API key appears in:
- Server-side access logs of the Gemini endpoint
- Any HTTP proxy logs
- Exception tracebacks that include the URL (e.g., `aiohttp.ClientConnectorError`)

**Solution — Apply this change in each of the 3 files:**

**`candidate_score.py` (lines 264–292):**
```python
# Before
key = settings.gemini_api_key.get_secret_value()
model_name = settings.gemini_model
url = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{model_name}:generateContent?key={key}"
)
...
async with session.post(url, json=payload) as resp:

# After
key = settings.gemini_api_key.get_secret_value()
model_name = settings.gemini_model
url = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{model_name}:generateContent"
)
_gemini_headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
...
async with session.post(url, json=payload, headers=_gemini_headers) as resp:
```

Apply the **same change** to `discovery_runner.py` (lines 69–73) and `api_clients.py` (lines 217–219). The pattern is identical in all three.

**Risk:** Low — same request, different key placement. Gemini supports both URL-key and header-key.  
**Behavior Change:** API key no longer appears in logs or tracebacks. Functional behavior unchanged.

---

### R-03: Move `import re` to Top of `candidate_score.py`

**Type:** Cleanup — Misplaced Import  
**Location:** `src/agents/phase1_discovery/candidate_score.py`, line 117

**Current Problem:**
```python
# Line 117 — mid-module, after class definitions and function bodies
import re
```
`re` is already used on line 210 (`re.sub(...)`) — but the import is placed mid-file after the prompt template and helper functions. Static analyzers (mypy, ruff) flag this.

**Solution:**
1. Delete `import re` from line 117.
2. Add `import re` to the top-level imports block (after `import time`, before `from typing`).

**Risk:** Very Low — zero logic change.  
**Behavior Change:** None.

---

### R-04: Remove Dev Artifact Comments

**Type:** Cleanup — Dev Artifacts  
**Location:** Multiple files:
- `discovery_runner.py` line 184: `# ---------------- ADD THIS BLOCK ----------------`
- `discovery_runner.py` line 207: `# CHANGE raw_candidates to novel_raw_candidates here`
- `runner.py` line 371: `# BUG-C2: store exact number; never guess on re-run`
- `candidate_score.py` line 93: Typo `"actally"` → `"actually"` in prompt text
- `archive_manager.py` line 55: `# ADDED: Instantly clean up garbage when system starts`

**Solution:**
1. `discovery_runner.py:184` — Remove entire `# ---- ADD THIS BLOCK ----` comment line.
2. `discovery_runner.py:207` — Remove the `# CHANGE raw_candidates...` comment line.
3. `runner.py:371` — Shorten to just `# store exact number for idempotent restart`.
4. `candidate_score.py:93` — Fix `"actally"` → `"actually"` in the prompt string.
5. `archive_manager.py:55` — Remove `# ADDED:` prefix, keep the meaningful description.

**Risk:** Very Low. Comments only.  
**Behavior Change:** None.

---

### R-05: Fix `should_retry_search` — State Mutation in Edge Function

**Type:** Bug Fix — LangGraph Anti-Pattern  
**Location:** `src/agents/phase1_extraction/graph.py`, lines 224–243 and `node_search` function (lines 99–128)

**Current Problem:**
```python
def should_retry_search(state: ExtractionState) -> str:
    ...
    if not urls:
        if attempts < 2:
            state.pop("failure_category", None)   # ← WRONG: mutating state in edge function
            state.pop("failure_reason", None)
            return "search"
```
LangGraph edge functions are routing functions — their state modifications are not guaranteed to propagate to the next node across all LangGraph versions. The state cleanup should happen in the node itself, not the edge.

**Solution:**

**Step 1** — Add state cleanup at the START of `node_search` (after line 101):
```python
async def node_search(state: ExtractionState) -> ExtractionState:
    """Node: Discover relevant URLs on the web."""
    # Clear any stale failure state from a previous attempt before trying again
    state.pop("failure_category", None)
    state.pop("failure_reason", None)

    log = state["log"]
    session = state["session"]
    ...
```

**Step 2** — Remove the `state.pop(...)` calls from `should_retry_search` (lines 232–233):
```python
def should_retry_search(state: ExtractionState) -> str:
    urls = state.get("search_urls", [])
    attempts = state.get("query_attempts", 0)

    if not urls:
        if attempts < 2:
            state["log"].warning("Search yielded 0 URLs. Retrying (attempt %d/2)...", attempts)
            return "search"
        else:
            state["log"].error("Search yielded 0 URLs after 2 attempts. Aborting.")
            return END

    return "scrape"   # Success path — no need to pop state here either
```

**Risk:** Low — the functional behavior is the same, but now state cleanup is owned by the correct owner (the node).  
**Behavior Change:** None externally. Internally, `failure_category` is cleared at the right time.

---

### R-06: Remove Dead Query Pivots from `_build_smart_query`

**Type:** Cleanup — Dead Code  
**Location:** `src/agents/phase1_extraction/graph.py`, lines 87–96

**Current Problem:**
```python
elif attempt == 3:     # ← DEAD: should_retry_search allows max 2 retries
    return f"{topic} market share industry breakdown report"
elif attempt == 4:     # ← DEAD: never reached
    return f"{topic} comparison versus detailed metrics"
```
`should_retry_search` limits to `attempts < 2`, so `attempt` can only ever be 0, 1, or 2. Pivots at 3 and 4 are unreachable.

**Solution:**
Delete lines 87–96 (the `elif attempt == 3` and `elif attempt == 4` blocks). Keep only attempts 0, 1, 2.

```python
def _build_smart_query(topic: str, template_name: str, attempt: int = 0) -> str:
    if attempt == 0:
        # ... template-aware base queries ...
        return base_queries.get(template_name, f"{topic} latest statistics data facts")
    elif attempt == 1:
        return f"{topic} official report research statistics whitepaper"
    elif attempt == 2:
        return f"{topic} historical data trend timeline analysis"
    # Default fallback (should not be reached with current retry cap of 2)
    return f"{topic} deeper quantitative evidence facts"
```

**Risk:** Very Low — unreachable code removed.  
**Behavior Change:** None.

---

### R-07: Clean Up `api_clients.py` — Dead Code + Unreachable Returns

**Type:** Cleanup — Dead Code  
**Location:** `src/agents/phase1_extraction/api_clients.py`

**Current Problem — Part A: `tavily_search_snippets` (line 93) is never called.**
`scourer.py` has its own `_validate_hypothesis` which does the same Tavily search+snippet operation. `tavily_search_snippets` is dead code.

**Current Problem — Part B: `return []` after tenacity loops (lines 90, 139, 200) is unreachable.**
With `reraise=True`, tenacity re-raises the last exception when retries are exhausted. These `return []` lines can never execute — they mask what would be a real exception.

**Solution:**

**Part A** — Delete `tavily_search_snippets` function entirely (lines 93–139). This removes ~47 lines of duplicate code.

**Part B** — Replace `return []` with explicit `raise` at end of `tavily_search` and `tavily_extract`:
```python
# At end of tavily_search (currently line 90)
raise RuntimeError(f"tavily_search exhausted retries for query: {query!r}")

# At end of tavily_extract (currently line 200)
raise RuntimeError(f"tavily_extract exhausted retries for {len(urls)} URLs")
```

**Risk:** Low. Dead function deletion and unreachable code change.  
**Behavior Change:** If somehow reached (impossible with current config), a `RuntimeError` replaces a silent empty list — makes failures explicit.

---

### R-08: Fix Unbalanced JSON Brace Parser in `gemini_extract`

**Type:** Bug Fix — Error Handling  
**Location:** `src/agents/phase1_extraction/api_clients.py`, lines 305–339

**Current Problem:**
If Gemini returns malformed JSON where the brace parser loop ends without finding a balanced closing brace, `json_str` remains as `raw_text.strip()` (the full unmodified response). `json.loads` on the full text may then silently succeed on partial JSON or fail with a confusing "Expecting value" error rather than "Unbalanced braces".

**Solution — Add explicit check after the brace loop:**
```python
# After the brace-counting loop (after current line 333):
if brace_count != 0:
    raise ValueError(
        f"parse_failure: Unbalanced JSON braces in Gemini response "
        f"(open={brace_count}). First 200 chars: {raw_text[:200]!r}"
    )
```

**Risk:** Low — adds clarity to existing error path.  
**Behavior Change:** Unbalanced responses now raise a clear `ValueError("parse_failure: ...")` which the caller already handles (line 337).

---

### R-09: Make Dataset JSON Write Atomic in `runner.py`

**Type:** Bug Fix — Atomic Write  
**Location:** `src/agents/phase1_extraction/runner.py`, line 344

**Current Problem:**
```python
json_path.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
```
A crash mid-write produces a corrupt `_dataset.json`. The `AuditTrail` (line 341) has already been written atomically via `trail.save_to_file()` — a corrupt JSON leaves audit and dataset out of sync.

**Solution — Replace line 344:**
```python
# Atomic write: temp file → os.replace
_json_content = dataset.model_dump_json(indent=2)
_json_fd, _json_tmp = tempfile.mkstemp(dir=str(attempt_dir), suffix=".tmp")
try:
    with os.fdopen(_json_fd, "w", encoding="utf-8") as _f:
        _f.write(_json_content)
    os.replace(_json_tmp, str(json_path))
except BaseException:
    try:
        os.unlink(_json_tmp)
    except OSError:
        pass
    raise
```
Note: `tempfile` and `os` are already imported in `runner.py` (we added them in R-14 of the core refactor).

**Risk:** Low — same logic, crash-safe.  
**Behavior Change:** None on success. On crash, no corrupt partial file left behind.

---

### R-10: Make `_write_csv` Atomic in `runner.py`

**Type:** Bug Fix — Atomic Write  
**Location:** `src/agents/phase1_extraction/runner.py`, lines 120–136 (`_write_csv` function)

**Current Problem:**
```python
with path.open("w", newline="", encoding="utf-8") as f:
    # writes meta + CSV rows
```
A crash mid-write leaves a truncated CSV. The Manim renderer reads this CSV — a partial CSV would cause a render error.

**Solution — Replace the file open with a temp file pattern in `_write_csv`:**
```python
def _write_csv(dataset: TemplateDataset, path: Path, log: logging.Logger) -> None:
    """Export the TemplateDataset to CSV for the Manim engine (atomic write)."""
    if not dataset.rows:
        return

    # ... build combined_meta and headers as before ...

    # Write to temp file then atomically replace
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            # Write Meta Tags
            if dataset.template_name == "scan_race":
                for k, v in combined_meta.items():
                    f.write(f"#{k}={v}\n")
            else:
                if combined_meta:
                    meta_line = ", ".join(f"{k}={v}" for k, v in combined_meta.items())
                    f.write(f"# {meta_line}\n")
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in dataset.rows:
                writer.writerow(row.model_dump())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    log.info("Saved CSV tags and data to %s", path.name)
```

**Risk:** Low — same output, crash-safe.  
**Behavior Change:** None on success.

---

### R-11: Make `candidates.json` Write Atomic in `discovery_runner.py`

**Type:** Bug Fix — Atomic Write  
**Location:** `src/agents/phase1_discovery/discovery_runner.py`, line 326

**Current Problem:**
```python
candidates_path.write_text(
    batch.model_dump_json(indent=2),
    encoding="utf-8",
)
```
A crash mid-write leaves a corrupt `candidates.json`. Next run reads it, fails to parse, logs a warning, and reruns full discovery — wasting API calls.

**Solution — Replace lines 326–330:**
```python
# Atomic write of candidates.json
import os, tempfile
_batch_content = batch.model_dump_json(indent=2)
_batch_fd, _batch_tmp = tempfile.mkstemp(dir=str(output_dir), suffix=".tmp")
try:
    with os.fdopen(_batch_fd, "w", encoding="utf-8") as _f:
        _f.write(_batch_content)
    os.replace(_batch_tmp, str(candidates_path))
except BaseException:
    try:
        os.unlink(_batch_tmp)
    except OSError:
        pass
    raise
log.info("Saved candidates.json to %s", candidates_path)
```
Note: `os` and `tempfile` should be added to top-level imports of `discovery_runner.py` if not already present (they are NOT currently imported there).

**Risk:** Low — same logic, atomic.  
**Behavior Change:** None on success.

---

### R-12: Fix Shared Session Timeout Across Attempts in `runner.py`

**Type:** Bug Fix — Timeout Budget  
**Location:** `src/agents/phase1_extraction/runner.py`, line 253

**Current Problem:**
```python
timeout = aiohttp.ClientTimeout(total=settings.api_timeout_seconds)  # created once

async with aiohttp.ClientSession(timeout=timeout) as session:
    for idx, attempt in enumerate(attempts, 1):  # BOTH best_fit AND fallback share this
        ...
        final_state = await graph.ainvoke(initial_state)
```
If best-fit extraction runs for 58 of 60 timeout seconds, the fallback gets only 2 seconds — it cannot even complete a search.

**Solution — Move session creation inside the attempt loop:**
```python
last_error = "Unknown error"

with timed_operation(log, step_name, topic=topic):
    for idx, attempt in enumerate(attempts, 1):
        t_name = attempt["template"]
        t_type = attempt["type"]

        log.info("--- Starting Extraction Attempt %d/%d (%s: %s) ---", ...)

        # Each attempt gets its own FULL timeout budget
        timeout = aiohttp.ClientTimeout(total=settings.api_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # ... rest of attempt logic unchanged ...
```

**Risk:** Low — each attempt now creates its own session. `aiohttp.ClientSession` creation is cheap. The session is closed at the end of each attempt which is correct — no shared state between attempts.  
**Behavior Change:** Fallback attempt now gets the full `api_timeout_seconds` budget, not the leftover.

---

### R-13: Add Retry to `_ideate_hypotheses` in `discovery_runner.py`

**Type:** Feature — Resilience  
**Location:** `src/agents/phase1_discovery/discovery_runner.py`, lines 88–114

**Current Problem:**
```python
try:
    ...
    async with session.post(url, json=payload) as resp:
        ...
except Exception as e:
    log.warning("Failed to ideate hypotheses: %s", e)
    return []
```
A single transient Gemini failure (503, timeout, DNS blip) silently returns `[]`, causing the runner to fall back to 3 hardcoded generic topics like `"Business revenue comparisons"`.

**Solution — Add tenacity retry wrapper:**

**Step 1** — Add import at top of `discovery_runner.py`:
```python
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
```

**Step 2** — Wrap the HTTP call with the retry policy:
```python
async def _ideate_hypotheses(
    niche_hint: str | None,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> list[str]:
    """Use Gemini to brainstorm novel topic ideas before we search the web."""
    key = settings.gemini_api_key.get_secret_value()
    model_name = settings.gemini_model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"    # ← key moved to header (from R-02)
    )
    _headers = {"x-goog-api-key": key}
    ...

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
            reraise=True,
        ):
            with attempt:
                t0 = time.perf_counter()
                async with session.post(url, json=payload, headers=_headers) as resp:
                    elapsed = (time.perf_counter() - t0) * 1000
                    log_api_call(log, service="gemini.ideate", status_code=resp.status,
                                 retry_count=attempt.retry_state.attempt_number - 1,
                                 duration_ms=elapsed)
                    resp.raise_for_status()
                    data = await resp.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
                    if match:
                        raw_text = match.group(0)
                    ideas = json.loads(raw_text)
                    if isinstance(ideas, list) and all(isinstance(x, str) for x in ideas):
                        return [x.strip() for x in ideas if x.strip()]
                    return []
    except Exception as e:
        log.warning("Failed to ideate hypotheses after retries: %s", e)
        return []
```

Also add `import asyncio` if not already imported in `discovery_runner.py`.

**Risk:** Low — wraps existing call in retry. `return []` fallback is still there for total failure.  
**Behavior Change:** Transient Gemini errors now retry up to 3× before falling back to defaults.

---

## 🟡 Medium Priority

---

### R-14: Add Timeout to Tavily Calls in `scourer.py` (Discovery Path)

**Type:** Bug Fix — Missing Timeout  
**Location:** `src/agents/phase1_discovery/scourer.py`

**Current Problem:**
`scourer.py` is called from `discovery_runner.py` which creates no `aiohttp.ClientSession` timeout. A hanging Tavily request blocks the semaphore slot indefinitely — stalling all concurrent hypothesis validations.

**Solution — Add a default timeout to `fetch_raw_candidates` and enforce it:**

```python
async def fetch_raw_candidates(
    hypotheses: list[str],
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_per_bucket: int = 4,
    max_concurrency: int = 5,
    request_timeout_seconds: float = 30.0,   # NEW param
) -> list[dict[str, Any]]:
```

Inside `_validate_hypothesis`, wrap the session call with `asyncio.timeout` or pass a per-request timeout:
```python
async def _validate_hypothesis(
    hypothesis: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_results: int = 4,
    request_timeout: float = 30.0,    # NEW
) -> dict[str, Any] | None:
    ...
    async for attempt in _get_retry_policy():
        with attempt:
            try:
                async with asyncio.timeout(request_timeout):   # Python 3.11+
                    async with session.post(url, json=payload) as resp:
                        ...
            except asyncio.TimeoutError:
                log.warning("Tavily request timed out for '%s'", hypothesis)
                raise   # let tenacity retry
```
For Python 3.10 compatibility, use `asyncio.wait_for(session.post(...), timeout=request_timeout)` instead.

**Risk:** Low — backward-compatible new param with default. Existing callers unchanged.  
**Behavior Change:** Hanging Tavily requests now fail after 30s and retry, rather than hanging forever.

---

### R-15: Fix URL Order Preservation in `scourer.py`

**Type:** Bug Fix — URL Dedup  
**Location:** `src/agents/phase1_discovery/scourer.py`, line 101

**Current Problem:**
```python
"source_urls": list(set(urls)),
```
Converting to set destroys insertion order. Tavily returns results ranked by relevance — high-authority URLs appear first. Randomizing order means they may be scraped last (or skipped if the list is truncated).

**Solution — Replace line 101:**
```python
"source_urls": list(dict.fromkeys(urls)),   # deduplicate while preserving insertion order
```

**Risk:** Very Low — one-word change.  
**Behavior Change:** Same URLs, same deduplication, original order preserved.

---

### R-16: Fix Authority Domain Check — Substring to Suffix Matching

**Type:** Bug Fix — Incorrect Heuristic  
**Location:** `src/agents/phase1_extraction/api_clients.py`, line 182

**Current Problem:**
```python
if any(x in lower_url for x in settings.primary_authority_domains):
```
`primary_authority_domains` includes `"gov"` as a plain string. `"gov" in "government-agency.com"` → `True` — misclassifies commercial sites as PRIMARY.

**Solution — Replace lines 180–185:**
```python
from urllib.parse import urlparse   # Add to imports if not already there

# In tavily_extract:
parsed_url = urlparse(u)
netloc = parsed_url.netloc.lower()

tier = AuthorityTier.SECONDARY
if any(netloc == d or netloc.endswith(f".{d}") 
       for d in settings.primary_authority_domains):
    tier = AuthorityTier.PRIMARY
elif any(netloc == d or netloc.endswith(f".{d}") 
         for d in settings.social_authority_domains):
    tier = AuthorityTier.SOCIAL
```
This ensures `"gov"` only matches domains like `cdc.gov`, `un.org`, `data.gov` — not `government-agency.com`.

**Risk:** Low — heuristic improvement. Some previously-PRIMARY sites may now be SECONDARY (more accurate).  
**Behavior Change:** Authority tier classification becomes more accurate.

---

### R-17: Use `settings.gemini_temperature` in `score_single_candidate`

**Type:** Bug Fix — Inconsistency  
**Location:** `src/agents/phase1_discovery/candidate_score.py`, line 284

**Current Problem:**
```python
"generationConfig": {
    "responseMimeType": "application/json",
    "temperature": 0.1,   # ← hardcoded, ignores settings
    "maxOutputTokens": 1000,
},
```
`gemini_extract` in `api_clients.py` uses `settings.gemini_temperature`. Scoring uses 0.1 always.

**Solution — Replace `"temperature": 0.1` with:**
```python
"temperature": settings.gemini_temperature,
```

**Risk:** Very Low — uses the same value as current default (0.1), just from settings.  
**Behavior Change:** Temperature is now configurable via `GEMINI_TEMPERATURE` env var for scoring too.

---

## 🟢 Low Priority

---

### R-18: Create `src/agents/core/retry.py` — Consolidate Retry Policy

**Type:** DRY — New Shared Module  
**Location:** New file: `src/agents/core/retry.py`  
**Consumers:** `api_clients.py`, `scourer.py`, `candidate_score.py`

**Current Problem:**
`_get_retry_policy()` is defined 3× with slightly different parameters:
- `api_clients.py`: `stop=3, min=2, max=10`
- `scourer.py`: `stop=3, min=1, max=5`
- `candidate_score.py`: `stop=3, min=2, max=10` (inner policy)
- `candidate_score.py`: `stop=3, min=60, max=120` (429-specific policy)

**Solution:**

**Step 1 — Create `src/agents/core/retry.py`:**
```python
"""
AutoShorts Core — Shared Tenacity Retry Policies
=================================================
Centralised retry factories so every HTTP consumer uses a consistent policy.
"""
from __future__ import annotations
import asyncio
import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential


def standard_retry_policy(*, min_wait: float = 2, max_wait: float = 10) -> AsyncRetrying:
    """3-attempt exponential backoff for transient HTTP/network errors."""
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )


def rate_limit_retry_policy() -> AsyncRetrying:
    """3-attempt retry with 60–120s backoff for Gemini HTTP 429 responses."""
    from src.agents.phase1_discovery.candidate_score import GeminiRateLimitError
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=60, min=60, max=120),
        retry=retry_if_exception_type(GeminiRateLimitError),
        reraise=True,
    )
```

**Step 2 — Update each consumer:**
- `api_clients.py`: Replace `_get_retry_policy()` definition with `from src.agents.core.retry import standard_retry_policy`
- `scourer.py`: Same import; use `standard_retry_policy(min_wait=1, max_wait=5)` for current behavior
- `candidate_score.py`: Import both policies

**Risk:** Low — same retry logic, just shared. Do after all other refactors are stable.  
**Behavior Change:** None.

---

### R-19: Decouple `expire_stale_entries()` from `ArchiveManager.__init__`

**Type:** Architecture — Decouple  
**Location:** `src/agents/phase1_discovery/archive_manager.py`, line 55

**Current Problem:**
```python
def __init__(self, archive_path: Path | None = None) -> None:
    ...
    self._load()
    self.expire_stale_entries()   # ← triggers _save() on every constructor call
```
Every `ArchiveManager()` instantiation potentially writes to disk. The discovery runner creates one per run.

**Solution:**

**Step 1** — Remove `self.expire_stale_entries()` from `__init__`:
```python
def __init__(self, archive_path: Path | None = None) -> None:
    ...
    self._load()
    # NOTE: expire_stale_entries() is NOT called here.
    # Call it explicitly at session start via run_discovery or CLI.
```

**Step 2** — In `discovery_runner.py`, make the expiry call explicit (it's already there at line 161):
```python
archive = ArchiveManager()
archive.expire_stale_entries()   # ← already explicit, this call stays
```

The behavior is identical — expiry still happens at session start. The difference: constructing `ArchiveManager` for read-only checks no longer triggers a write.

**Risk:** Low — expiry still called at the same point in `run_discovery`. Any other callers that need expiry must now call it explicitly.  
**Behavior Change:** `ArchiveManager()` construction no longer writes to disk unless expired entries exist AND the caller explicitly calls `expire_stale_entries()`.

---

### R-20: Add Cross-Process File Lock to `ArchiveManager._save()`

**Type:** Architecture — Concurrency Safety  
**Location:** `src/agents/phase1_discovery/archive_manager.py`, `_save()` method (lines 309–338)

**Current Problem:**
Two simultaneous CLI processes both load the archive, both mutate in memory, and both call `_save()`. The atomic write prevents corruption, but the last writer's changes overwrite the first writer's changes.

**Solution — Use a `.lock` file for cross-process exclusive access:**

```python
import fcntl   # POSIX only; for Windows use msvcrt

def _save(self) -> None:
    """Persist archive to disk using an atomic write with cross-process locking."""
    lock_path = self._archive_path.with_suffix(".lock")

    # Acquire exclusive advisory lock before read-mutate-write
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)   # blocks until lock acquired
        
        # Re-read from disk to pick up any changes made by the other process
        # while we were waiting for the lock
        self._load()
        
        payload: dict[str, Any] = {
            "produced": {k: v.model_dump(mode="json") for k, v in self._produced.items()},
            "rejected": {k: v.model_dump(mode="json") for k, v in self._rejected.items()},
            "saved_queue": [q.model_dump(mode="json") for q in self._saved_queue],
        }

        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._archive_path.parent), suffix=".tmp", prefix=".archive_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(self._archive_path))
        except BaseException as e:
            logger.error("Atomic save of archive failed: %s", e)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
```

For Windows compatibility, add a platform check:
```python
import sys
if sys.platform == "win32":
    import msvcrt
    # ... use msvcrt.locking instead
```

**Risk:** Medium — introduces cross-process synchronization. On Windows, `fcntl` is not available. Test with concurrent processes before merging.  
**Behavior Change:** Concurrent writes are now serialized — no more silent data loss.

---

## 📋 Execution Order

Do refactors **in this order** — each should be a separate commit:

```
Group 1 — CRITICAL: Must fix immediately (zero-risk, max impact)
  1.  R-01  — Fix .replace("_", "-") in candidate_score.py   ← DO THIS FIRST
  2.  R-03  — Move import re to top of candidate_score.py
  3.  R-04  — Remove dev artifact comments + fix typo
  4.  R-06  — Remove dead query pivots from graph.py

Group 2 — Security + Dead code (isolated, safe)
  5.  R-02  — API key → x-goog-api-key header (all 3 files)
  6.  R-07  — Delete tavily_search_snippets + remove unreachable returns
  7.  R-17  — Use settings.gemini_temperature in candidate_score

Group 3 — Bug fixes (behavior improving, no API change)
  8.  R-05  — Fix state mutation in should_retry_search
  9.  R-08  — Add unbalanced brace check in gemini_extract
  10. R-15  — dict.fromkeys(urls) in scourer.py
  11. R-16  — Fix authority domain suffix matching

Group 4 — Atomic write fixes (same logic, crash-safe)
  12. R-09  — Atomic JSON write in runner.py
  13. R-10  — Atomic CSV write in runner.py (_write_csv)
  14. R-11  — Atomic candidates.json write in discovery_runner.py

Group 5 — Resilience additions (new params, backward compatible)
  15. R-12  — Fix ClientSession per-attempt timeout in runner.py
  16. R-13  — Add retry to _ideate_hypotheses in discovery_runner.py
  17. R-14  — Add timeout to Tavily calls in scourer.py

Group 6 — Architecture (do after all above are stable)
  18. R-18  — Create src/agents/core/retry.py + consolidate 3 copies
  19. R-19  — Decouple expire_stale_entries from __init__
  20. R-20  — Add cross-process file lock to ArchiveManager._save()
```

**Logic behind the order:**
- R-01 first: production is broken without it — zero cost to fix
- R-02 before R-13: `_ideate_hypotheses` retry (R-13) uses the header pattern from R-02
- R-07 before R-18: delete dead code before consolidating retry policies
- R-09/R-10/R-11 together: all atomic write fixes, same pattern, same commit
- R-18 last in Group 6: consolidates 3 files — needs all bugs fixed in callers first
- R-20 last overall: cross-process locking is the riskiest structural change

---

## 🛡️ Risk Assessment

| Change | Risk | What Can Break | Mitigation |
|--------|------|----------------|------------|
| R-01 | **Zero** | Nothing — fixes broken behavior | Single line change |
| R-02 | Low | Gemini auth if header not supported | Test with real API key |
| R-03 | Zero | Nothing | — |
| R-04 | Zero | Nothing | — |
| R-05 | Low | LangGraph state if version-specific | Test extraction graph end-to-end |
| R-06 | Zero | Nothing | — |
| R-07 | Low | Any hidden caller of tavily_search_snippets | `Select-String -Recurse -Pattern "tavily_search_snippets" src/` |
| R-08 | Low | Error handling path only | — |
| R-09 | Low | Nothing (same output) | Verify dataset file exists and parses after |
| R-10 | Low | Nothing (same output) | Verify CSV readable after |
| R-11 | Low | Nothing (same output) | Verify candidates.json parses after |
| R-12 | Low | Session creation overhead | Minimal — ClientSession is cheap |
| R-13 | Low | Nothing — additive | — |
| R-14 | Low | Nothing — additive param | — |
| R-15 | Zero | Nothing | — |
| R-16 | Low | Tier classification changes for some URLs | Review classified URLs in test runs |
| R-17 | Zero | Nothing — same value as default | — |
| R-18 | Low | Import paths if retry policy params differ | Check all 3 callers use correct params |
| R-19 | Low | Any caller that relied on expiry at construction | `Select-String -Recurse -Pattern "ArchiveManager()" src/` |
| R-20 | Medium | POSIX-only (`fcntl`); Windows needs `msvcrt` | Platform check + test concurrently |

**Overall Risk:** Medium (R-20 is the only genuinely risky change)  
**Recommendation:** Feature branch per group. Merge Group 1 immediately (critical fix). Groups 2–4 can be merged together after review. Groups 5–6 should have dedicated PRs.

---

## 🚧 Scope — What Will NOT Change

- **Scoring algorithm logic** — weights, formulas, ideation-first vs legacy branch unchanged
- **LangGraph graph topology** — nodes and edges remain the same (R-05 only moves cleanup within existing node)
- **Archive TTL values** — PRODUCED_TTL_DAYS, REJECTED_TTL_DAYS unchanged
- **Pydantic model schemas** — DiscoveryBatch, TopicCandidate, SourceAudit field definitions unchanged
- **`_ideate_hypotheses` output format** — still returns `list[str]`, fallback topics unchanged
- **Phase 1A → Phase 1B handoff contract** — `candidates.json` schema, `run_discovery` return type unchanged
- **Files NOT touched:** `archive_manager._migrate_entries`, `_migrate_queue`, `run_extraction` core loop logic, `node_scrape`, `node_extract` behavior, `_validate_dataset_quality`, `_build_template_spec`

---

## ✅ Verify

**After R-01 (critical — verify scoring pipeline works):**
```powershell
python -c "
from src.agents.phase1_discovery.candidate_score import _parse_scoring_response
import json

# Simulate what Gemini returns
fake_raw = json.dumps({
    'hook_potential_score': 8,
    'novelty_score': 7,
    'visual_fit_score': 9,
    'data_feasibility_score': 8,
    'freshness_score': 7,
    'best_fit_template': 'bar_chart',
    'fit_reason': 'Rankings map perfectly',
    'source_hint': 'statista.com',
    'rationale': 'High interest data'
})
result = _parse_scoring_response(fake_raw, 'Top AI Companies', 'some snippet')
if result is None:
    print('FAIL: still returning None (bug not fixed)')
else:
    print(f'PASS: got candidate with template={result.best_fit_template}, score={result.final_score}')
"
```
Expected: `PASS: got candidate with template=bar_chart, score=...`

**After R-02 (API key in header):**
```powershell
python -c "
import ast, sys
with open('src/agents/phase1_discovery/candidate_score.py') as f:
    content = f.read()
if '?key=' in content:
    print('FAIL: API key still in URL')
else:
    print('PASS: No API key in URL query string')
"
```
Expected: `PASS`

**After R-07 (dead code removed):**
```powershell
Select-String -Recurse -Pattern "tavily_search_snippets" src/
```
Expected: Zero matches.

**After R-09/R-10/R-11 (atomic writes — compile check):**
```powershell
.venv\Scripts\python.exe -m py_compile src/agents/phase1_extraction/runner.py
.venv\Scripts\python.exe -m py_compile src/agents/phase1_discovery/discovery_runner.py
```
Expected: No output (no errors).

**Full test suite after each group:**
```powershell
.venv\Scripts\python.exe -m pytest tests/phase1 -v --tb=short 2>&1 | Select-Object -Last 10
```
Expected: 20 passed, 1 pre-existing failure (`test_discovery_runner.py::test_run_discovery_writes_candidates_json` — pre-existing `fallback_template='line_chart'` fixture bug, unrelated to our changes).
