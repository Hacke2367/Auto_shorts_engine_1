# Project Overview — AutoShorts
**Generated:** 2026-05-22 | **Source:** CHANGELOG_CODEX.md + PLANS.md + RUNBOOK.md + git history + codebase scan

---

## What is this?
AutoShorts is an end-to-end pipeline that turns a topic into a finished short-form data video.
It has two independent halves that share `jobs/<job_id>/` as their handoff bus:
- **Data Pipeline** (Phases 1–3) — AI-driven topic discovery, data extraction, script writing, TTS audio
- **Video Renderer** (Phase 4) — Reads `job.json` + audio, renders a Manim scene, mixes audio/SFX/BGM, optionally burns captions

## Tech Stack
- **Python 3.11+** · Manim (scene rendering) · FFmpeg (audio/video mixing)
- **LLM**: Gemini (ideation, scripting) · **Search**: Tavily (topic evidence)
- **Audio TTS**: ElevenLabs (Phase 3) · **Schema**: Pydantic v2
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
- `hold_breathing` — 4-layer fail-safe hold: Living Data glow, Confidence Tick, Narrative Cursor, Template Accent
- 7 per-template accent functions in `retention_accents.py`
- `job_config.py` — Pydantic v2 schema with cross-field validators (audio alignment + timeline coverage)
- Technical Refactor Phases 0–3 completed: HUD telemetry, delta-time sync standard, ghost padding loops, visual audit

**Captions Pipeline (`src/captions/`)**
- ASS subtitle generation — plain / reveal_words / karaoke modes
- `modern_clean` + `modern_premium` style presets with font fallback chain
- Standalone `captions.py` CLI with `--burn`, `--force`, custom output paths
- `timeline_resolver` — uses `job.timeline` with ffprobe fallback

**Tooling**
- `tools/audio_durations.py` — strict segment mismatch detection, `--write-timeline` gate
- `RUNBOOK.md` — complete command reference for every pipeline step
- `src/sync/job_config.py` — Pydantic schema catches audio/timeline misalignment at load time

**Data Pipeline (Phases 1–3)**
- Phase 1: Topic discovery (`src/agents/phase1_discovery/`) + Data extraction (`phase1_extraction/` + LangGraph)
- Phase 2: Script generation (`phase2_scripting/`) with LLM + XML parsing
- Phase 3: TTS synthesis (`phase3_audio/`) with offline e2e mode
- Handoff: `final_handoff/handoff.py` converts pipeline output → `job.json` shape
- CLI: `src/cli/autoshorts.py` (master) + `src/cli/phase1.py` (granular)
- Tests: `tests/phase1/`, `tests/phase2_scripting/`, `tests/pipeline/` — all use fakes (no API keys)

**Code Quality (This Session — `features/polishing`)**
- Expert code review of `src/sync/` and `src/captions/` completed → `CODE_REVIEW.md`
- All review issues fixed across 11 files (no core logic changed):
  - Critical NameError bug fixed (`styles.py` — missing `Path` import)
  - `burn_in` default inconsistency fixed (`True` → `False`)
  - `source_lang` default fixed (`"hi"` → `"en"`)
  - Donut accent contract violation fixed (ghost copy instead of mutating focus)
  - Key-phrase logic bug fixed in `hold_breathing`
  - Schema validators added to `job_config.py` for audio alignment + timeline coverage
  - Logging added across all silent `except` blocks
  - subprocess timeout + stderr capture added

---

### 🔄 Currently Working On

- **`features/polishing` branch** — Polish + code quality pass. Code review done, fixes applied. Pending: compile smoke + merge.
- **Phase 1 pipeline flaw** — Known issue (commit: `"phase1 have flaw"`, `"phase 1 testing pending"`). Phase 1 agents (`src/agents/`) were modified in the last data-pipeline commit but testing is marked as incomplete. *(Inferred from git history)*
- **B5 end-to-end smoke** — scan_race and geo_universal jobs have aligned scaffolds but full render verification (real audio + manim environment) is still pending per CHANGELOG_CODEX last entries.

---

### 📋 Planned / Not Started

- **Translation support** — `translator.py` is a stub; `enabled=False` hardcoded in pipeline v1. Needs a provider integration.
- **`pandas` removal from `scan_race`** — `scan_race.py` depends on `pandas` which caused a blocking install failure in the venv (noted in CHANGELOG Step B5-ADVANCE). Template should switch to stdlib CSV reading.
- **`sort_card`, `vs_card`, `donut_breakdown` job scaffolds** — These three templates have no dedicated `jobs/` directory; they borrow `jobs/job_0001` for testing. Production job scaffolds not yet created.
- **Manual render verification** — geo_universal, donut_breakdown, butterfly_chart final render check still listed as "Next step" in the last few CHANGELOG entries.

---

## Last Active Area

`src/sync/` + `src/captions/` — Just finished expert code review + applied all fixes in this session (`features/polishing` branch). 11 files modified.

Previously: `src/agents/` and `main.py` — Phase 1 pipeline flaw investigation (most recent data-pipeline commit).

---

## Next Step (Inferred)

**1. Run the compile smoke check** to verify today's fixes didn't break anything:
```powershell
python -m py_compile src/sync/job.py src/sync/timeline.py src/sync/job_config.py src/sync/retention_base.py src/sync/retention_accents.py
python -m py_compile src/captions/pipeline.py src/captions/styles.py src/captions/ass_renderer.py src/captions/burn_in.py src/captions/script_loader.py src/captions/timeline_resolver.py src/captions/aligner.py src/captions/translator.py
```

**2. Do a fast smoke render** to confirm Phase 4 still works end-to-end:
```powershell
python main.py --job jobs/job_0001 --template bar_chart -q l --no_sfx
```

**3. Investigate the Phase 1 flaw** — check `src/agents/phase1_discovery/` and `src/agents/phase1_extraction/` for the issue referenced in commit `e57fe1b3`. Run:
```powershell
python -m pytest tests/phase1 -v
```

---

*Notes:*
- *Template status for sort_card/vs_card/donut_breakdown inferred from absence of dedicated job scaffolds + no CHANGELOG entries for standalone job creation*
- *Phase 1 "flaw" status inferred from git commit messages — no specific error log found*
- *B5 smoke render blocking by environment (pandas/manim) noted in CHANGELOG; assumed resolvable in user's local env*
