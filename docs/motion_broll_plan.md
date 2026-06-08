# Motion B-Roll Strategy — Implementation Plan

> **Status:** ✅ In MVP scope — plan only (no code written yet).
> **Build order:** Implement this *after* the
> [Visual & Aesthetic Premium Pass](./current_implementation_plan.md), so B-roll inherits the upgraded
> brand layer (background, palette, `FONT_DISPLAY`) and the whole video shares one polished universe.
> Longer-term ideas: [`future_features_roadmap.md`](./future_features_roadmap.md).

---

## Goal & guiding principle

Break visual monotony with **procedural, on-brand motion-graphics B-roll** (kinetic typography,
branded transitions, abstract data-flow underlays) — **never stock footage**, which would clash with
the synthetic neon aesthetic. B-roll is an **additive compositing layer**, architecturally modelled on
the existing **captions** pipeline (`captions.py` → ffmpeg post-process, optional, off by default,
core renderer untouched).

> ### 🔒 The sync-safety law (read this first)
> **The main render's audio track is the immutable master clock.** B-roll is composited **only as a
> visual `overlay`** keyed to timestamps we read from the existing `job.json["timeline"]` and
> `output/sfx_marks.json`. We **never re-cut, re-time, concat, or trim** the main video's audio or
> duration. Overlaying pixels on top of an unchanged A/V stream **cannot desync** by construction.
> (True timeline *inserts* — which would shift audio — are explicitly **out of scope for MVP**.)

---

## Architecture at a glance

```
[ existing pipeline ]                         [ NEW additive B-roll layer ]
jobs/<id>/output/final_captioned.mp4  ──┐
jobs/<id>/job.json  (timeline)          ├──►  tools/compose_broll.py  ──►  output/final_broll.mp4
jobs/<id>/output/sfx_marks.json         │        (ffmpeg overlay only)
assets/broll/  (pre-rendered library) ──┘
src/broll/scenes/  (Manim generators) ──► assets/broll/<tag>/*.mov (alpha)
```

- **New code lives in its own corner:** `src/broll/` (Manim generators) + `tools/compose_broll.py`
  (ffmpeg compositor) + `assets/broll/` (the rendered, tagged clip library). **Zero edits** to
  `main.py` or the 7 templates.
- **Reuses the brand layer:** B-roll scenes import `src/utils.py` (`Brand`, `Theme`, fonts, particles)
  so they automatically inherit the Visual Premium Pass look — one consistent universe.

---

## Step 1 — B-roll Manim generator scenes  (`src/broll/scenes/`)

Build a small set of **parametric** Manim `Scene`s. Each takes inputs (text, accent, duration) and
renders short clips. All reuse `Brand`/`Theme`/`FONT_DISPLAY` from the Visual Pass for consistency.

| Scene | Purpose | Background | Typical len |
|---|---|---|---|
| `KineticStinger` | Full-screen big-text/number slam for **hook / headline stat / outro CTA** (word-by-word + number-slam variants) | full-frame OR alpha | 1.5–3.0 s |
| `TransitionWipe` | Glitch / scanline / radar sweep between chart segments | **alpha** | 0.4–0.8 s |
| `DataFlowUnderlay` | Loopable particle / network-pulse stream to sit *under* narration | **alpha** | 3–5 s loop |
| `OdometerSlam` | Number rapidly counting up to the headline figure | alpha | 1.0–2.0 s |
| `SourceCard` | Animated "SOURCE: … 2025" credibility beat | alpha | 1.0–1.5 s |

**Transparency:** render overlay clips with Manim's transparent flag so they carry an alpha channel:
```
python -m manim -t -qh src/broll/scenes/transition_wipe.py TransitionWipe
# -t / --transparent → .mov (qtrle/prores4444) with alpha, ffmpeg-overlay ready
```

**Keep them light:** these are short and reuse existing cheap primitives (particles, glows). No new
heavy physics — same "no render spike" rule as the Visual Pass.

## Step 2 — Pre-render the reusable library  (`tools/build_broll_library.py`)

The content-factory move: **render generic clips ONCE, reuse forever** (near-zero marginal cost).
- A builder script renders the *topic-agnostic* clips — every `TransitionWipe` style, the
  `DataFlowUnderlay` loops, the iconography set — into `assets/broll/<tag>/<name>.mov`.
- Emit `assets/broll/manifest.json` tagging each clip:
  `{ "name", "file", "type", "duration_s", "has_alpha", "tags": ["transition","glitch"] }`.
- **Per-video clips** (kinetic stingers needing the actual hook text / headline number) are rendered
  on demand at compose time — they're tiny and short.

## Step 3 — Resolve placement times from existing data  (no new timing system)

We already produce everything needed to place B-roll on the master clock:
- `job.json["timeline"]` → per-segment durations (reuse `src/sync/timeline.py :: Timeline.from_dict`
  and the resolver logic in `tools/audio_durations.py` / `src/captions/timeline_resolver.py` to turn
  segment names into **absolute start/end seconds**).
- `output/sfx_marks.json` → exact cue timestamps (e.g. the `winner` impact) for precise hits.

So a placement like *"transition wipe at the boundary between `setup` and `item_1`"* or *"hook stinger
over the `hook` segment"* resolves to concrete seconds with the data already on disk.

## Step 4 — The B-roll plan  (`broll_plan.json`, per job)

A simple declarative list (hand-authored for MVP; AI-scripted later) describing what goes where:
```json
{
  "entries": [
    { "clip": "stinger_hook",       "mode": "overlay", "anchor": "segment:hook",        "opacity": 1.0 },
    { "clip": "transition_glitch_1","mode": "overlay", "anchor": "boundary:setup>item_1","opacity": 1.0 },
    { "clip": "underlay_dataflow",  "mode": "overlay", "anchor": "segment:setup", "opacity": 0.35 },
    { "clip": "stinger_outro_cta",  "mode": "overlay", "anchor": "segment:outro",        "opacity": 1.0 }
  ]
}
```
- `anchor` is resolved to `start_s` / `duration_s` by Step 3 (segment span, or a named `sfx` mark).
- **MVP default plan = 3 placements:** hook stinger + one mid transition + outro CTA. Minimal, maximal
  impact. Underlays are a fast-follow.

## Step 5 — The compositor  (`tools/compose_broll.py`, ffmpeg overlay only)

A standalone script (mirrors `captions.py`'s role) that takes the finished main video + the resolved
plan and produces `output/final_broll.mp4`:
- For each entry, an ffmpeg `overlay` with time-gating, e.g.:
  ```
  [0:v][1:v] overlay=enable='between(t,START,END)':x=...:y=... [v]
  ```
  chained per clip; alpha clips blend natively; `opacity` via `format=...,colorchannelmixer=aa=`.
- **Audio is passed through with `-c:a copy`** (stream-copied, never re-encoded/re-timed) → audio is
  byte-for-byte the original. This is the concrete enforcement of the sync-safety law.
- `-t` of output is **not** changed; total duration stays identical.

## Step 6 — Pipeline wiring (optional, additive, OFF by default)

- Expose as a separate entrypoint `broll.py --job jobs/<id>` (exactly like `captions.py`), OR an
  opt-in `--broll` flag on `main.py` that runs **after** render + captions.
- Default = disabled, so the existing render path is 100% untouched. Producing B-roll is always an
  explicit, additional step. Output deliverable: `output/final_broll.mp4`.

## Step 7 — Verification

1. **Audio integrity (the critical one):** `ffprobe` the audio stream of `final_captioned.mp4` vs
   `final_broll.mp4` → must be identical (same codec, duration, sample count). `-c:a copy` guarantees it.
2. **Duration unchanged:** total video length identical before/after.
3. **Placement accuracy:** spot-check that each overlay appears at its intended segment/mark time.
4. **A/B watch:** confirm the B-roll reads as on-brand and *reduces* monotony without clutter.
5. **Compile smoke check** on all new `src/broll/*` + `tools/compose_broll.py`.

## Build order (suggested)
1. `KineticStinger` + `TransitionWipe` scenes (the two highest-ROI clip types).
2. `tools/compose_broll.py` overlay compositor + `broll.py` entrypoint.
3. Time-resolution helper (reuse caption/timeline resolvers).
4. MVP 3-placement default plan; render one job end-to-end; verify audio integrity.
5. Add `DataFlowUnderlay` + `OdometerSlam` + `SourceCard` and the pre-rendered library builder.

> **Dependency note:** Build B-roll **after** the Visual & Aesthetic Premium Pass, so the
> stingers/transitions inherit the upgraded brand layer (background, palette, `FONT_DISPLAY`) and the
> whole video — chart *and* B-roll — shares one polished universe.