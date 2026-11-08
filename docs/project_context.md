# Project Context: AutoShorts (finance channel)

## Problem
The owner runs a faceless Hinglish finance channel on YouTube Shorts. Competitors now publish
high-quality, Claude-made motion-graphics videos; a video that looks like a filled-in template
will not hold viewers or go viral. Making each video by hand does not scale to daily posting.

## Objective
A first working version where the owner gives a topic and the whole pipeline
(topic -> verified data -> script -> voice -> Manim animation) runs end to end, without errors or
bugs, and produces a video that is ready to post. All seven templates (bar_chart, vs_card,
scan_race, donut_breakdown, butterfly_chart, geo_universal, sort_card) must reach that standard.
geo and sort_card are adapted to finance (India map, numeric values).

## Who it's for
The owner alone, for their own faceless finance channel (Hinglish, India-first audience).

## Scope
**In scope:**
- All seven templates polished to post-ready quality: hook in the first second, editing effects
  on beats, correct positions (nothing overlaps, nothing shifts), finance-trust look.
- The full pipeline from a topic to `output/final.mp4` (animation + voice), with audio/visual sync.
- Verified data with a visible source; numbers in ₹ lakh/crore where the data is Indian.
- Roman Hinglish scripts; the owner's ElevenLabs voice ("Abhishek - Conversational Hinglish").

**Out of scope:**
- Captions, SFX and BGM — the owner's separate post-production system adds them.
- Long-form videos, face-cam, any niche other than finance.
- Automatic upload/posting and thumbnails.

## Constraints
- Local machine: Windows laptop, ~8 GB RAM. Heavy or long renders go to RunPod (CPU pods).
- Paid APIs: OpenAI (LLM routes; billing must be active), Tavily (search), ElevenLabs (voice).
- Operational settings live in `src/agents/core/config.py`; secrets in `.env`.

## What already exists that's close
This repo already has every stage: Phase 1 discovery/extraction, Phase 2 scripting, Phase 3 TTS,
handoff, and the Manim renderer with seven templates plus the shared effects library `src/fx.py`.
The work is to finish and harden it, not to start a new project.

## Success signal
The owner gives a finance topic, runs the pipeline once, and gets a post-ready video with no
error, no bug and no manual fix, for any of the seven templates.

## Red lines
1. No wrong or unsourced number ever appears in a video.
2. No paid API call (OpenAI, Tavily, ElevenLabs) runs without telling the owner first.
3. No captions, SFX or BGM are added in this repo.
4. No render so heavy that it can crash the laptop (watch RAM; one render at a time).
5. No hacker/"leak" look comes back (finance needs trust).
