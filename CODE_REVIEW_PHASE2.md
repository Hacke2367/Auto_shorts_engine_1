# Code Review — `src/agents/phase2_scripting/`

**Level:** Expert  
**Date:** 2026-05-25  
**Reviewer:** Claude Code  
**Files Reviewed:** 5 (`contracts.py`, `timing.py`, `xml_parser.py`, `llm_writer.py`, `runner.py`)

---

## 📄 `contracts.py` — Expert Review

**Code Quality:** 8/10  
**Improvement Chance:** 15%  
**Verdict:** Solid foundation — clean exception hierarchy, well-modelled data contracts. Minor dead code and typing anachronisms.

### ✅ What's Good
- Exception hierarchy (`ScriptParsingError`, `ScriptValidationError`, `ScriptGenerationError`) clearly expresses the failure modes.
- `normalize_text` and `count_chars` are correctly isolated as shared helpers; both callers use them consistently.
- Pydantic models are typed cleanly with good field names.

### ⚠️ Issues Found

🟡 Medium Priority
- **`ScriptValidationError` is defined but never raised or imported anywhere.** It's dead code at the contract level — creates a misleading public API surface. Either remove it, or use it in `xml_parser.py` for length violations (currently `ScriptParsingError` is overloaded for both structural and validation failures).
- **`SegmentSpec.required` field always defaults to `True` and is never checked.** In `xml_parser.py`, all tags in the plan are treated as required unconditionally. The field has no effect — either enforce it in the parser or remove it to avoid misleading future maintainers.

🟢 Low Priority
- **`List` and `Optional` imported from `typing` module** — Python 3.10+ supports `list[...]` and `X | None` natively. The rest of the pipeline files use `from __future__ import annotations`; this file does not, creating an inconsistency.
- **`ScriptPayload` has no `created_at` timestamp.** When debugging a stale cache hit, there is no way to know when the script was generated without checking the file's `mtime`.

---

## 📄 `timing.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 35%  
**Verdict:** Core math is correct, but the function is too long, the markdown parser is fragile, and tag prefix expansion has silent edge-case bugs.

### ✅ What's Good
- CPS resolution (`global_cps → persona_cps`) with sane fallback hierarchy is well-designed.
- Separating `_load_visual_rules` into its own function is good SRP practice.
- `_load_yaml` raises a clear `FileNotFoundError` for missing mandatory files.

### ⚠️ Issues Found

🔴 High Priority
- **`_load_visual_rules` uses a bespoke, fragile markdown parser** (`timing.py`, lines 151–173). It splits on `:` to extract key-value pairs — meaning any description containing `:` (e.g. `HOOK: "Revenue grew 47%: here's why"`) will be silently truncated at the first colon, injecting corrupted visual rules into the LLM prompt with no warning. Move visual rules to a proper YAML file.
- **`prefix = raw_tag.split("_")[0]` is incorrect for multi-part dynamic tags** (`timing.py`, line 87). For a tag like `ITEM_VALUE_1..ITEM_VALUE_N`, `split("_")[0]` returns `"ITEM"` not `"ITEM_VALUE"`, so the timing lookup will fail with a misleading `ValueError`. The expansion logic assumes a single-word prefix which is an undocumented, fragile constraint.

🟡 Medium Priority
- **`build_segment_plan` is 95 lines long and does loading, expansion, and segment construction** — violates SRP. Extracting `_expand_tags(raw_order, dataset)` and `_build_segment_spec(tag, idx, timings, cps, visual_rules)` would make each unit independently testable.
- **`".._N" in raw_tag or "_1.." in raw_tag` substring detection** (`timing.py`, line 85) is fragile. A tag like `"FINAL_1..10"` would match `"_1.."` and be incorrectly treated as dynamic. Use a precise regex like `r"^[A-Z]+_\d+\.\.[A-Z]+_N$"` instead.
- **3 YAML files are loaded from disk on every `build_segment_plan` call** with no caching. For a single-job pipeline this is acceptable, but if the function is called more than once per process, these are redundant I/O hits. Use `functools.lru_cache` on the loaders or pass them in as dependencies.

🟢 Low Priority
- **`_load_yaml` returns `data or {}` silently** — if a YAML file is syntactically valid but empty, callers get an empty dict and the first key access raises `KeyError` deep inside the function rather than a clear validation error at load time.

---

## 📄 `xml_parser.py` — Expert Review

**Code Quality:** 7/10  
**Improvement Chance:** 25%  
**Verdict:** Structural validation logic is thorough and well-reasoned. Greedy regex and O(n²) lookup are correctness/performance concerns; import-inside-function is sloppy.

### ✅ What's Good
- Five distinct structural rules (missing, extra, duplicate, ordering, empty) are checked cleanly and each raises a descriptive `ScriptParsingError` with the specific tags named.
- Separation of structural parsing from length validation is architecturally correct — it lets `llm_writer.py` retry only failing segments.
- `normalize_text` is applied at parse time, so all downstream consumers work with canonical text.

### ⚠️ Issues Found

🔴 High Priority
- **`<MONOLOGUE>` wrapper regex is greedy** (`xml_parser.py`, line 37): `r"<MONOLOGUE>(.*)</MONOLOGUE>"` with `re.DOTALL`. If the LLM produces two `<MONOLOGUE>` blocks (which happens on malformed retries), the greedy `.*` captures from the first open tag to the *last* closing tag, merging two generations into one. Use `r"<MONOLOGUE>(.*?)</MONOLOGUE>"` (non-greedy) or a brace-counter approach.

🟡 Medium Priority
- **`re.IGNORECASE` on line 37 for the wrapper but `[A-Z0-9_]+` on line 46 for inner tags** — the outer wrapper tolerates `<monologue>` but inner tags like `<hook>` or `<Hook>` are silently invisible to the extractor. The parser raises "No valid XML tags found" instead of "Found lowercase tag `hook`". Add `re.IGNORECASE` to the inner tag pattern and uppercase the captured name.
- **`expected_tags.index(spec.tag)` inside `for spec in plan.segments` loop** (`xml_parser.py`, line 86) — `list.index()` is O(n); inside an O(n) loop this is O(n²). Since ordering is already validated to be exactly correct, replace with `for i, spec in enumerate(plan.segments): _, text = found_elements[i]` — O(n) and simpler.
- **`from collections import Counter` inside the function body** (`xml_parser.py`, line 74). Module-level imports are a Python convention; import-inside-function adds hidden overhead on every invocation and obscures dependencies.

🟢 Low Priority
- **No handling of self-closing tags or unclosed tags** — `<HOOK/>` or `<HOOK>text without close` both silently result in "No valid XML tags found" rather than a specific error message. A pre-check `if re.search(r"<[A-Z0-9_]+/>", mono_content)` could give a better error.

---

## 📄 `llm_writer.py` — Expert Review

**Code Quality:** 5/10  
**Improvement Chance:** 45%  
**Verdict:** Not production-ready. API key leaked in URL, generic Exception bypasses retry machinery, system prompt directory path contradicts `runner.py`, and partial segment failures are silently accepted.

### ✅ What's Good
- Two-layer retry strategy (429-aware outer + transient-error inner) is correct and mirrors Phase 1's pattern.
- `_build_rewrite_prompt` targeting only failing segments is a smart, cost-efficient design.
- `_get_failing_segments` cleanly separates the "what failed" query from the retry orchestration.
- Visual rules are injected into both the initial and rewrite prompts, giving the LLM spatial awareness on every attempt.

### ⚠️ Issues Found

🔴 High Priority
- **API key exposed in URL** (`llm_writer.py`, line 189): `url = f"...generateContent?key={key}"`. The API key appears in server-side access logs, proxy logs, and any exception traceback that includes the URL. Phase 1 files were fixed with R-02 (move key to `x-goog-api-key` header). This file was missed. Fix: same pattern as R-02.
  ```python
  url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
  headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
  # then: session.post(url, json=payload, headers=headers)
  ```

- **`SYSTEM_PROMPTS_DIR = PERSONAS_DIR / "system_prompt"` (singular) contradicts `runner.py:170`** which hashes `personas_dir / "system_prompts"` (plural). One of these paths does not exist. If the hash uses `system_prompts/` but `_build_system_prompt` reads from `system_prompt/`, the hash is computed from a *different* file than what gets sent to Gemini — cache invalidation breaks silently. Unify to one canonical path.

- **`raise Exception(...)` on a malformed Gemini response** (`llm_writer.py`, line 222). The outer `_get_retry_policy()` only retries `aiohttp.ClientError` and `asyncio.TimeoutError`. A generic `Exception` bypasses this entirely and propagates directly to `write_script` where it is uncaught, crashing Phase 2 on the first malformed response with no retry. Use `raise ScriptGenerationError(...)` so the caller can handle it properly.

🟡 Medium Priority
- **`_run_rewrite_loop` returns `bool` but does not communicate which segments are still failing** (`llm_writer.py`, line 336). When the rewrite loop returns `False`, `write_script` calls `log.warning("Rewrite loop exhausted; retrying full monologue.")` — but immediately after (on the next `for attempt` iteration), it does `for seg in parsed: final_segments[seg.tag] = seg` which overwrites the partially-fixed `final_segments`. The out-of-bounds segments from the failed rewrite are silently accepted if the next full generation also fails length checks. The final `_order_segments` call on line 336 after a successful rewrite returns whatever is in `final_segments`, which may still have segments violating their limits. Consider returning `(bool, remaining_failing)` from `_run_rewrite_loop`.

- **`"temperature": 0.3` is hardcoded** (`llm_writer.py`, line 194). Every other Gemini call in the codebase reads from `settings.gemini_temperature`. The scripting engine is the only exception — it cannot be tuned via env var without a code change.

- **f-strings used in all logging calls** (`llm_writer.py`, lines 262, 281, 307, 314, 324, 338). The codebase convention is `%s` lazy formatting. F-strings evaluate eagerly, building the string even when the log level is disabled. Use `log.info("--- Full Monologue Generation (Attempt %d/%d) ---", attempt + 1, max_full_retries + 1)` etc.

🟢 Low Priority
- **`full_generation_history` string grows unboundedly in memory** (`llm_writer.py`, line 309). With 3 full retries × large LLM outputs, this could reach several MB before being written to disk. Use `io.StringIO` and write incrementally, or simply write each attempt's raw output to `llm_raw_{attempt}.txt` separately.

---

## 📄 `runner.py` — Expert Review

**Code Quality:** 6/10  
**Improvement Chance:** 30%  
**Verdict:** Hash-based caching and pre-flight validation are well-designed. Non-atomic writes and a dev artifact comment left in, plus a module logger that's never used.

### ✅ What's Good
- `_build_inputs_hash` correctly fingerprints all inputs: dataset file, context YAMLs, persona files, engine version. Cache invalidation is deterministic and thorough.
- `_get_dataset_path` manifest-first → filesystem fallback pattern is robust.
- `_validate_phase2_inputs` gives early, specific failure messages before any LLM work begins.
- `_resolve_phase1_template` tries multiple step-name variants, tolerating minor naming drift.

### ⚠️ Issues Found

🔴 High Priority
- **`script_json_path.write_text(...)` is not atomic** (`runner.py`, line 245). A crash mid-write corrupts `script.json`. On the next run, the cache check at line 221 reads the corrupted file, fails to parse it, logs a warning, and regenerates — wasting an LLM call and potentially diverging from the first attempt. Apply the same `tempfile.mkstemp → os.replace` pattern used in Phase 1 (R-09):
  ```python
  _content = payload.model_dump_json(indent=2)
  fd, tmp = tempfile.mkstemp(dir=str(script_dir), suffix=".tmp")
  try:
      with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(_content)
      os.replace(tmp, str(script_json_path))
  except BaseException:
      try: os.unlink(tmp)
      except OSError: pass
      raise
  ```
  `os` and `tempfile` are not imported in `runner.py` — add them.

- **`llm_raw.txt` write is also not atomic** (`runner.py`, line 246): same issue. If the process dies between writing `script.json` and `llm_raw.txt`, the audit file is missing but the script file exists, making the audit incomplete.

🟡 Medium Priority
- **`# BUG-C5:` dev artifact comment** (`runner.py`, line 202). This is the same category of dev comment cleaned up by R-04 in Phase 1. Replace with: `# Validate all Phase 1B outputs are present before any LLM work begins.`

- **`log.info(f"Starting Phase 2...")` and `log.info(f"Phase 2 inputs hash: {inputs_hash}")`** (`runner.py`, lines 200, 214) — f-strings in logging. Use `%s` format for consistency and to avoid eager evaluation.

- **Module-level `logger = logging.getLogger(__name__)` is never used** (`runner.py`, line 24). All actual logging goes through `log = job_manager.get_logger()`. The module logger either should be used as a fallback for module-level functions (e.g. `_get_dataset_path`, `_validate_phase2_inputs`) or removed. Currently those helper functions receive a `log` parameter — module logger is truly dead.

🟢 Low Priority
- **`_load_dataset` does not catch `json.JSONDecodeError`** (`runner.py`, line 179). A corrupt `*_dataset.json` produces a raw `json.JSONDecodeError` propagating to `run_scripting` caller with no context about which file failed. Wrap in a `try/except` and re-raise as `ValueError(f"Corrupt dataset JSON at {dataset_path}: {exc}")`.
- **`Optional[Dict[str, Any]]` from `typing`** (`runner.py`, line 13). Modernize to `dict[str, Any] | None` with `from __future__ import annotations`.

---

## 📊 Overall Project Report — Expert Review

**Files Reviewed:** 5  
**Overall Quality Score:** 6/10  
**Overall Improvement Chance:** 30%  
**Verdict:** ❌ Not production-ready — 2 security issues (API key in URL, system-prompt path mismatch), 2 crash-corruption risks (non-atomic writes), and 1 correctness bug in the retry loop make this unsuitable for deployment as-is.

### Score Breakdown

| File | Score | Expert OK? |
|------|-------|------------|
| `contracts.py` | 8/10 | ✅ |
| `xml_parser.py` | 7/10 | ✅ with caveats |
| `runner.py` | 6/10 | ⚠️ |
| `timing.py` | 6/10 | ⚠️ |
| `llm_writer.py` | 5/10 | ❌ |

### Common Issues (Across the Codebase)

- **f-strings in `log.*()` calls** — `runner.py` and `llm_writer.py` both use f-strings in logging. Correct pattern is `log.info("text %s", var)`.
- **Legacy `typing` imports** — `contracts.py` and `runner.py` both use `List`, `Dict`, `Optional` from `typing` instead of built-in `list`, `dict`, `X | None` with `from __future__ import annotations`.
- **No `os`/`tempfile` imports or atomic writes** — all file writes in Phase 2 use direct `.write_text()`, contradicting the atomic-write standard established and enforced in Phase 1.

---

### 🔴 Critical Fixes (Do First)

1. **`llm_writer.py` line 189** — Move API key from `?key=` URL param to `x-goog-api-key` header. Security risk: key leaks in every server log and traceback.
2. **`llm_writer.py` / `runner.py`** — Unify `SYSTEM_PROMPTS_DIR` to one canonical path. Currently `runner.py` hashes `system_prompts/` (plural) while `llm_writer.py` reads from `system_prompt/` (singular). Cache invalidation is broken for this input.
3. **`runner.py` lines 245–246** — Make both `script.json` and `llm_raw.txt` writes atomic with `tempfile.mkstemp → os.replace`. Add `import os, tempfile`.
4. **`llm_writer.py` line 222** — Change `raise Exception(...)` to `raise ScriptGenerationError(...)` so malformed responses trigger the correct retry path.
5. **`xml_parser.py` line 37** — Change greedy `(.*)` to non-greedy `(.*?)` in the `<MONOLOGUE>` wrapper regex.

---

### 🟡 Important Improvements

1. **`llm_writer.py` line 194** — Replace `"temperature": 0.3` with `settings.gemini_temperature`.
2. **`timing.py` lines 151–173** — Replace the bespoke markdown parser in `_load_visual_rules` with a proper YAML file. Any visual rule description containing `:` silently truncates.
3. **`timing.py` line 87** — Fix `prefix = raw_tag.split("_")[0]` for multi-part dynamic tags (e.g. `ITEM_VALUE_1..ITEM_VALUE_N`). Use a regex to extract the full prefix up to the numeric suffix.
4. **`xml_parser.py` line 46** — Add `re.IGNORECASE` and `.upper()` to the inner tag pattern so lowercase LLM output produces a useful error instead of "No valid XML tags found."
5. **`xml_parser.py` line 86** — Replace O(n²) `expected_tags.index(spec.tag)` loop with simple indexed access `found_elements[i]`.
6. **`runner.py` line 202** — Clean up `# BUG-C5:` dev artifact comment.
7. **`contracts.py`** — Remove unused `ScriptValidationError` or wire it into `xml_parser.py` for length violations (decoupling it from `ScriptParsingError`).

---

### 🟢 Nice to Have

1. **`xml_parser.py` line 74** — Move `from collections import Counter` to module top.
2. **`timing.py`** — Cache `_load_yaml` results with `functools.lru_cache` to avoid repeated disk reads if `build_segment_plan` is ever called multiple times in one process.
3. **`runner.py` line 24** — Remove the unused module-level `logger` or route helper-function logging through it.
4. **`runner.py` line 179** — Wrap `json.loads` in `_load_dataset` with a `try/except json.JSONDecodeError` and re-raise as `ValueError` with the file path.
5. **`llm_writer.py` line 304** — Use `io.StringIO` for `full_generation_history` to avoid unbounded string concatenation across retries.
