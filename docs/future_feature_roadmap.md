# Future Features Roadmap — BACKLOG

> **Status:** 🅿️ Parked / Backlog. **Do NOT build any of this during the MVP.**
> Revisit **once the YouTube channel is live and generating real performance data.**
> Building these now (SaaS backend, Vision-QA loops, GenAI assets) would be massive over-engineering
> before product-market fit.
>
> The active MVP work is split across [`current_implementation_plan.md`](./current_implementation_plan.md)
> (Visual & Aesthetic Premium Pass) and [`motion_broll_plan.md`](./motion_broll_plan.md) (Motion B-Roll).
> Everything below is for *after* those ship and the channel proves traction.

**Why park it:** the channel isn't launched. The fastest path to learning is shipping watchable videos,
not infrastructure. Each pillar below becomes worth building only when a specific real-world pain
appears (manual asset prep hurts → GenAI; quality misses slip through → Vision-QA; volume outgrows a
laptop → SaaS).

**Contents**
- [Pillar 1 — The Director Layer (God-level control)](#pillar-1--the-director-layer-god-level-control)
- [Pillar 2 — Generative AI Assets & Vision QA](#pillar-2--generative-ai-assets--vision-qa)
- [Pillar 3 — Paradigm-shifting Templates](#pillar-3--paradigm-shifting-templates)
- [Pillar 4 — Local Pipeline → SaaS Factory Backend](#pillar-4--local-pipeline--saas-factory-backend)
- [Top 3 bets, sequencing & the flywheel](#top-3-bets-sequencing--the-flywheel-endgame)

> **Foundational advantage to remember:** the codebase is already architected close to a real content
> factory — phase isolation, the idempotent `jobs/<id>/` handoff contract, atomic state writes,
> config-driven model routing, cost tracking, rate limiting. Most of the below is **wrapping and
> extending**, not rewriting. That's a strong starting position whenever we choose to act.

---

## Pillar 1 — The Director Layer (God-level control)

Today the flow is topic → auto. "God-mode" = steering every creative dimension **without editing code**.

- **A single declarative "Video Spec"** (one YAML/JSON per video) controlling template, persona/voice,
  palette "skin," pacing/energy, which retention hooks fire, B-roll choices, music mood, hook style.
  One file = total creative control. **The keystone** — turns a pipeline into an *instrument*.
- **Style "skins"** — named visual themes (`Hacker Leak`, `Clean Editorial`, `Neon Arcade`) swappable
  per video, decoupled from templates. *(The MVP palette+typography pass is literally the seed of this.)*
- **Variant generation / A-B** — render N versions from one dataset (different hook / music / thumbnail),
  ship the winner. Factory-scale creative experimentation, with deterministic seeds for reproducibility.

## Pillar 2 — Generative AI Assets & Vision QA

Integrate generative AI — but always **behind the brand filter** (duotone/halftone/recolor every
generated asset through the palette, so it reads as *our brand*, not generic "AI slop").

- **AI image generation for hero/topic imagery** (Flux / Imagen / SDXL). The VS/Sort templates already
  consume image assets (`Player1.jpg`, etc.); auto-generating topic-relevant portraits/logos kills the
  manual asset-prep bottleneck. **High ROI the moment manual prep becomes a chore.**
- **🌟 Vision-model visual QA loop** *(the single most transformative idea)*. Use a multimodal model
  (Claude / Gemini vision) to *look at a rendered frame* and grade it — overflow, contrast, legibility,
  "does this look premium?" → auto-retry. We already closed the quality loop on **scripts** (Phase 2
  script-doctor); closing it on **pixels** is what makes an autonomous factory *reliable at scale*
  instead of occasionally shipping a broken render.
- **Auto-thumbnail generation + A/B** — the highest-CTR lever on YouTube/Shorts, currently a gap.
- **AI music/SFX mood selection** per topic energy (BGM mixing + SFX marks already exist — just add a
  selection brain).

## Pillar 3 — Paradigm-shifting Templates (format > chart type)

The engine is a *chart* factory; the next leap is a *narrative-format* factory — **format drives
virality more than chart type.**

- **🌟 Time-evolution / "racing bar chart over time"** — the legendary viral format (how X changed
  2010→2025, animated playhead). Under-served and perfect for the data niche. *Top template bet.*
- **Countdown list ("Top 10…")** — the bread-and-butter of shorts; not built yet.
- **Tier list (S/A/B/C placement animation)** — enormous on social.
- **Relationship/network graph ("who owns what," conspiracy-board)** — tailor-made for the spy/leak
  brand; the elbow-connector tech (geo/sort) already half-exists.
- **Comparison scorecard / spec-matrix** — multi-attribute showdowns, deeper than 1-metric VS.
- **"Can you guess?" reveal** — interaction-bait that drives comments + watch-time.

## Pillar 4 — Local Pipeline → SaaS Factory Backend

The `jobs/<id>/` contract maps almost 1:1 onto a job-queue architecture, so this is mostly wrapping:

- **Async job queue + render-worker pool** (Celery / RQ / Temporal + Redis). Manim render becomes the
  heavy GPU/containerized worker step; CLI commands map directly to queue tasks.
- **Storage + DB swap** — `jobs/` artifacts → S3/GCS; `.pipeline_state.json` → Postgres rows. The
  `JobManager` abstraction already makes this a swap, not a rewrite.
- **FastAPI service** — create-job / approve-candidate / status / download / webhooks. The CLI verbs
  *are* the endpoints.
- **Containerized deterministic render env** (Docker + pinned FFmpeg/Manim/**fonts**) — also permanently
  solves the font-registration portability issue at the infra level.
- **Multi-tenancy + billing** — `cost_tracker` JSONL → usage metering; `rate_limiter.py` → per-tenant
  throttling. Already seeded.
- **🌟 The flywheel (the real endgame):** auto-discover topic → generate → **auto-publish** to
  YT/TikTok/IG via their APIs → ingest analytics (views/retention) → feed performance *back* into
  `candidate_score.py` topic scoring → repeat. A **self-optimizing, autonomous, multi-tenant content
  factory.** That feedback loop — the machine learning which topics/hooks/styles win and re-weighting
  its own discovery — is the difference between "a renderer" and "an unstoppable factory."

---

## Top 3 bets, sequencing & the flywheel (endgame)

When we do come back to this, the three highest-impact bets (in priority):

1. **Vision-model visual QA loop** (Pillar 2) — makes autonomous scale *trustworthy*.
2. **Director Spec + style skins** (Pillar 1) — unlocks god-mode control *and* variant testing.
3. **Time-evolution + countdown-list templates** (Pillar 3) — format-driven virality, where audience
   growth actually comes from.

**Sequencing:** the SaaS wrapping (Pillar 4) is the *industrialization* track — start it only **after**
quality (the QA loop) and control (the Director layer) are solid, so we scale something already
excellent rather than scaling chaos.

**Trigger to revisit this doc:** channel is live + we have real retention/CTR data to optimize against.