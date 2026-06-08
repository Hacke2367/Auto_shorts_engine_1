# Current Implementation Plan — Visual & Aesthetic Premium Pass

> **Status:** ✅ Approved — ready to execute (no code written yet).
> **Scope:** This is our immediate to-do list for the MVP visual track — **only** the Visual & Aesthetic
> Premium Pass.
> The **Motion B-Roll Strategy** now lives in its own file → [`motion_broll_plan.md`](./motion_broll_plan.md)
> (also MVP scope; build it *after* this pass so it inherits the upgraded brand layer).
> Longer-term ideas live in [`future_features_roadmap.md`](./future_features_roadmap.md) — out of scope
> until the channel is live and generating data.

---

## Context

The data pipeline, scripting, and TTS sync are solid. The goal now is to push the **Manim
visual templates + retention layer** from "good base visuals" to a *premium, breathtaking*
motion-graphics aesthetic — because the audience knows these are AI-generated and will judge
visual quality harshly.

Hard constraints (non-negotiable): **zero overengineering**, **do not break audio-visual sync
or core template logic**, **minimal code / maximum ROI**, and the engine must stay a **repeatable,
scalable content factory**.

### What the audit actually found (verified against *active* code)

A deep audit of all 7 templates, `retention*.py`, `utils.py`, and `config.py` produced one
important correction to the first-pass agent report: **the templates are more polished than they
looked.** The agent's "flat / linear-easing" findings mostly cited **dead commented-out legacy
blocks** (e.g. `bar_chart.py:529` `rate_func=linear` is inside a `#`-commented block; the *active*
hero reveal at `bar_chart.py:1322` already uses `rate_func=rf.ease_out_cubic`). Per-template hero
animations, glows, sheen, micro-settle, and chroma effects are already good — **we will not churn
them.**

The real, verified, high-ROI gaps are all in the **shared layer**, where one change upgrades all 7
templates at once:

1. **Dead-flat background.** Every template does only `self.camera.background_color = BACKGROUND_COLOR`
   (`#0A0A0A`). There is **no gradient/atmosphere mobject anywhere**. Flat near-black is the single
   biggest "cheap AI" tell.
2. **Flat particles.** `make_floating_particles` (`utils.py:216`) = single-color cyan dots, uniform
   linear upward drift, no twinkle, no depth parallax.
3. **Crude vignette.** `get_cinematic_overlay` (`utils.py:127`) fakes a vignette with a 140px black
   *stroke* on a rectangle — hard-edged, not a soft radial falloff. Scanlines are at opacity `0.02`
   (effectively invisible).
4. **Palette rough spots.** `NEON_YELLOW = #FFFF00` is harsh/cheap; `TEXT_SUB` is inconsistent
   (`#CCCCCC` in config vs `#B8B8B8` in the utils fallback).
5. **Typography is non-deterministic.** Bundled Montserrat TTFs are **never registered** with
   Manim → titles may be silently falling back to a default font on any machine without Montserrat
   OS-installed.
6. **Retention is well-built** (every layer/accent = one fail-safe, duration-gated updater with LIFO
   cleanup). It needs subtle tuning + one new cheap shared hook, **not** an overhaul.

### Decisions locked with the user
- **Scope:** Depth/atmosphere **+ palette polish + typography**.
- **Background motion:** **Subtle breathing drift** — one cheap updater (same cost class as the
  existing `_add_subtle_flicker`).
- **Rollout:** **All 7 templates in one pass.**

### The sync-safety guarantee (why this can't break timing)
Every change below adds mobjects via `scene.add(...)` (instant) and/or attaches lightweight
`updater` callbacks. **No new `self.play(..., run_time=...)` calls and no changes to any
`TL.consume(...)` / `hold_breathing(...)` duration math.** Segment timing is therefore provably
untouched — identical to how the existing particles/flicker already work.

---

## Plan

### Part A — Shared "cinematic background" helper (the flagship, ~80% of the ROI)

Add **one** new helper to `src/utils.py` and call it once per template.

`add_cinematic_background(scene, accent=Brand.CYAN, breathing=True)`:
- **Base gradient:** full-frame `Rectangle` (`frame_width+2 × frame_height+2`), `set_color_by_gradient`
  top→bottom from a subtle cool charcoal (`#0E1116`) to near-black (`#050608`). Kills the dead-flat
  look. `z_index = -100`, `stroke_width=0`.
- **Radial brand glow:** 2–3 large concentric `Ellipse`s filled with `accent` at very low opacity
  (`~0.06 → 0.03`), centered slightly above frame center (the content focal zone) → a soft
  brand-tinted "pool of light." Layered ellipses approximate a gaussian glow with **zero** per-frame
  cost. `z_index = -90`.
- **Breathing drift (the one allowed updater):** a single updater slowly oscillates the glow group's
  opacity (`~0.04 ↔ 0.07`) and nudges its position by a few hundredths via `np.sin(scene.time * ~0.4)`.
  This is the "dynamic background shift," kept strictly in the flicker cost class.
- Returns the VGroup (so callers could remove it; not required).

**Wire-up (pattern, applied to all 7):** immediately after each template sets its camera background,
add one line — `add_cinematic_background(self, accent=<template accent>)`. Call sites:
- `src/templates/Bar_chart/bar_chart.py:876`
- `src/templates/chart_folder/butterfly_chart.py:381`
- `src/templates/pie_chart/donut_breakdown.py:134`
- `src/templates/line_chart/scan_race.py:158`
- `src/templates/map_chart/geo_universal.py:168`
- `src/templates/Sort_card/sort_card.py:710`
- `src/templates/Vs_card/vs_card.py:731`

`accent` is each template's existing primary color, so backgrounds stay on-brand per template.

### Part B — Particle upgrade (one shared function, all templates benefit)

Enhance `make_floating_particles` (`src/utils.py:216`) — keep the signature backward-compatible:
- **Twinkle:** extend the existing single drift updater so each particle's opacity gently pulses on a
  per-particle phase offset (precomputed once; updater stays O(n) simple-sine — same cost class).
- **Depth parallax:** assign particles to 2 depth bands (near = larger/brighter/faster, far =
  smaller/dimmer/slower) for a subtle 3D feel.
- **Color variety:** allow a small accent palette (default = brand cyan + a touch of the template
  accent) instead of one flat color.
- **Soft edge wrap:** when a particle drifts past the top safe edge, recycle it to the bottom (prevents
  the cloud from emptying out on longer videos). Still one VGroup updater, no new mobjects per frame.

### Part C — Vignette / overlay refinement (shared)

In `get_cinematic_overlay` (`src/utils.py:127`):
- Replace the hard 140px-stroke vignette with a soft radial-falloff approximation (a few stacked,
  oversized, low-opacity dark `Ellipse`/`Rectangle` rings → gradient-like edge darkening). Static.
- Bump scanline opacity from `0.02` to `~0.05` so they read as intentional premium texture instead of
  being invisible (still subtle). No count change (stays 46 static lines).

### Part D — Palette polish (central, ripples to all 7 automatically)

In `src/config.py` `Theme` (templates import `Theme`; `Brand` derives from it — so editing here
propagates everywhere with no per-template edits):
- `NEON_YELLOW`: `#FFFF00` → a richer amber-gold (e.g. `#FFC74A`). Softens the one harsh value used in
  palettes / `GROUP_COLORS`.
- `TEXT_SUB`: unify to a single cool premium grey (e.g. `#AEB7C2`) and mirror the same value in the
  `utils.py` fallback `Theme` so both paths agree.
- Optionally enrich `C_BAR_GRADIENT` end-stop for a touch more vibrancy (low priority; only if it reads
  better on a test render).

### Part E — Typography: register fonts + premium display face for titles

**E1 — Register bundled fonts (reliability win, do first).** In `src/config.py` after `FONTS_DIR`
(line ~90), register the bundled TTFs at import via `manimpango.register_font(...)` wrapped in
try/except. This guarantees `font="Montserrat"` always resolves to the bundled file regardless of OS
install state — may itself visibly upgrade every title that was silently falling back.

**E2 — Premium display font for hero titles.** Add a `FONT_DISPLAY` constant (default recommendation:
**Space Grotesk** for a premium-tech feel that pairs with Montserrat; **Anton** is the high-punch
alternative). Bundle its OFL `.ttf` into `assets/fonts/`, register it in E1's loop, and swap **only the
single hero/title `Text(...)`** in each template's active `construct` to `font=FONT_DISPLAY`. Body/label
text stays Montserrat. Implement with graceful fallback to Montserrat Bold if the file is absent, so a
missing TTF can never break a render.

### Part F — Retention: subtle tuning + one new cheap shared hook

- **Tuning (`src/sync/retention_base.py`):** nudge Living-Data glow `glow_max_opacity` `0.18 → 0.20`
  and let stroke breathe a hair wider. Bump confidence-tick `fill_opacity` `0.50 → 0.60`. Parameter-only;
  no new updaters.
- **New shared hook (opt-in, render-cheap):** add a "focus aura" — a soft accent-tinted radial glow that
  fades in behind the active `focus` mobject during a hold (reuses the Part A glow primitive, gated by the
  same `duration` thresholds and LIFO cleanup as existing layers). One updater, fully fail-safe, off by
  default so no existing call changes behavior unless we opt a template in.

### Part G — (Optional) efficiency win, not aesthetic

`get_cinematic_overlay`'s HUD timer (`utils.py:165`) rebuilds a full `Text` mobject **every frame** via
`.become()` for the entire video. Throttle it to only rebuild when the displayed `MM:SS` actually changes.
Pure render-time reduction, no visual change. Include only if touching that function for Part C anyway.

---

## Guardrails (enforced throughout)
- **No** new `self.play(run_time=...)` and **no** edits to `TL.consume` / `hold_breathing` durations → sync
  is mathematically unchanged.
- New per-frame updaters: **at most one** (background breathing) + the opt-in focus aura. Everything else
  is static mobjects. This stays within the existing flicker/particle cost envelope — no render-time spike.
- All new shared helpers wrapped defensively; a failure degrades to the current look, never crashes a render.
- Do not touch the already-polished active hero animations, the legacy commented blocks, or `src/utils.py`'s
  legacy header note.

## Critical files
- `src/utils.py` — **new** `add_cinematic_background()`; upgrade `make_floating_particles()` (216); refine
  `get_cinematic_overlay()` vignette/scanlines (127); sync `TEXT_SUB` fallback.
- `src/config.py` — `Theme` palette tweaks (31–82); `manimpango` font registration after `FONTS_DIR` (90);
  add `FONT_DISPLAY`.
- The 7 template files — one `add_cinematic_background(self, ...)` call at each camera-bg line (listed in
  Part A) + one hero-title `font=FONT_DISPLAY` swap each.
- `src/sync/retention_base.py` — glow/tick parameter nudges; opt-in focus-aura hook.
- `assets/fonts/` — add the chosen display `.ttf`.

## Verification (end-to-end)
1. **Compile smoke check** (project standard) on every touched file:
   `python -m py_compile src/utils.py src/config.py src/sync/retention_base.py src/templates/**/<file>.py`
2. **Render eyeball** on at least 2 visually different templates (fast quality), e.g.:
   `python main.py --job jobs/job_0001 --template bar_chart -q l` and `--template donut_breakdown`.
   Confirm: gradient background + brand glow visible, particles twinkle/parallax, titles render in the new
   display font, palette reads richer, no z-index regressions (content/HUD still on top).
3. **Sync proof:** `python tools/audio_durations.py --job jobs/<id>` before/after → segment durations and
   timeline must be **identical** (we added no timed animations).
4. **Font-fallback proof:** confirm titles change between pre/post (verifies registration took effect); confirm
   render still succeeds with the display `.ttf` temporarily removed (verifies graceful fallback).
5. Run the relevant template/pipeline tests if any cover rendering hooks; otherwise compile + render is the gate.