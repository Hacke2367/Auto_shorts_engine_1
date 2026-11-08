# Decisions

## D-1 (2026-11-03) Single niche: finance, Hinglish, India-first
Owner decision. Chart engines kept, hacker/leak skin replaced. Plan: `~/.claude/plans/pasted-content-id-3a71-mein-chatha-linear-beacon.md`.

## D-2 (2026-11-06) Hook-first: no brand intro card
`INTRO_ENABLED = False` in `src/config.py`; title/data on screen at t=0. Commit b1d3d9c5.

## D-3 (2026-11-08) One shared effects library, driven by CSV meta
`src/fx.py` holds count-up, shake, slam, pop, flash, fly, progress pips, cold open, loop card.
Templates opt in through CSV meta keys `HOOK_STAT/HOOK_LINE/HOOK_SUB` and `OUTRO_Q/OUTRO_SUB`.
Effects only on beats (reveal, twist, winner), never on every line.

## D-4 (2026-11-08) Captions, SFX and BGM are out of this repo
Owner decision: the owner's separate system adds them. This repo delivers animation + voice.

## D-5 (2026-11-08) Every template anchors segment ends to the master clock
`sync_hold` / absolute `TL.target_elapsed` instead of relative `TL.remaining()` holds, so an
animation overrun cannot drift later segments. Done for vs_card, bar, donut, scan_race, butterfly.

## D-6 (2026-11-09) devsystem tracking, tier standard
Owner decision. Context: `docs/project_context.md`. Config: `.claude/devsystem.json`.
