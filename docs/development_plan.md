# Development Plan

Goal and "done": `docs/project_context.md`. Statuses: Todo / In progress / Blocked / Done.

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Finance skin: palette, HUD source label, `fmt_value`, hook-first (no intro card), niche + source policy | Done | commit b1d3d9c5 |
| 2 | Editing-effects library `src/fx.py` + vs_card hero edit (cold open, fly-in cards, count-up values, "+1" fly, progress pips, loop card, layout above Shorts UI band) | Done | verified render `jobs/vs_job/job_vs_card_2`; D-3 |
| 3 | Cold open + loop card on bar_chart, scan_race, donut; drift-free `sync_hold` in scan_race + butterfly; scan_race per-frame text cache | In progress | code done, compiled; renders not yet verified |
| 4 | scan_race 15 fps render memory growth (private memory 6.5 -> 8.2 GB in 40 s, killed) | Todo | root cause unknown; 3 fps full run is fine; see pending_work |
| 5 | Stop adding captions/SFX in the default output (handoff `burn_in`, main.py SFX mix) | Todo | red line #3, D-4 |
| 6 | Editor pass (count-up, punch-ins, beats) for bar_chart, donut, butterfly | Todo | reuse `src/fx.py` |
| 7 | geo_universal for finance: India map, decimals, motion during long holds | Todo | |
| 8 | sort_card for finance: numeric values, drop "tribunal" tone, real bins | Todo | |
| 9 | Layout lock: per-template frame probes, no overlaps, Shorts safe zones | Todo | |
| 10 | A-to-Z pipeline run per template (topic -> post-ready video, no manual fix) | Blocked | OpenAI billing inactive (H-1) |
