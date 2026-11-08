# Development Plan

Goal and "done": `docs/project_context.md`. Statuses: Todo / In progress / Blocked / Done.

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Finance skin: palette, HUD source label, `fmt_value`, hook-first (no intro card), niche + source policy | Done | commit b1d3d9c5 |
| 2 | Editing-effects library `src/fx.py` + vs_card hero edit (cold open, fly-in cards, count-up values, "+1" fly, progress pips, loop card, layout above Shorts UI band) | Done | verified render `jobs/vs_job/job_vs_card_2`; D-3 |
| 3 | Cold open + loop card on bar_chart, scan_race, donut; drift-free `sync_hold` in scan_race + butterfly; scan_race per-frame text cache | Done | bar + donut `-q l` renders checked (contact sheets); scan_race cold open/loop via `-s` probes; segment-end drift 0.00 s in scan_race + butterfly (skip-mode probe); donut hook show-through fixed |
| 4 | scan_race 15 fps render memory growth (private memory 6.5 -> 8.2 GB in 40 s, killed) | Todo | root cause unknown; 3 fps full run is fine; see pending_work |
| 5 | Stop adding captions/SFX in the default output (handoff `burn_in`, main.py SFX mix) | Done | opt-in `--sfx` / `--captions` in `main.py`; handoff writes both off (D-4) |
| 6 | Editor pass (count-up, punch-ins, beats) for bar_chart, donut, butterfly | Done | winner flash/shake/pop (bar, butterfly), donut centre % count-up + leader beat, butterfly score-ring pop + name slam; `fx.pop` safe under play rate_func; drift 0.00 s bar/butterfly. Visual check on RunPod pending |
| 7 | geo_universal for finance: India map, decimals, motion during long holds | Blocked | decimals (`fmt_value`, no more int rounding), card count-up, map sweep during holds, ticker shrink-only, `set_source` done; India states map waits on H-5 |
| 8 | sort_card for finance: numeric values, drop "tribunal" tone, real bins | Done | bins from TITLE, optional `Value` column (schema + CSV + count-up pill), neutral copy, `set_source`, sync_hold + exact dwell reserve (drift 0.00 s) |
| 9 | Layout lock: per-template frame probes, no overlaps, Shorts safe zones | In progress | done: bar TOP 3 pill (tick labels fade), sort pill fits header gap, geo ticker text. Left: full per-template probe sweep |
| 10 | A-to-Z pipeline run per template (topic -> post-ready video, no manual fix) | Blocked | OpenAI billing inactive (H-1) |
