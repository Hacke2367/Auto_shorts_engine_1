PROJECT STATE: Auto_shorts_engine_1
Last Updated: 21-Feb-2026
Project Type: Production-Grade Automated Shorts/Reels Generation Engine (Custom Python Pipeline)

1. Project Vision & Philosophy
Goal: To generate premium, high-retention, "faceless" infographic shorts in bulk.

Philosophy: "Build > Buy/Wrapper". Deep custom engineering, no cheap API wrappers. Production-level code (10/10 Rule), modularity, and pixel-perfect sync.

Aesthetic: Tech/Cyberpunk, "BIGDATA LEAK" theme, glassmorphism, glowing neons, and dynamic HUDs.

2. Core Architecture
The engine is decoupled into three strict layers:

Input Layer: Driven by job.json (configs, audio timings) and .csv files (raw stats, metadata).

Visual Engine (Manim): Renders the video using custom 10/10 templates (bar_chart, donut_breakdown, geo_universal, etc.).

Audio & Muxing Orchestration (main.py): Uses strict FFmpeg commands to concatenate TTS, mix frame-perfect SFX, add BGM with sidechain ducking, and mux the final output.

3. Engineering Master-Logics (The Secret Sauce)
Dynamic Audio-Video Sync (Delta Time): We DO NOT use hardcoded run_time. We calculate actual elapsed time using self.time - t0 and limit animations via fractions of the allocated audio segment (TL.seg_total).

The Retention Buffer (retention.py): The ultimate fix for audio-video length mismatch. If animation finishes before the audio segment, hold_breathing kicks in—keeping the UI alive with subtle idle animations (scans, pulses) so the video never freezes.

Event-Driven SFX (SFXMarksWriter): The Manim engine does not play audio. It writes a precise sfx_marks.json file logging exact frame timestamps (t) for hits, sweeps, and pops. main.py later uses FFmpeg to delay and mix these perfectly.

Custom Math > Libraries: Used custom 2D bounding-box repulsion math for labels, and custom Lat/Lon map projections instead of heavy GIS dependencies.

4. Current Templates Library (Verified & Delta-Synced)
bar_chart.py (Base Standard)

butterfly_chart.py

scan_race.py (Cinematic Line Race)

geo_universal.py (Map/Alliance Logic)

donut_breakdown.py (Pie/Donut with AABB overlap resolver)

sort_card.py (Tribunal Sort with Async Scanner State)

5. Current Project Status & Immediate Bottleneck
Status: [To be updated by user]

Current Issue: [To be updated by user]

Next Milestone: [To be updated by user]