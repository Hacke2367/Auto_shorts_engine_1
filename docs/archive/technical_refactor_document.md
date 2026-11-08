# Technical Refactor Document

**Project:** `MANIM_VIDEOS_CODE_TEMPALTE`
**Phases:** 0-3 Refactor Plan
**Goal:** Implement "System Processing" HUD, Standardize Sync (0.0s Rule + Ghost Padding), Audio Pipeline Silence Trimming, and elevate Visuals (10/10 Standard).

---

## Phase 0: Audio Pipeline Silence Trimming (New)
**Files to Modify:** `main.py`
**Target Functions:** `concat_audio_ffmpeg`

### Logic Changes:
1. **Aggressive Silence Removal:** Apply FFmpeg's `silenceremove` filter to all voice segments *before* concatenation.
2. **Threshold:** Strip silence below `-50dB`.
3. **Duration:** Detect silence lasting longer than `0.02s`.
4. **Scope:** Apply `start_periods=1:start_duration=0.02:start_threshold=-50dB` and `stop_periods=-1:stop_duration=0.02:stop_threshold=-50dB`. This strips both the start and end of every segment.
5. **Goal:** Ensure a seamless, 10/10 transition between TTS segments without any CHOPS or dead-air gaps.

---

## Phase 1: `src/sync/retention.py` - HUD Telemetry Ghost
**Files to Modify:** `src/sync/retention.py`
**Target Classes/Functions:** `RetentionOverlay`, `hold_breathing`

### Logic Changes:
1. **Wipe legacy visual elements:** Remove the old edge streaks and message pills.
2. **Adaptive Brackets:** Create 4 corner brackets (L-shapes) anchored to the safe frame corners. Use a `ValueTracker` to apply breathing scale (1.0 -> 1.05) and opacity pulses (0.1 -> 0.4).
3. **Hex-Data Stream:** Add vertical strings of randomized hex data (`0x...`) anchored to the top-right and bottom-left bounds. These will scroll downwards via an updater.
4. **Bit-Oscillators:** Add a thin horizontal sine-wave rendering at the bottom, updating its phase/frequency based on `self._t`.
5. **Duration Check:** Add a hard `if duration < 0.5:` block inside `hold_breathing()` to instantly skip rendering complex UI components when the timeline padding is negligible.

---

## Phase 2: Global Timeline & Sync Standardization
**Files to Modify:** All templates (`bar_chart.py`, `donut_breakdown.py`, `sort_card.py`, `vs_card.py`, `butterfly_chart.py`, `scan_race.py`, `geo_universal.py` - already done)
**Target Areas:** `construct()`, main data loops.

### Logic Changes:
1. **The 0.0s Intro Rule:** 
   - Define `global_start_t0 = float(self.time)` as the *very first line* before `IntroManager.play_intro()` is called.
   - Set `hook_t0 = global_start_t0`.
2. **Delta-Time Refactor:** 
   - In every segment block, define `[seg]_t0 = float(self.time)`.
   - Before `hold_breathing`, run `TL.consume([key], float(self.time) - [seg]_t0)`.
   - Remove any manual additive math for `run_time`.
3. **Ghost Padding Block:** 
   - Add a post-loop check in every template: `for ghost_i in range(len(data), len(segments)):`
   - Use `hold_breathing` to absorb the exact remaining duration of the unused audio segment.

---

## Phase 3: Visual Audit & Improvement (Additive Only)
**Files to Modify:** `donut_breakdown.py`, `sort_card.py`, `vs_card.py` (and any other missing components).

### Logic Changes:
1. **Particle Injection:** Many templates (like `donut_breakdown` and `sort_card`) are missing the `make_floating_particles` call. Inject the utility and render it behind the main visual groups (z-index 5).
2. **Radiant Glow Layers:** Review grid and background instances in each template. Ensure every structural UI element has an underlying duplicated object with higher stroke width and 0.15 opacity for a "neon spill" effect.
3. **Motion Curves:** Standardize all component entrances/reveals to `rate_func=rf.ease_out_cubic` and all idle/ambient loops to `rate_func=rf.ease_in_out_sine`.

---

**Execution Flow:**
Since the TRD is now updated mapping the requested Audio Pipeline Silence Trimming to Phase 0, I will proceed with executing Phase 0, followed by Phase 1 -> 3.
