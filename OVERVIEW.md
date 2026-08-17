# Project Overview — AutoShorts
**Generated:** 2026-06-04 | **Source:** CHANGELOG_CODEX.md + CODE_REVIEW files + REFACTOR_PLAN files + git history + test run

---

## What is this?
AutoShorts is an end-to-end pipeline that turns a topic into a finished short-form data video.
It has two independent halves that share `jobs/<job_id>/` as their handoff bus:
- **Data Pipeline** (Phases 1–3) — AI-driven topic discovery, data extraction, script writing, TTS audio
- **Video Renderer** (Phase 4) — Reads `job.json` + audio, renders a Manim scene, mixes audio/SFX/BGM, optionally burns captions

## Tech Stack
- **Python 3.11+** · Manim (scene rendering) · FFmpeg (audio/video mixing)
- **LLM**: OpenAI `gpt-5.6-luna` on all routes (Gemini kept as a secondary A/B option) · **Search**: Tavily (topic evidence)
- **Audio TTS**: ElevenLabs (Phase 3) · **Schema**: Pydantic v2 · **State machine**: LangGraph
- **Testing**: pytest + offline fakes (no API keys needed for most tests)

---

## Feature Status

### ✅ Completed

**Video Renderer (Phase 4)**
- `main.py` full pipeline — Manim render → voice concat → SFX mix → BGM mix → final mux
- Silence trimming in concat (`--no-trim-silence` to disable)
- `--open`, `--no_sfx`, custom `--ffmpeg` flags all wired

**7 Templates — All registered in `main.py` TEMPLATE_MAP**
| Template | Scene Class | Job Scaffold |
|----------|-------------|--------------|
| `bar_chart` | `BarChartTemplate` | `jobs/job_0001/` |
| `butterfly_chart` | `ButterflyChart` | `jobs/butterfly_job/` |
| `scan_race` | `CinematicLineRace` | `jobs/scan_job/` |
| `geo_universal` | `GeoUniversalMap` | `jobs/geo_job/` |
| `sort_card` | `SortCardTribunalFinal` | *(no dedicated scaffold)* |
| `vs_card` | `VsCardFinal` | *(no dedicated scaffold)* |
| `donut_breakdown` | `DonutBreakdownFinal` | *(no dedicated scaffold)* |

**Sync / Retention Layer (`src/sync/`)**
- `Timeline` — budget-tracking with overrun warnings
- `hold_breathing` — 4-layer fail-safe hold with per-template retention accents
- Technical Refactor Phases 0–3 completed: HUD telemetry, delta-time sync, ghost padding loops, visual audit

**Captions Pipeline (`src/captions/`)**
- ASS subtitle generation — plain / reveal_words / karaoke modes
- `modern_clean` + `modern_premium` style presets
- Standalone `captions.py` CLI with `--burn`

**Data Pipeline (Phases 1–3) — Core + Agents Refactored**
All four `src/agents/` modules have completed expert code review + refactor on branch `features/agentic_engine`:

| Module | Review File | Refactor File | Status |
|--------|-------------|---------------|--------|
| `src/agents/core/` | `CODE_REVIEW_CORE.md` | `REFACTOR_PLAN_CORE.md` | ✅ Applied (15 items) |
| `src/agents/phase1_*/` | `CODE_REVIEW_phase1.md` | `REFACTOR_PLAN_PHASE1.md` | ✅ Applied (20 items) |
| `src/agents/phase2_scripting/` | `CODE_REVIEW_PHASE2.md` | *(inline)* | ✅ Applied |
| `src/agents/phase3_audio/` | `CODE_REVIEW.md` | `REFACTOR_PLAN.md` | ✅ Applied (11 items) |

Key fixes applied in `polish8` commit (`d040bcaf`):
- `config.py` — module-level singleton replaced with `@lru_cache get_settings()` factory (testability fix)
- `packager.py` — `atomic_write_bytes()` added; phase 3 runner now writes audio atomically
- `_offline_tts.py` — fake TTS extracted out of test file (no longer pollutes root logger on import)
- `runner.py` (phase3) — double ffmpeg decode per segment eliminated
- Phase 1 — atomic writes, retry logic, timeout guards, URL dedup all applied
- New test fixtures added: `tests/fixtures/` with n-variant JSON fixtures for all 7 templates

**Tests**
- Phase 2 scripting: 3/3 pass
- Phase 1: 20/21 pass (1 known test fixture bug — see WIP below)
- `runbook_agentic.md` created — agentic pipeline command reference

---

### 🔄 Currently Working On

- **`features/agentic_engine` branch** — 3 commits ahead of `main` (`d040bcaf`, `feb7721b`, `1749b245`). Not yet merged.
- **Phase 1 test failure** — `tests/phase1/test_discovery_runner.py::test_run_discovery_writes_candidates_json` fails with:
  ```
  ValidationError: Unknown template 'line_chart'
  ```
  Root cause: test fixture constructs `TopicCandidate(fallback_template="line_chart" if "line_chart" else "bar_chart")` — the ternary is always truthy, passing `"line_chart"` which is not in `VALID_TEMPLATES`. Fix: change to a valid template name (`"scan_race"` or `"bar_chart"`) in the test fixture.

---

### 📋 Planned / Not Started

- **Translation support** — `translator.py` is a stub; `enabled=False` hardcoded in pipeline. Needs a provider integration.
- **`sort_card`, `vs_card`, `donut_breakdown` job scaffolds** — These three templates have no dedicated `jobs/` directory.
- **Manual render verification** — geo_universal, donut_breakdown, butterfly_chart final render check still pending after refactors (render requires local manim env).
- **Merge `features/agentic_engine` → `main`** — Pending test fix + smoke.

---

## Last Active Area

`src/agents/` (all phases) — Major refactor pass completed in `polish8` commit (2026-06-03). Expert code reviews done for all 4 agent modules; all 46 refactor items applied.

---

## Next Step (Inferred)

**1. Fix the Phase 1 test fixture (5 min):**
```python
# tests/phase1/test_discovery_runner.py ~line 63
# Change:
fallback_template="line_chart" if "line_chart" else "bar_chart"
# To:
fallback_template="scan_race"   # or any other VALID_TEMPLATES member
```

**2. Verify full test suite green:**
```powershell
python -m pytest tests/phase1 tests/phase2_scripting -v
```

**3. Run pipeline smoke (offline mode, no API keys):**
```powershell
python -m src.agents.phase3_audio.offline_e2e
```

**4. Merge `features/agentic_engine` → `dev` or `main`** when tests are clean.

---

*Notes:*
- *Phase 1 test failure confirmed by live test run — root cause is test fixture, not production code*
- *All refactor items status inferred from code inspection (get_settings, atomic_write_bytes, _offline_tts.py all confirmed present)*
- *Render verification (geo_universal, butterfly_chart visual pass) still pending — requires local manim environment*
