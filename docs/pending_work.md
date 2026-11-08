# Pending Work

Last updated: 2026-11-09
Branch: `finance_launch`
Current focus: plan step 9 (layout lock), then the RunPod visual batch for steps 5-9.

## Next up
1. **Resume point.** Plan step 9, In progress, branch `finance_launch` (stay on it). Skills: `/gate`
   before commits, `/handoff` at session end, `/ship` once the owner has seen the RunPod batch.
   - Left in step 9: probe every template's busiest frames for overlaps / Shorts safe zones
     (bottom ~20% UI band). Probe tools: copy the skip-mode sync probe pattern from item 2 below;
     a mid-video frame can be saved from a wrapped `sync_hold` with
     `scene.renderer.update_frame(scene, ignore_skipping=True)` + `scene.renderer.camera.get_image()`.
   - Pre-existing, not fixed: donut hook overruns its slot by 0.79 s and slice3 by 0.13 s (absorbed
     at the next anchor, same at HEAD 1ed3af1a).
   - Not done (out of plan scope): butterfly and sort_card have no cold open / loop card; butterfly
     has no `set_source` (its CSV parser reads only P1/P2).
2. **Owner: RunPod visual batch** (steps 5-9, one render each; SFX/captions are now off by default):
   - `python main.py --job jobs/job_0001/job_bar_chart_3 --template bar_chart -q h`
   - `python main.py --job jobs/donut_job/job_donut_breakdown_1 --template donut_breakdown -q h`
   - `python main.py --job jobs/butterfly_job/job_butterfly_chart_1 --template butterfly_chart -q h`
   - `python main.py --job jobs/sort_job/job_sort_card_1 --template sort_card -q h`
   - `python main.py --job jobs/geo_job/job_geo_universal_2 --template geo_universal -q h`
   Look for: winner flash/shake (bar, butterfly), donut centre % rolling up, sort_card HITS/FLOPS
   bins + pill below the underline, geo decimals (33.5%) and the slow map sweep.
   sort_card's value pill only shows when the CSV has a `Value` column (old job has none).
3. Plan step 4 (scan_race 15 fps memory growth): diagnose on RunPod. Notes from the last session:
   3 fps full run is fine and mobject count stays flat; suspect the frame writer queue or Cairo
   buffers. Sweep zero-byte SVGs after any killed render (`find jobs -name "*.svg" -size 0 -delete`).
4. Step 7 India map after H-5; step 10 after H-1.

## Waiting on the owner
H-1 OpenAI billing, H-2 Gemini key, H-3 brand name, H-4 two historical prices, H-5 India map asset
(`docs/human_decision.md`).
