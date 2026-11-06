# PLANS

## Batch-1 Audit Notes

### bar_chart (`src/templates/Bar_chart/bar_chart.py`)
- Design and pacing findings:
- Strong visual hierarchy already exists (title/underline/subtitle + depth layers + winner banner), but title/subtitle can overflow for long CSV meta text because there is no width-fit/clamp.
- Guide labels are hardcoded to `0/25/50/75/100` while data can use arbitrary `max_val`; this can visually mislead when `max_val != 100`.
- Pipeline risks (audio sync, SFX marks, captions hooks):
- Uses timeline-driven pacing via `Timeline.from_dict` and `hold_breathing`, and writes SFX marks in `output/sfx_marks.json`; this is compatible with current `main.py` mixing flow.
- Uses local `SFXMarksWriter` implementation instead of shared `src/sfx/engine.py`; not broken, but duplicated logic increases drift risk.
- Captions are pipeline-level (job + script + timeline); template does not validate segment alignment, so bad job/script alignment fails later in captions stage.
- Long-audio-pad break risks:
- If voice has more item segments than rendered bars, bar_chart does not explicitly pad missing item segments (unlike butterfly); long extra audio can be truncated at final mux (`-shortest`).
- If CSV/meta yields values above declared `max_val`, bar width can exceed container bounds because target width is not clamped to container max.

### butterfly_chart (`src/templates/chart_folder/butterfly_chart.py`)
- Design and pacing findings:
- Visual language is premium and consistent (rings, glass cards, timeline spine, winner banner); pacing is segmentized with `sync.begin/end` per phase.
- Header/title copy is fixed in code and not job-driven; this reduces template reuse flexibility compared with data-driven bar title/subtitle.
- Pipeline risks (audio sync, SFX marks, captions hooks):
- Critical bug risk: fallback branch uses `RetentionOverlay(...)` even when import failed (`RetentionOverlay = None`), which can crash construct path.
- Data file resolution does not prioritize `job_dir/data/...`; it checks project/current fallbacks first, so job-scoped data may be skipped unintentionally.
- SFX marks are written in expected shape (`{"version":1,"marks":[{"t","key"}]}`) and compatible with `main.py`; exception handling in `write()` is silent, so failures can be hidden.
- Long-audio-pad break risks:
- Stronger than bar_chart for long pads: `AudioSync.end()` pads each segment to actual audio duration and `pad_missing_item_segments()` handles extra `itemN` clips.
- Retention overlay behavior during long pads depends on overlay availability; the fallback bug can disable/ break this safety under missing import conditions.

## Batch-1 B4.5/B4.6 Execution

### B4.5 — Audio duration tooling
- B4.5-S1: Document execution slice + changelog entry.
- B4.5-S2: Add `tools/audio_durations.py` compatibility wrapper.
- B4.5-S3: Upgrade `tools/audio_duration.py` with strict mismatch detection, timeline delta reporting, and `--write-timeline` gate.
- B4.5-S4: Preserve-only timeline writes (no other job key edits) when write flag is explicitly enabled.

### B4.6 — Silence trim in concat/mix path
- B4.6-S1: Add `--no-trim-silence` CLI flag in `main.py` (default trim ON).
- B4.6-S2: Extend `concat_audio_ffmpeg` to apply conservative leading/trailing silence trim per segment when enabled.
- B4.6-S3: Compile checks + runtime invocation checks for both trim ON/OFF paths.

### B5 — Immediate follow-up after B4.5/B4.6
- B5-S1: Preflight alignment + duration check for `jobs/scan_job`.
- B5-S2: Captions OFF smoke render for `scan_race`.
- B5-S3: Captions ON smoke render for `scan_race`.
- B5-S4: Final duration sanity check (`ffprobe` vs timeline sum).

## Batch-1 Retention + Captions Premium Polish

### Scope (locked)
- `src/sync/retention.py`
- `src/captions/styles.py`
- `src/captions/ass_renderer.py`
- `PLANS.md`
- `CHANGELOG_CODEX.md`

### Constraints
- No job folder changes.
- No schema changes.
- No long render commands in this pass.
- Keep retention public API unchanged.

### Changes
- Retention overlay visual polish:
- reduce streak dominance (opacity/width/speed)
- keep center clean while adding very subtle center micro-particles
- keep top message + subtitle-safe layout behavior unchanged
- Captions style polish:
- add new `modern_premium` preset
- keep `modern_clean` unchanged for compatibility
- font fallback chain preference: `Montserrat -> Segoe UI -> Liberation Sans -> DejaVu Sans`
- ASS dialogue polish:
- apply subtle per-dialogue tags only for `modern_premium`
- `\fad(140,100)` + tiny start blur/outline easing
- no movement effects, readability-first
- keep `max_lines=2` and existing mode behavior unchanged

### Acceptance Criteria
- `modern_premium` is selectable and emits valid ASS.
- `modern_clean` output path remains unchanged.
- Retention functions/signatures remain the same.
- Only scoped files are edited.
- Fast checks pass:
- `python3 -m py_compile src/sync/retention.py src/captions/styles.py src/captions/ass_renderer.py`

## Geo Batch — `geo_universal` Job Migration

### Locked Rules
- Do not remove/replace existing geo visuals/animations.
- Add only job-driven timing and audio/SFX integration.
- Visual changes only additive micro-polish (positions/margins), no deletions.
- No long renders in this batch.

### Implementation Checklist
- Add `geo_universal` entry in `main.py` registry.
- Create single-folder scaffold `jobs/geo_job/` (`job.json`, `script/script.json`, `audio/`, `data/`, `output/`, `media/`).
- Copy `data/map_data.csv` to `jobs/geo_job/data/map_data.csv`.
- Integrate `geo_universal.py` with `src/sync.job.load_job`, `src/sync.timeline.Timeline`, and shared `src/sfx/engine.SFXEngine`.
- Use `audio.order` as authoritative source for `node_*` segment count and order.
- Keep segment alignment strict across `audio.segments`, `audio.order`, `timeline`, `script`.
- Add fast compatibility checks only:
- `python3 -m py_compile ...`
- `python3 tools/audio_durations.py --job jobs/job_0001`
- `python3 tools/audio_durations.py --job jobs/butterfly_job`
- `python3 tools/audio_durations.py --job jobs/scan_job`
