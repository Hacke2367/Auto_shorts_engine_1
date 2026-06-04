# RUNBOOK — Video Generation Pipeline
**Project:** AutoShorts | **Updated:** 2026-05-15

This runbook covers every command required to operate, test, and render videos in this project.

---

## Prerequisites

```bash
# Activate the virtual environment
.venv\Scripts\activate          # Windows PowerShell
source .venv/bin/activate       # Linux / macOS

# Install dependencies
pip install -r requirements.txt

# Verify FFmpeg is on PATH (both are required)
ffmpeg -version
ffprobe -version
```

> **Note:** `.env` at project root is required **only for Phases 1–3** (Agent/Content pipeline).
> The Video Generation renderer (`main.py`) does not need any API keys.
> ```
> TAVILY_API_KEY=...
> GEMINI_API_KEY=...
> ELEVENLABS_API_KEY=...   # optional (Phase 3 TTS)
> ```
> `.env` = secrets only. Model selection, temperature, RPM, timeout, retry, and
> TTS defaults are configured in `src/agents/core/config.py` (`APP_CONFIG`), not
> via env vars.

---

## Phase 4 — Video Generation (Renderer)

### Standard Render Commands

```bash
# Full high-quality render of an existing job
python main.py --job jobs/job_0001 --template bar_chart -q h

# Low-quality smoke test (fast preview, ~5x faster)
python main.py --job jobs/job_0001 --template bar_chart -q l

# Skip SFX mixing (useful for timing/layout testing)
python main.py --job jobs/job_0001 --template bar_chart -q h --no_sfx

# Disable silence trimming between TTS segments
python main.py --job jobs/job_0001 --template bar_chart -q h --no-trim-silence

# Auto-open final video in OS viewer after render (Windows only)
python main.py --job jobs/job_0001 --template bar_chart -q h --open

# Custom FFmpeg binary path
python main.py --job jobs/job_0001 --template bar_chart -q h --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe"
```

### `main.py` — All CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--job` | **required** | Path to job directory (e.g., `jobs/job_0001`) |
| `--template` | from `job.json` | Override template ID. See **Template Registry** below. |
| `-q / --quality` | `h` | Manim quality: `l` (low/fast), `m` (medium), `h` (1080p), `p` (4K) |
| `--open` | `False` | Auto-open final video after render |
| `--no_sfx` | `False` | Skip SFX mixing even if `output/sfx_marks.json` exists |
| `--no-trim-silence` | `False` | Disable per-segment silence removal before concat |
| `--ffmpeg` | `ffmpeg` | Path to FFmpeg binary (falls back to PATH) |

### Template Registry

| Key | Scene Class | Template File |
|-----|-------------|---------------|
| `bar_chart` | `BarChartTemplate` | `src/templates/Bar_chart/bar_chart.py` |
| `butterfly_chart` | `ButterflyChart` | `src/templates/chart_folder/butterfly_chart.py` |
| `geo_universal` | `GeoUniversalMap` | `src/templates/map_chart/geo_universal.py` |
| `scan_race` | `CinematicLineRace` | `src/templates/line_chart/scan_race.py` |
| `sort_card` | `SortCardTribunalFinal` | `src/templates/Sort_card/sort_card.py` |
| `vs_card` | `VsCardFinal` | `src/templates/Vs_card/vs_card.py` |
| `donut_breakdown` | `DonutBreakdownFinal` | `src/templates/pie_chart/donut_breakdown.py` |

### Render a Single Manim Scene (Bypass Audio & Captions)

```bash
# Directly invoke Manim — skips voice concat, SFX, BGM, captions
python -m manim -qh src/templates/Bar_chart/bar_chart.py BarChartTemplate \
  --media_dir jobs/job_0001/media
```

> You must set `JOB_JSON_PATH` manually when bypassing `main.py`:
> ```powershell
> $env:JOB_JSON_PATH = "C:\MANIM_VIDEOS_CODE_TEMPALTE\jobs\job_0001\job.json"
> $env:JOB_DIR = "C:\MANIM_VIDEOS_CODE_TEMPALTE\jobs\job_0001"
> python -m manim -qh src/templates/Bar_chart/bar_chart.py BarChartTemplate --media_dir jobs/job_0001/media
> ```

---

## Captions Pipeline

### Standalone Caption Commands

```bash
# Generate ASS subtitle file only (no video burn)
python captions.py --job jobs/job_0001

# Generate ASS + burn into final.mp4
python captions.py --job jobs/job_0001 --burn

# Force generation even if captions.enabled=false in job.json
python captions.py --job jobs/job_0001 --force --burn

# Custom output paths
python captions.py --job jobs/job_0001 --burn \
  --ass-out jobs/job_0001/output/my_captions.ass \
  --video-in jobs/job_0001/output/final.mp4 \
  --video-out jobs/job_0001/output/final_captioned.mp4
```

### `captions.py` — All CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--job` | **required** | Job directory path |
| `--ffmpeg` | `ffmpeg` | FFmpeg binary path |
| `--ass-out` | from `job.json` | Override ASS output path |
| `--burn` | `False` | Also burn subtitles into the video |
| `--video-in` | from `job.json` | Input video for burn-in |
| `--video-out` | `output/final_captioned.mp4` | Captioned video output path |
| `--force` | `False` | Run even if `captions.enabled=false` |

---

## Timeline & Audio Diagnostics

```bash
# Verify audio durations match job.json timeline (strict mode — exits code 2 on mismatch)
python tools/audio_durations.py --job jobs/job_0001

# Relax mismatch tolerance (default is 0.35s)
python tools/audio_durations.py --job jobs/job_0001 --tolerance 0.50

# Auto-fix: write measured audio durations back into job.json timeline
python tools/audio_durations.py --job jobs/job_0001 --write-timeline
```

> The renderer requires alignment across 4 lists: `audio.segments`, `audio.order`, `timeline`, `script.json`.
> Any mismatch causes truncated or padded video. Run this tool when segments sound cut off.

---

## Phases 1–3 — Agent / Content Pipeline

### Master CLI (`src/cli/autoshorts.py`)

```bash
# Create a new empty job directory bucket
python -m src.cli.autoshorts new --template bar_chart

# Phase 1: Topic Discovery (Gemini ideation + Tavily search + AI scoring)
python -m src.cli.autoshorts phase1-discover --template bar_chart

# Phase 1: Data Extraction for a specific approved topic
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/<job_id> \
  --template bar_chart \
  --topic "Top AI Companies by Revenue 2024"

# Phase 2: Script Generation via LLM
python -m src.cli.autoshorts phase2 \
  --job jobs/auto/<job_id> \
  --template bar_chart \
  --persona savage_roast_master

# Phase 3: Audio Synthesis (TTS via ElevenLabs)
python -m src.cli.autoshorts phase3 \
  --job jobs/auto/<job_id> \
  --voice-id <elevenlabs_voice_id> \
  --model-id <elevenlabs_model>

# Handoff: Convert Phase 3 artifacts → renderer-ready job.json
python -m src.cli.autoshorts handoff --job jobs/auto/<job_id>

# Render only (Phase 4 via master CLI)
python -m src.cli.autoshorts render --job jobs/auto/<job_id> -q h

# Full pipeline: Phases 2 → 3 → Handoff → Render in one command
python -m src.cli.autoshorts run \
  --job jobs/auto/<job_id> \
  --template bar_chart \
  --persona savage_roast_master \
  --voice-id <voice> \
  --model-id <model> \
  -q h
```

### Granular Phase 1 CLI (`src/cli/phase1.py`)

```bash
# Interactive: discover + operator selection + auto extract
python -m src.cli.phase1 auto --niche "AI Industry" --top-n 5

# Discovery only (no extraction)
python -m src.cli.phase1 discover --niche "AI Industry" --top-n 5

# Approve a discovered candidate by index
python -m src.cli.phase1 approve --job-id <job_id> --index 2

# Direct extraction without discovery
python -m src.cli.phase1 extract \
  --topic "AI Revenue Rankings 2024" \
  --template bar_chart

# Inspect job output paths
python -m src.cli.phase1 inspect --job-id <job_id>

# View the pending topic queue
python -m src.cli.phase1 queue-show

# Reject candidates by index
python -m src.cli.phase1 reject --job-id <job_id> --indices "1,2,3"
```

---

## Compile & Smoke Checks

```bash
# Compile-check all core pipeline modules
python -m py_compile main.py captions.py
python -m py_compile src/sync/timeline.py src/sync/retention.py src/sync/job.py
python -m py_compile src/sfx/engine.py src/sfx/registry.py src/utils.py
python -m py_compile src/captions/ass_renderer.py src/captions/styles.py \
  src/captions/timeline_resolver.py src/captions/pipeline.py

# Compile-check all 7 templates
python -m py_compile \
  src/templates/Bar_chart/bar_chart.py \
  src/templates/chart_folder/butterfly_chart.py \
  src/templates/Sort_card/sort_card.py \
  src/templates/map_chart/geo_universal.py \
  src/templates/Vs_card/vs_card.py \
  src/templates/pie_chart/donut_breakdown.py \
  src/templates/line_chart/scan_race.py

# Fastest end-to-end smoke render (low quality, no SFX)
python main.py --job jobs/job_0001 --template bar_chart -q l --no_sfx
```

---

## Tests

```bash
# Phase 1 tests (no API keys needed — uses fakes)
python -m pytest tests/phase1 -v

# Phase 2 scripting tests
python -m pytest tests/phase2_scripting -v

# Full pipeline integration tests
python tests/pipeline/run_all.py

# Phase 3 offline end-to-end (no TTS API key needed)
python src/agents/phase3_audio/offline_e2e.py
```

---

## When Things Break

| Symptom | Diagnostic Command | Fix |
|---------|-------------------|-----|
| Audio truncated / long pad | `python tools/audio_durations.py --job jobs/job_0001` | `--write-timeline` or fix audio files |
| Caption misalignment | Check segment names across `script.json`, `audio.order`, `timeline` | Match all 4 name lists |
| FFmpeg error on render | Read the full stderr in the error message (`_run_ffmpeg` wrapper surfaces it) | Fix the specific FFmpeg filter issue |
| Phase rerun does nothing | Check `cat jobs/<id>/.pipeline_state.json` | Delete the completed step key to force re-run |
| ValidationError on import | `.env` file missing `TAVILY_API_KEY` or `GEMINI_API_KEY` | Add keys to `.env` |
| `job.json not found` | Verify path: `ls jobs/<id>/job.json` | Run `handoff` step or create manually |

---

# Video Generation Flow Breakdown

> Complete step-by-step lifecycle of:
> `python main.py --job jobs/job_0001 --template bar_chart -q h`

---

## Step 0 — Argument Parsing & Path Resolution

`main.py::main()` parses CLI args and:
- Resolves `job_dir = (repo_root / args.job).resolve()` → absolute path
- Loads and validates `job.json` from `job_dir/job.json`
- Determines `template_name` from `--template` flag or `job["template_id"]`
- Looks up template in registry → gets `scene_file` path and `scene_name`
- Validates that `scene_file` exists on disk

**Reads:** `jobs/job_0001/job.json`

---

## Step 1 — Manim Scene Render

```
subprocess: python -m manim -qh <scene_file> <scene_name> --disable_caching --media_dir jobs/job_0001/media
```

**Environment variables injected into Manim subprocess:**
- `JOB_JSON_PATH` = absolute path to `job.json`
- `JOB_DIR` = absolute path to job directory

**What happens inside the Manim scene (`construct()`):**

1. **Job load:** `src/sync/job.load_job()` reads `$JOB_JSON_PATH` → returns full job dict
2. **CSV load:** Reads `job["data_csv"]` → e.g., `jobs/job_0001/data/ai_stats.csv` → `names[]`, `values[]`, `meta{}`
3. **Timeline init:** `Timeline.from_dict(job["timeline"])` → segment budget tracking object
4. **SFXEngine init:** `SFXEngine(scene, job_dir)` → will record SFX cue timestamps during render
5. **Visual construction:** All `VGroup` builds, animations (`self.play()`), `hold_breathing()` pauses
6. **SFX flush:** At end of `construct()`, `sfx.flush()` writes `output/sfx_marks.json`

**Assets read during render:**

| Asset | Path | Used by |
|-------|------|---------|
| Job config | `jobs/job_0001/job.json` (via env var) | All templates |
| Data CSV | `jobs/job_0001/data/ai_stats.csv` | All templates |
| Fonts | `assets/fonts/Montserrat-*.ttf` | All templates |
| Images | `assets/images/*.jpg` | `vs_card`, `sort_card` |
| World SVG | `assets/svgs/world.svg` | `geo_universal` only |

**Writes:**
- `jobs/job_0001/media/videos/<quality>/BarChartTemplate.mp4`
- `jobs/job_0001/output/sfx_marks.json`

---

## Step 2 — Voice Segment Concatenation

**Source:** `job["audio"]["segments"]` + `job["audio"]["order"]`

For each segment name in `order`, resolves the audio path relative to `job_dir` and feeds into FFmpeg:

```
FFmpeg filter (silence trim ON by default):
[0:a]silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB:
       stop_periods=-1:stop_duration=0.02:stop_threshold=-50dB[tr0];
[1:a]silenceremove=...[tr1];
...
[tr0][tr1]...concat=n=N:v=0:a=1[a]
→ AAC 192kbps
```

Use `--no-trim-silence` to disable the `silenceremove` filter (raw concat only).

**Reads:** `jobs/job_0001/audio/hook.mp3`, `audio/setup.mp3`, ..., `audio/outro.mp3`  
**Writes:** `jobs/job_0001/output/_voice.aac`

---

## Step 3 — SFX Track Build *(optional)*

**Triggered when:** `job["sfx"]["enabled"] == true` **AND** `output/sfx_marks.json` exists

**Source:** `output/sfx_marks.json` — list of `{t, event, key, gain_db, rel_path, vol}`

**Process:**
1. Resolves each event key via `src/sfx/registry.SFX_LIBRARY` → absolute path in `assets/sfx/`
2. Per mark: `adelay={t*1000}ms:all=1, volume={vol*global_gain}`
3. All marks: `amix=inputs=N:duration=longest:dropout_transition=0, alimiter=limit=0.98`

**Reads:** `assets/sfx/ui_click_01.wav`, `assets/sfx/scan_beep_01.wav`, etc.  
**Writes:** `jobs/job_0001/output/_sfx_mix.aac`

---

## Step 4 — BGM Track Build *(optional)*

**Triggered when:** `job["bgm"]["enabled"] == true`

**Source:** `job["bgm"]` config — per-segment file paths, crossfade duration, gain values

**Process:**
1. Uses `job["timeline"]` to compute start time + duration for every segment
2. Per segment: loop BGM file (`-stream_loop -1`), trim to `seg_dur`, apply `afade` in/out, `adelay` to timeline offset, `volume` in dB
3. All segments `amix`-ed → trimmed to total video length

**Reads:** `jobs/job_0001/audio/bgm/*.mp3`  
**Writes:** `jobs/job_0001/output/_bgm.aac`

---

## Step 5 — Final Audio Mix

**Inputs:** `_voice.aac` + (optional) `_sfx_mix.aac` + (optional) `_bgm.aac`

**Filter graph (`preset="punchy"`):**
```
Voice:  aformat=stereo → aresample=44100 → pan=stereo → volume → acompressor(threshold=-18dB, ratio=3)
SFX:    aformat=stereo → aresample=44100 → highpass=80Hz → lowpass=14kHz → volume
BGM:    aformat=stereo → aresample=44100 → highpass=40Hz → lowpass=15kHz
        [Sidechain: voice signal ducks SFX/BGM via sidechaincompress when voice is active]
Final:  amix(normalize=0) → alimiter(limit=0.97)
```

**Writes:** `jobs/job_0001/output/_mix.aac`

---

## Step 6 — Video + Audio Mux

```bash
ffmpeg -i <manim_video.mp4> -i _mix.aac \
  -c:v copy -c:a aac -b:a 192k -shortest \
  output/final.mp4
```

Video is stream-copied (no re-encode). Audio is AAC 192kbps. `-shortest` trims to the shorter of the two streams.

**Reads:** `media/videos/<quality>/BarChartTemplate.mp4`, `output/_mix.aac`  
**Writes:** `jobs/job_0001/output/final.mp4`

---

## Step 7 — Captions *(optional)*

**Triggered when:** `job["captions"]["enabled"] == true`

Sub-pipeline via `src/captions/pipeline.run_captions_pipeline()`:

| Sub-step | Module | Action |
|----------|--------|--------|
| Script load | `script_loader.py` | Reads `script/script.json` → `{segment: {text: {lang: str}}}` |
| Timeline resolve | `timeline_resolver.py` | `job["timeline"]` → `[{name, start, end, dur}]` per segment; falls back to `ffprobe` |
| ASS render | `ass_renderer.py` | Builds `[Script Info]` + `[V4+ Styles]` + `[Events]` dialogue lines |
| Burn-in *(optional)* | `burn_in.py` | `ffmpeg -vf "ass='...'" -c:v libx264 -crf 18 -preset veryfast -c:a copy` |

**Reads:** `script/script.json`, `output/final.mp4`  
**Writes:** `output/subtitles.ass`, `output/final_captioned.mp4`

---

## Data Flow Diagram

```
jobs/job_0001/                          assets/
├── job.json ─────────────────────┐    ├── sfx/*.wav ──────────────┐
├── data/ai_stats.csv             │    ├── fonts/Montserrat*.ttf   │
├── audio/hook.mp3 ─────────┐     │    ├── images/*.jpg            │
├── audio/item_*.mp3 ───────┤     │    └── svgs/world.svg          │
├── audio/bgm/*.mp3 ────────┤     │                                │
└── script/script.json      │     │                                │
                             │     │                                │
                             ▼     ▼                                │
                     ┌────────────────────┐                        │
                     │   Manim Render     │ ◄──────────────────────┘
                     │  (scene.construct) │
                     └─────────┬──────────┘
                               │  media/videos/…/Scene.mp4
                               │  output/sfx_marks.json
                               ▼
           ┌──────────────────────────────────────────┐
           │         FFmpeg Audio Pipeline             │
           │  audio/*.mp3 ──→ concat ──→ _voice.aac   │
           │  sfx_marks + assets/sfx ──→ _sfx_mix.aac │
           │  audio/bgm/*.mp3 ──→ _bgm.aac            │
           │  _voice + _sfx + _bgm ──→ _mix.aac       │
           └──────────────────┬───────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   FFmpeg Mux       │
                    │  video + _mix.aac  │
                    └─────────┬──────────┘
                              │  output/final.mp4
                    ┌─────────▼──────────┐
                    │  Captions (opt.)   │ ◄── script/script.json
                    │  ASS + burn-in     │
                    └─────────┬──────────┘
                              │  output/final_captioned.mp4
                              ▼
                         ✅ COMPLETE
```

---

## Job Directory Structure

```
jobs/<job_id>/
├── job.json                    # ← All configuration (renderer reads this)
├── data/
│   ├── <template>_dataset.json # Phase 1 extraction output
│   ├── data_manifest.json      # Phase 1 manifest
│   └── <template>_data.csv     # Source CSV (renderer reads this)
├── audio/
│   ├── hook.mp3                # One file per segment in audio.segments
│   ├── item_1.mp3
│   ├── ...
│   └── bgm/                    # Background music (optional)
│       └── track.mp3
├── script/
│   ├── script.json             # Phase 2/3 internal script
│   └── engine_script.json      # Handoff-transformed script (captions use this)
├── output/                     # ← Created by renderer
│   ├── sfx_marks.json          # Written by Manim scene
│   ├── _voice.aac              # Step 2 intermediate
│   ├── _sfx_mix.aac            # Step 3 intermediate
│   ├── _bgm.aac                # Step 4 intermediate
│   ├── _mix.aac                # Step 5 intermediate
│   ├── final.mp4               # ← Final deliverable
│   ├── subtitles.ass           # Caption file (if enabled)
│   └── final_captioned.mp4    # Captioned version (if enabled)
├── media/                      # ← Created by Manim
│   └── videos/<quality>/
│       └── <SceneName>.mp4
└── .pipeline_state.json        # Phase 1–3 idempotency flags
```

---

## job.json Schema Reference

```json
{
  "job_id":      "string — unique identifier",
  "template_id": "string — one of the 7 template keys",
  "data_csv":    "relative path from job_dir to CSV file",

  "paths": {
    "output_dir":  "output",
    "media_dir":   "media",
    "sfx_marks":   "output/sfx_marks.json"
  },

  "video": { "w": 1080, "h": 1920 },

  "audio": {
    "segments": [{ "name": "hook", "path": "audio/hook.mp3" }],
    "order":    ["hook", "setup", "item_1", "winner", "outro"]
  },

  "timeline": {
    "hook": 2.53,
    "setup": 2.74,
    "item_1": 3.00
  },

  "gains": {
    "gain_voice": 1.0,
    "gain_sfx":   1.0,
    "gain_bgm_db": -20.0
  },

  "sfx": { "enabled": true, "gain": 1.0 },

  "bgm": {
    "enabled":     false,
    "mode":        "per_segment",
    "library_dir": "audio/bgm",
    "default":     { "path": "track.mp3", "gain_db": 0.0, "duck": true, "duck_amount": "strong" },
    "segments":    {},
    "crossfade":   0.25
  },

  "mix": { "preset": "punchy", "duck_sfx": false },

  "captions": {
    "enabled": false,
    "script":  { "path": "script/script.json", "source_lang": "en", "target_langs": ["en"] },
    "render":  {
      "format":  "ass",
      "burn_in": false,
      "style":   { "preset": "modern_clean", "safe_margin_px": 80, "max_lines": 2 },
      "tracks":  [{ "lang": "en", "mode": "plain", "position": "bottom" }]
    }
  },

  "output": {
    "final_mp4":      "output/final.mp4",
    "subtitles_ass":  "output/subtitles.ass",
    "captioned_mp4":  "output/final_captioned.mp4"
  }
}
```
