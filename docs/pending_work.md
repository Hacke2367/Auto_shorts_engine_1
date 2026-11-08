# Pending Work

Last updated: 2026-11-09
Branch: `finance_launch`
Current focus: plan step 3 (verify cold open/loop on bar, donut, scan_race) and step 4 (scan_race memory).

## Next up
1. **Resume point.** Plan step 3, In progress, on branch `finance_launch` (stay on it; no
   `/start_work` needed). Skills: `/gate` before commits, `/handoff` at session end, `/ship` when
   steps 3-9 are reviewable. Read first: `docs/project_context.md`, `docs/development_plan.md`,
   `src/fx.py`, then `src/templates/line_chart/scan_race.py`.
   - Render-check bar_chart (`jobs/job_0001/job_bar_chart_3`) and donut
     (`jobs/donut_job/job_donut_breakdown_1`) one at a time at `-q l`; their CSVs already carry
     HOOK_*/OUTRO_* meta. Check frames with an ffmpeg contact sheet.
   - Step 4: scan_race at 15 fps grows private memory ~1 GB per 20 s on this laptop and was killed
     twice; a full run at `--frame_rate 3` finishes and its mobject count stays flat (~800). Next
     test: watch the manim child's private memory at 15 fps for 60 s, then suspect the frame
     writer queue (`scene_file_writer.listen_and_write`) or Cairo per-frame buffers. Fallback:
     render on RunPod.
   - Always sweep zero-byte SVGs after a killed render (`find jobs -name "*.svg" -size 0 -delete`).
   - `manim -n a,b` probes hang at exit (writer thread): wrap them in `timeout`.
2. Plan step 5: remove caption burn + SFX mix from the default output (D-4).
3. Plan steps 6-9, then step 10 once H-1 is resolved.

## Waiting on the owner
H-1 OpenAI billing, H-2 Gemini key, H-3 brand name, H-4 two historical prices (`docs/human_decision.md`).
