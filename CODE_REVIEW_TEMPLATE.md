# Code Review — `src/templates/` — Expert Level

> Reviewed: 2026-05-22 | Standard: Production-ready deployment | Files: 7

---

## 📄 `bar_chart.py` — Expert Review

**Code Quality:** 4/10
**Improvement Chance:** 55%
**Verdict:** Active logic is solid, but 60% of the file is commented-out dead code and the ghost padding is hardcoded to a magic number.

### ✅ What's Good
- Correct delta-time pattern: `global_start_t0 = float(self.time)` anchors the hook correctly.
- `register_template_accent` wired with the correct bar-chart accent.
- SFX marks placed at semantically correct animation moments.
- `sfx.flush()` called unconditionally at line 1464 — no silent failure path.
- `clamp()` used consistently on all `run_time` values to avoid zero-duration crashes.

### ⚠️ Issues Found

🔴 High Priority
- **Lines 1–873 are entirely commented-out dead code** — 873 lines (60% of the file) are a commented-out legacy class. `git log` preserves history; this should be deleted. It makes code navigation impossible and bloats the file to 1464 lines unnecessarily.
- **Ghost padding hardcoded to 15** (line 1349: `range(len(names), 15)`) — If a job has audio segments `item_1` through `item_20`, the loop only runs to `item_15` and 5 audio segments are left unabsorbed. Fix: derive the cap from `audio.order` length, same as `geo_universal` does with `node_segments`.

🟡 Medium Priority
- **`print(f"Intro Error: {e}")` at line 945** — Replace with `logging.warning("bar_chart: IntroManager failed: %s", e, exc_info=True)`.
- **Job dir resolution duplicated** (lines 883–885) — Identical 3-line pattern copy-pasted from every other template. Extract to a shared `_resolve_job_dir()` utility (already exists in `geo_universal.py`).

🟢 Low Priority
- **`load_ai_stats_csv` fallback is silent** — When the CSV is missing, a hardcoded dummy dataset is used without any log. Add `logging.warning(...)` so operators know they're rendering stale data.

---

## 📄 `butterfly_chart.py` — Expert Review

**Code Quality:** 6/10
**Improvement Chance:** 35%
**Verdict:** Well-structured with correct delta-time and good visual depth, but carries a dead import and a ghost-padding off-by-one.

### ✅ What's Good
- `ValueTracker` string-caching fix (mentioned in CHANGELOG) eliminates the memory leak from repeated `Text()` creation in updaters.
- `EndBoxPolicy` dataclass cleanly separates layout constants from logic.
- `_compact_spec_for_target` handles K/M/B formatting without magic strings.
- Delta-time pattern is correct: `TL.consume(seg_name, float(self.time) - item_t0)` then `TL.remaining`.
- `LayoutCfg` with z-index constants prevents z-index collisions between layers.

### ⚠️ Issues Found

🔴 High Priority
- **`RetentionOverlay` imported but never used** (lines 74–78) — The import `from src.sync.retention import RetentionOverlay` and fallback `RetentionOverlay = None` are dead code. `hold_breathing` is used throughout the construct and `RetentionOverlay` is not referenced anywhere in the file. Delete these lines.

🟡 Medium Priority
- **Ghost padding hardcoded to 15** (line 1108: `range(len(attrs) + 1, 15)`) — Same issue as `bar_chart`. Use `audio.order`-derived segment count as the cap.
- **Rotating ring updaters never cleared** (lines 521–523) — `ring1`, `ring2`, `ring3` have `rotate` updaters added permanently. These accumulate through all subsequent `scene.wait()` calls. Clear them before the winner section: `ring1.clear_updaters(); ring2.clear_updaters(); ring3.clear_updaters()`.
- **Segment names hardcoded as strings** — `hold_breathing(self, TL.remaining("hook"), ...)` at line 657 uses `"hook"` as a literal. If a job renames this segment, it silently pulls from a zero-budget bucket.

🟢 Low Priority
- **Fallback `IntroManager`, `get_safe_frame`, `make_floating_particles` duplicated** — Identical or near-identical fallback implementations copy-pasted across all 7 templates. Consolidate into a `src/templates/_fallbacks.py` module.

---

## 📄 `scan_race.py` — Expert Review

**Code Quality:** 7/10
**Improvement Chance:** 20%
**Verdict:** Cleanest of the 7 templates. One timing order issue in the outro segment and a `pandas` hard dependency.

### ✅ What's Good
- `global_start_t0` used and correctly aliased to `hook_t0 = global_start_t0`.
- `register_template_accent` wired at the very top of `construct()`.
- SFX marks properly named and timed to animation events.
- `sfx.flush()` in try/except — acceptable since scan_race has only 5 named segments and no ghost padding needed.
- Fallback `hold_breathing` stub correctly falls back to `scene.wait()`.

### ⚠️ Issues Found

🟡 Medium Priority
- **Outro wait/consume ordering is reversed** (lines 479–480):
  ```python
  hold_breathing(self, TL.seg_total("outro", 1.8), focus=banner, ...)
  TL.consume("outro", float(self.time) - outro_t0)
  ```
  `hold_breathing` uses `seg_total` rather than `remaining`. The consume call after the wait is cosmetic — the segment budget is never deducted before the wait. This works by accident (remaining == seg_total since nothing else consumed "outro"). Use the standard pattern: `TL.consume("outro", ...)` then `hold_breathing(self, TL.remaining("outro"), ...)`.
- **`pandas` hard dependency** — `scan_race` was previously blocked by `pandas` missing in the venv (CHANGELOG B5-ADVANCE). The CSV loader uses `df["Start"]`, `df["Mid"]`, `df["End"]` etc., but the data is simple enough to load with stdlib `csv`. A stdlib fallback would eliminate this fragility.

🟢 Low Priority
- **`load_race_csv` fallback data is silently used** — No warning when CSV file is missing.

---

## 📄 `geo_universal.py` — Expert Review

**Code Quality:** 6/10
**Improvement Chance:** 35%
**Verdict:** Best job dir resolution of all templates (has a reusable `_resolve_job_dir()`), but uniquely fragile at import time because it lacks fallback imports.

### ✅ What's Good
- `_resolve_job_dir()` is a proper reusable helper — the pattern that should be adopted by all templates.
- `_extract_audio_order()` correctly reads segment order from `job.json` instead of hardcoding it.
- `_extract_geo_segments()` cleanly separates segment name resolution from rendering.
- `_timeline_defaults()` as a standalone function makes defaults easy to adjust without touching `construct()`.
- Ghost padding correctly uses `node_segments` length (not a hardcoded cap).

### ⚠️ Issues Found

🔴 High Priority
- **Direct imports without try/except** (lines 15–17) — `from src.config import DATA_DIR, ASSETS_DIR, BACKGROUND_COLOR, Theme` and `from src.utils import IntroManager, get_safe_frame, make_floating_particles` are bare imports with no fallback. Every other template wraps these in `try/except`. If `src.config` is missing or broken, `geo_universal` fails at import time (before `main.py` can catch it), while all other templates degrade gracefully. Add the same `try/except` fallback pattern.

🟡 Medium Priority
- **Data-processing functions inside `construct()` use pandas** (lines 822–847) — `_winner_metric_index()`, `_winner_compare_index()`, `_winner_alliance_group()` are nested helper functions inside `construct()` that call `pd.to_numeric`, `np.nanargmax` etc. These should be module-level helpers or run outside the Manim scene clock, not be defined inside `construct()` where they mix rendering concerns with data logic.
- **Ghost padding off-by-one potential** — `range(len(all_dots) + 1, len(node_segments) + 1)` — the `+1` offsets are correct for 1-indexed segment names like `node_1`, but they're not commented. Add a comment explaining why `+1` on both sides.

🟢 Low Priority
- **`Theme.NEON_ORANGE` and `Theme.NEON_YELLOW` referenced in `GROUP_FALLBACK`** (lines 43–51) but may not exist in all `Theme` fallback definitions — add them to the fallback `Theme` class.

---

## 📄 `donut_breakdown.py` — Expert Review

**Code Quality:** 4/10
**Improvement Chance:** 50%
**Verdict:** Ghost padding is completely broken — it never executes. Extra audio segments are silently left unabsorbed.

### ✅ What's Good
- Correct delta-time pattern used for every named segment.
- `register_template_accent` wired with the donut accent (and correctly captures `donut_center` via closure).
- `AnnularSector` gap stroke (`#050505`) cleanly separates slices.
- SFX marks placed at semantically meaningful events.

### ⚠️ Issues Found

🔴 High Priority
- **Ghost padding loop is always empty** (lines 391–394):
  ```python
  for ghost_i in range(n, len(slice_segs)):
  ```
  `slice_segs` is built as `[f"slice_{i + 1}" for i in range(n)]` — exactly `n` elements. So `range(n, n)` is always empty and ghost padding **never runs**. If a job has more `slice_*` audio segments than CSV rows, they're silently unabsorbed, causing the voice to run past the scene. Fix: build `slice_segs` from `audio.order` (filtering `slice_*` names), not from CSV row count — the same way `geo_universal` builds `node_segments` from `audio.order`.

🟡 Medium Priority
- **`hold_breathing` uses `TL.seg_total("outro", 1.5)` instead of `TL.remaining("outro")`** (line 445) — Same outro ordering issue as `scan_race`. Consume and hold are in the right order here (consume at line 447 after hold), but using `seg_total` instead of `remaining` means any prior consume on "outro" is ignored. Use the standard: consume first, then `hold_breathing(self, TL.remaining("outro"), ...)`.
- **Hardcoded segment name strings** — `"hook"`, `"setup"`, `"winner"`, `"outro"` are hardcoded literals. If job uses different names, the budget falls back to defaults silently.

🟢 Low Priority
- **`INNER_R` and `OUTER_R` are magic numbers** (lines 215–216) — Define as named constants at class or module level for easier visual tuning.

---

## 📄 `sort_card.py` — Expert Review

**Code Quality:** 6/10
**Improvement Chance:** 30%
**Verdict:** Good sync patterns throughout the card loop. Outro pattern is slightly inconsistent but functionally correct.

### ✅ What's Good
- Item segments are driven from `audio.order` via a proper `item_segments` list — not hardcoded names.
- Ghost padding uses `range(len(df), len(item_segments))` which correctly uses the audio-order-derived length.
- `clamp()` applied consistently on all animation durations.
- SFX marks are descriptive and well-placed.

### ⚠️ Issues Found

🟡 Medium Priority
- **`outro` uses `TL.seg_total` not `TL.remaining`** (line 1314):
  ```python
  hold_breathing(self, TL.seg_total(outro_seg, 2.5), ...)
  TL.consume(outro_seg, float(self.time) - outro_t0)
  ```
  Works by accident (nothing else consumed `outro` yet), but violates the established consume-then-remaining pattern. If a future refactor adds a consume call before this, the outro will silently over-run.
- **`sfx.flush()` wrapped in silent `except Exception: pass`** (lines 1317–1320) — If SFX marks fail to write to disk (permissions, full disk), the render completes silently without the SFX track. Change to `except Exception as e: logging.warning(...)`.

🟢 Low Priority
- **`safe_text` wrapper function** is defined locally but does essentially the same thing as `Text()` with a try/except font fallback — identical to `_text_with_fallback` in `retention_base.py`. Consider sharing.

---

## 📄 `vs_card.py` — Expert Review

**Code Quality:** 7/10
**Improvement Chance:** 20%
**Verdict:** Most complete implementation — correct delta-time, proper ghost padding, good segment naming. Two minor structural issues.

### ✅ What's Good
- All segment names read from `audio.order` — no hardcoded string segment names in the main loop.
- Ghost padding uses `range(len(df), len(round_segments))` correctly.
- Early-return draw branch calls `sfx.flush()` before returning — no flush is ever skipped.
- `ValueTracker`-based scoreboard doesn't create `Text()` per frame (string-cached).
- `vs_box.clear_updaters()` + `vs_grp.clear_updaters()` called before outro — good cleanup discipline.

### ⚠️ Issues Found

🟡 Medium Priority
- **`sfx.flush()` called twice** — Once inside the draw branch at line 1469, and again at line 1547 for the win path. This is structurally correct (draw returns early), but `sfx.flush()` writing the same SFX marks file twice if somehow both branches execute would produce a corrupt file. The `return` at line 1470 prevents this, but the structure is fragile. Consolidate to a single `finally`-style flush at the very end of `construct()` with the early draw path simply not flushing.
- **`reset_t0` pattern at line 1400** — `TL.consume(seg_name, float(self.time) - reset_t0)` where `reset_t0` is set inside a draw-branch. If the win branch is taken, `reset_t0` may shadow an earlier variable of the same name. Rename to `draw_reset_t0` or `branch_t0` for clarity.

🟢 Low Priority
- **`p1_pts`, `p2_pts` accumulated from `p1_wins`/`p2_wins`** — Variable naming suggests points vs wins but they're used interchangeably. Clarify which is which in comments.

---

## 📊 Overall — `src/templates/` — Expert Review

**Files Reviewed:** 7
**Overall Quality Score:** 5/10
**Overall Improvement Chance:** 35%
**Verdict:** ❌ Not production-ready as a group — one ghost padding is completely broken, one file is 60% dead code, and all 7 share identical boilerplate that creates a maintenance risk.

### Score Breakdown
| File | Score | Level OK? |
|------|-------|-----------|
| `bar_chart.py` | 4/10 | ❌ |
| `butterfly_chart.py` | 6/10 | ❌ |
| `scan_race.py` | 7/10 | ✅ |
| `geo_universal.py` | 6/10 | ❌ |
| `donut_breakdown.py` | 4/10 | ❌ |
| `sort_card.py` | 6/10 | ❌ |
| `vs_card.py` | 7/10 | ✅ |

### Common Issues (Across All 7 Templates)

1. **Boilerplate duplication** — Every template duplicates: (a) `get_safe_frame` fallback (~10 lines), (b) `IntroManager` fallback (~10 lines), (c) `make_floating_particles` fallback (~2 lines), (d) job dir resolution (3 lines). That's ~25 lines × 7 files = 175 lines of copy-pasted maintenance risk. One update to `get_safe_frame` signature requires 7 edits.
2. **`pandas` hard dependency with no fallback** — All 7 templates use `pd.read_csv()` at module level. If `pandas` is not installed (CHANGELOG B5-ADVANCE flagged this), all templates fail on import. Each should fall back to stdlib `csv` for simple column reads.
3. **Silent SFX flush failures** — `scan_race`, `donut_breakdown`, and `sort_card` wrap `sfx.flush()` in `except Exception: pass`. SFX marks silently not written = no SFX in final video with zero diagnostic output.
4. **Outro consume/wait ordering inconsistency** — `scan_race`, `donut_breakdown`, `sort_card` use `TL.seg_total()` in `hold_breathing` instead of `TL.remaining()`. Works by accident currently but is fragile. Standard pattern (used in `bar_chart`, `vs_card`): `TL.consume(seg, time - t0)` → `hold_breathing(self, TL.remaining(seg), ...)`.

### 🔴 Critical Fixes (Do First)

1. **`donut_breakdown.py` line 391** — Ghost padding `range(n, len(slice_segs))` is always empty. Replace with: build `slice_segs` from `audio.order` (not CSV row count). This is a data loss bug — extra audio segments are permanently silently skipped.
2. **`bar_chart.py` lines 1–873** — Delete 873 lines of commented-out legacy code. This is not a cosmetic issue; it makes the file unnavigable and confuses any tool that reads the file.
3. **`geo_universal.py` lines 15–17** — Wrap direct imports in `try/except` with fallbacks identical to the other 6 templates. A bare import failure crashes the entire render before `main.py` can report the error.

### 🟡 Important Improvements

1. **All templates** — Extract job dir resolution into a shared `src/templates/_utils.py` module with `resolve_job_dir()`, `resolve_data_csv()` functions. `geo_universal` already has these — copy them out.
2. **`bar_chart.py` + `butterfly_chart.py`** — Replace ghost padding hardcoded cap of `15` with the length of `audio.order` filtered to `item_*` segments.
3. **`butterfly_chart.py` lines 74–78** — Delete the `RetentionOverlay` import — it's dead code.
4. **`butterfly_chart.py` lines 521–523** — Clear `ring1/ring2/ring3` updaters before the winner/outro section to avoid drift accumulation during final wait calls.
5. **All templates** — Replace `except Exception: pass` on `sfx.flush()` with `except Exception as e: logging.warning("sfx.flush failed: %s", e)`.

### 🟢 Nice to Have

1. **All templates** — Replace the 7 identical `IntroManager`/`get_safe_frame`/`make_floating_particles` fallback blocks with a single import from `src/templates/_fallbacks.py`.
2. **All templates** — Replace `pandas` CSV loading with a stdlib `csv` fallback for cases where only simple `Name,Value` columns are needed.
3. **`donut_breakdown.py`** — Define `INNER_R = 1.48` and `OUTER_R = 2.55` as named module-level constants.
4. **`vs_card.py`** — Consolidate the two `sfx.flush()` calls (lines 1469 and 1547) into a single call at the bottom to remove the structural fragility of the early-return flush.
