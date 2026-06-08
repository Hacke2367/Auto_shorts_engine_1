# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visual Work: Polish-Only Mandate (IMPORTANT)

Whenever doing visual/aesthetic work on the Manim templates (`src/templates/`), the shared visual
layer (`src/utils.py`), or the retention layer (`src/sync/retention*.py`), the scope is **visual
polish ONLY**. The standing target on every such task:

- **Do not break anything that already works.** Never alter audio-visual sync, segment timing
  (`TL.consume` / `hold_breathing` / `Timeline.seg_total`), the core template/scene logic, or the
  data pipeline. If a thing already looks and works correctly, leave it untouched — improve only what
  is genuinely flat/cheap.
- **Additive changes only.** Add visuals via `scene.add()` + lightweight updaters. During a visual
  pass, **never** introduce new `self.play(..., run_time=...)` calls and **never** change any
  `TL.consume` / `hold_breathing` durations — those define sync and must stay byte-identical.
- **Verify after every visual change.** The render must stay full-length and in sync: the Manim video
  duration must match the audio (compare via `tools/audio_durations.py`; the raw scene render
  `media/.../<Scene>.mp4` / `_staged_render.mp4` must equal audio length). A shorter final.mp4 than
  the scene render means the audio was truncated (e.g. silence-trim) — not a visual regression.
- **Work part-by-part with visual sign-off.** Ship one part at a time, then give the exact render
  command and wait for the user's own-eyes confirmation before proceeding to the next part.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Project Overview

AutoShorts is an end-to-end pipeline that turns a topic into a finished short-form data video. Two distinct halves share the `jobs/<job_id>/` directory as their handoff bus:

1. **Data pipeline** (`src/agents/`, `src/cli/`) — Phases 1–3 + Handoff. Discovers topics, extracts data, writes a script, synthesizes audio, then produces `job.json` in the schema the renderer expects. LLM-driven (Gemini + Tavily).
2. **Video renderer** (`main.py`, `src/templates/`, `src/captions/`, `src/sync/`, `src/sfx/`) — Phase 4. Reads `job.json` + audio + script, renders a Manim scene from a template, mixes audio + SFX, optionally burns captions.

The two halves can run independently. `main.py` only needs a fully-formed `jobs/<id>/` directory; how that directory got there (manual or pipeline) does not matter.

## Environment

- Python 3.11+ with `.venv`. Install: `pip install -r requirements.txt`.
- FFmpeg must be on PATH (`ffmpeg -version`).
- `.env` at repo root holds **secrets only**: `TAVILY_API_KEY`, `GEMINI_API_KEY` (required), `ELEVENLABS_API_KEY` (optional). `src/agents/core/config.py` raises ValidationError on import if a required key is missing.
- **All operational settings live in `config.py`, NOT `.env`.** Per-phase model routing, temperatures, RPM, HTTP timeout, retry/backoff, TTS defaults, and authority domains are managed in `APP_CONFIG` (`src/agents/core/config.py`). To change the model for a phase, edit `LLMConfig` there. The legacy env vars `GEMINI_MODEL` / `GEMINI_RPM_LIMIT` / `GEMINI_TEMPERATURE` / `API_TIMEOUT_SECONDS` are **ignored** — do not put them in `.env`.
- Windows shell here is PowerShell; the Bash tool is available but most examples below use forward slashes which work in both.

## Common Commands

### Rendering (Phase 4)
- Full render of an existing job: `python main.py --job jobs/job_0001 --template bar_chart -q h`
- Skip SFX mixing: append `--no_sfx`
- Skip silence trim during concat: `--no-trim-silence`
- Captions only (regenerate ASS + burn): `python captions.py --job jobs/job_0001 --burn`
- Render a single scene directly (bypasses mixing/captions): `python -m manim -qh src/templates/Bar_chart/bar_chart.py BarChartTemplate --media_dir jobs/job_0001/media`
- Template registry lives in `main.py` (`TEMPLATE_MAP`) — adding a template means registering a `{file, scene}` entry here.

### Data Pipeline (Phases 1–3)
The master CLI is `src/cli/autoshorts.py`. Bucket = templated job folder under `jobs/<bucket>/<run_id>/`.

- New empty job bucket: `python -m src.cli.autoshorts new --template <template>`
- Phase 1 Discovery (find topic candidates via Gemini ideation + Tavily search): `python -m src.cli.autoshorts phase1-discover --template <template>`
- Phase 1 Extraction (extract structured data for an approved candidate): `python -m src.cli.autoshorts phase1-extract ...`
- Phase 2 Scripting → Phase 3 Audio → Handoff → Phase 4 Render: `python -m src.cli.autoshorts run --job <run_dir> --template <template> --persona <persona>`
- Granular Phase 1 control: `python -m src.cli.phase1 ...` (discovery, scoring, archive management).

### Audio / Timeline Tooling
- Verify durations vs `timeline`: `python tools/audio_durations.py --job jobs/<job_id>`
- Strict mismatch detection: append `--write-timeline` to preserve-write durations (won't touch other keys).

### Tests
- All tests live under `tests/` (subfolders `phase1/`, `phase2_scripting/`, `pipeline/`).
- Run a single phase: `python -m pytest tests/phase1 -v`
- Run all pipeline tests: `python tests/pipeline/run_all.py`
- Most tests use fakes/fixtures (`fake_llm.py`, `dummy_phase1_outputs.py`, `*_fake.py`) so no API keys are required for them.
- Phase 3 has an offline e2e mode: `src/agents/phase3_audio/offline_e2e.py` and `tests_offline.py`.

### Compile-only Smoke Checks
The codebase relies heavily on `python -m py_compile <file>` as a fast pre-commit sanity check for template/scene files. Use this before long renders.

## Architecture: The `jobs/<id>/` Contract

This directory is the single source of truth that the data pipeline writes and the renderer reads. Touching its schema affects both halves.

```
jobs/<job_id>/
  job.json                 # Schema below — authoritative config for renderer
  script/script.json       # Per-segment voice lines (Phase 2 output)
  audio/                   # Per-segment .wav/.mp3, plus bgm/ subdir (Phase 3 output)
  data/                    # Source CSV/JSON (Phase 1 Extraction output)
  output/                  # Phase 4 deliverables: final.mp4, subtitles.ass, final_captioned.mp4, sfx_marks.json
  media/                   # Manim intermediate render artifacts (regeneratable)
  .pipeline_state.json     # JobManager idempotency state — phase completion flags
  discovery/, attempts/    # Only for "auto" template flows
```

Critical invariants the renderer enforces:
- `audio.segments[].name` and `audio.order[]` must list the same set of segments in the same order.
- `timeline[<segment_name>]` must provide a duration for every segment in `audio.order`.
- `script.json` segment names must align with `audio.order`.

Drift between these four lists is the most common source of render failures. `tools/audio_durations.py` and `src/captions/timeline_resolver.py` are the canonical places to debug alignment.

## Architecture: Data Pipeline (`src/agents/`)

Phases produce + consume artifacts under a single run directory; each phase is idempotent via `JobManager`'s `.pipeline_state.json` step flags.

- `core/` — shared infra. `config.py` (pydantic-settings, fails fast on missing API keys), `job_manager.py` (creates dir tree, atomic state writes via temp-file → `os.replace`, tolerates corruption), `models.py` (`VALID_TEMPLATES`, `TEMPLATE_FALLBACKS`, `QueuedTopic`, `TopicCandidate`, `DiscoveryBatch`), `cost_tracker.py` (JSONL cost events per run), `rate_limiter.py`, `logger.py`.
- `phase1_discovery/` — `discovery_runner.py` runs the Idea-First flow: Gemini ideation → archive filter → Tavily evidence (`scourer.py`) → Gemini scoring (`candidate_score.py`) → ranked `candidates.json`. `archive_manager.py` prevents re-pitching already-produced or rejected topics.
- `phase1_extraction/` — `runner.py` orchestrates extraction; `graph.py` is a LangGraph state machine; `api_clients.py` wraps Tavily + Gemini calls. Output: `data/<template>_dataset.json` + `data/data_manifest.json`.
- `phase2_scripting/` — `runner.py` builds prompt → `llm_writer.py` calls Gemini → `xml_parser.py` extracts segments → `timing.py` estimates per-segment duration → writes `script/script.json`. `contracts.py` defines the schema.
- `phase3_audio/` — `runner.py` orchestrates TTS via `tts_client.py`, then `duration.py` measures real audio, `trimming.py` applies silence trim, `packager.py` lays out `audio/` files. `offline_e2e.py` allows running without TTS API.
- `final_handoff/handoff.py` — converts the pipeline's internal `script.json` + `audio/` into the exact `job.json` shape `main.py` expects (tag-to-engine-name mapping in `tag_to_engine_name`).

LangGraph is used in `phase1_extraction/graph.py` to model the extract-validate-retry loop as a state machine.

## Architecture: Video Renderer

- `main.py` — entrypoint. Loads `job.json`, selects template from `TEMPLATE_MAP`, invokes Manim with the right scene class, then runs the audio mix pipeline (`concat_audio_ffmpeg` with optional silence trim, BGM mix, SFX overlay from `sfx_marks.json`), then optionally calls the captions pipeline.
- `src/templates/<chart_kind>/<file>.py` — each template is a Manim `Scene` subclass. Scenes pull timing from `Timeline.from_dict(job["timeline"])` (`src/sync/timeline.py`) and write SFX cue marks to `output/sfx_marks.json`. Some templates have a local `SFXMarksWriter` (legacy); the shared one is `src/sfx/engine.py`.
- `src/sync/` — `job.py` loads job.json, `timeline.py` wraps duration logic + `hold_breathing`, `retention.py` is the retention overlay (streaks/center particles) injected by some scenes.
- `src/sfx/` — `engine.py` (writer), `registry.py` (maps cue keys → wav files in `assets/sfx/`).
- `src/captions/` — `pipeline.py` is the top-level entry (called from `main.py` and `captions.py`); `script_loader.py` reads `script/script.json`, `timeline_resolver.py` aligns it to durations, `styles.py` provides presets (`modern_clean`, `modern_premium`), `ass_renderer.py` writes the ASS file, `burn_in.py` calls ffmpeg to hardcode subtitles. `translator.py` and `aligner.py` are for multilingual / forced-alignment work.
- `src/utils.py` — shared visual layer (`Brand`, safe-frame helpers, `IntroManager`, overlays/watermarks). The file has two `utils.py` header blocks; the active code is in the second block — the first is legacy commented-out code. Don't edit the legacy block.

## Conventions

- Python: 4-space indent, snake_case for functions/vars, PascalCase for Manim `Scene` classes. No enforced formatter — `black`/`ruff`/`pytest` are the suggested tools if adding automation.
- Use `pathlib.Path` for all path manipulation; resolve relative paths against the project root or job dir explicitly (most modules compute `PROJECT_ROOT = Path(__file__).resolve().parents[N]`).
- Pipeline state writes go through `JobManager.mark_step_completed` — never write `.pipeline_state.json` directly; the atomic temp-file → `os.replace` pattern is the safety net for mid-write crashes.
- Generated artifacts (`media/`, `jobs/*/output/`, `*.log`, `traceback.txt`, etc.) are not committed unless required for review.

## When Things Break

- "Audio truncated" or "long final pad" → check `timeline` durations match real audio (`tools/audio_durations.py`). `butterfly_chart` pads extra `itemN` segments; `bar_chart` does NOT — items beyond declared bars get truncated by `-shortest` at mux time.
- "Caption misalignment" → segment names must match across `script.json`, `audio.segments`, `audio.order`, and `timeline`.
- "ValidationError on import" → `.env` is missing `TAVILY_API_KEY` or `GEMINI_API_KEY`.
- "Phase rerun does nothing" → `.pipeline_state.json` has the step marked complete; delete the relevant key or use the CLI's force flag.
