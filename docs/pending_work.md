# Pending Work

Last updated: 2026-11-09
Branch: `finance_launch`
Current focus: plan step 4 (scan_race 15 fps memory), then step 5.

## Next up
1. **Resume point.** Plan step 4, Todo, on branch `finance_launch` (stay on it; no `/start_work`
   needed). Skills: `/gate` before commits, `/handoff` at session end, `/ship` when steps 3-9 are
   reviewable. Read first: `docs/project_context.md`, `docs/development_plan.md`, then
   `src/templates/line_chart/scan_race.py`.
   - scan_race at 15 fps grows private memory ~1 GB per 20 s on this laptop and was killed twice;
     a full run at `--frame_rate 3` finishes and its mobject count stays flat (~800). Next test:
     watch the manim child's private memory at 15 fps for 60 s, then suspect the frame writer
     queue (`scene_file_writer.listen_and_write`) or Cairo per-frame buffers. Fallback: RunPod.
   - Before any render: check free RAM (laptop is 7.7 GB). Close WSL (`wsl --shutdown`) and other
     heavy jobs first; one render at a time.
   - Always sweep zero-byte SVGs after a killed render (`find jobs -name "*.svg" -size 0 -delete`).
   - `manim -n a,b` probes hang at exit (writer thread): wrap them in `timeout`.
   - Sync check without rendering: run the scene under `tempconfig` with `skip_animations` AND
     `save_last_frame=True` (manim 0.19 only skips when save_last_frame is set), wrap
     `Timeline.consume` / the module's `sync_hold`, compare `scene.time` to `TL.target_elapsed`.
2. Owner visual check: re-render donut after the hook fix
   (`python main.py --job jobs/donut_job/job_donut_breakdown_1 --template donut_breakdown -q l --no_sfx`).
3. Plan step 5: remove caption burn + SFX mix from the default output (D-4).
4. Plan steps 6-9, then step 10 once H-1 is resolved.

## Waiting on the owner
H-1 OpenAI billing, H-2 Gemini key, H-3 brand name, H-4 two historical prices (`docs/human_decision.md`).
