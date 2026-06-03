# RUNBOOK — Agentic Pipeline (Phases 1–3 + Handoff)
**Project:** AutoShorts | **Updated:** 2026-05-29

Ye runbook sirf **data pipeline** ke liye hai — topic discovery se lekar audio synthesis aur handoff tak.
Video rendering ke liye `RUNBOOK.md` dekho.

---

## Prerequisites

```bash
# Virtual environment activate karo
.venv\Scripts\activate          # Windows PowerShell
source .venv/bin/activate       # Linux / macOS

# Dependencies install karo
pip install -r requirements.txt
```

### Required `.env` file (project root mein)

Agentic pipeline ke liye API keys **mandatory** hain:

```
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxx      # Phase 1 web search
GEMINI_API_KEY=AIzaxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx # Phase 1 scoring + Phase 2 scripting
ELEVENLABS_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxx      # Phase 3 TTS (offline mode mein jarurat nahi)
```

**Optional overrides:**
```
GEMINI_MODEL=gemini-1.5-pro
GEMINI_RPM_LIMIT=15
GEMINI_TEMPERATURE=0.7
API_TIMEOUT_SECONDS=60
```

---

## Pipeline Overview

```
Phase 1A: Discovery  →  Phase 1B: Extraction  →  Phase 2: Scripting
     (Gemini + Tavily)       (LangGraph + Gemini)       (Gemini LLM)
                                                              ↓
                                                   Phase 3: Audio TTS
                                                     (ElevenLabs API)
                                                              ↓
                                                      Handoff → job.json
                                                              ↓
                                                   Phase 4: Video Render
                                                         (main.py)
```

---

## Do CLIs Hain

| CLI | Module | Kab use karein |
|-----|--------|----------------|
| **Master CLI** | `src/cli/autoshorts.py` | Phase 2 → 3 → Handoff → Render (ya full pipeline) |
| **Phase 1 CLI** | `src/cli/phase1.py` | Phase 1 Discovery + Extraction pe granular control |

---

## Master CLI — `src/cli/autoshorts.py`

### 1. Naya Job Folder Banao

```bash
python -m src.cli.autoshorts new --template bar_chart
```

**Kya karta hai:** Ek naya empty job directory banata hai `jobs/auto/<timestamp>_bar_chart/` ke andar.
Output mein aapko exact job path milta hai jise aage ke commands mein use karna hai.

**Flag:**
| Flag | Required | Description |
|------|----------|-------------|
| `--template` | ✅ | Template name — `bar_chart`, `butterfly_chart`, `geo_universal`, `scan_race`, `sort_card`, `vs_card`, `donut_breakdown` |

---

### 2. Phase 1 — Topic Discovery

```bash
python -m src.cli.autoshorts phase1-discover --template bar_chart
```

**Kya karta hai:** Gemini se topic ideas generate karta hai, Tavily se web evidence dhundta hai, phir AI scoring se best candidates rank karta hai. Results `discovery/raw_candidates.json` mein save hote hain.

```bash
# Discovery + results ek specific job folder mein copy karo
python -m src.cli.autoshorts phase1-discover --template bar_chart --job jobs/auto/my_job
```

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--template` | ✅ | Template niche hint (e.g., `vs_card` → VS battles, `bar_chart` → rankings) |
| `--job` | ❌ | Agar diya toh `raw_candidates.json` us job folder mein bhi copy hoga |

---

### 3. Phase 1 — Candidate Approve Karo

```bash
python -m src.cli.autoshorts phase1-approve \
  --job jobs/auto/my_job \
  --index 2 \
  --template bar_chart
```

**Kya karta hai:** `raw_candidates.json` se ek candidate (0-based index) ko approve karta hai. `discovery/approved.json` mein save hota hai — phase1-extract isko automatically read karta hai agar `--topic` nahi diya.

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--index` | ✅ | 0-based candidate index (`raw_candidates.json` mein `candidates[0]`, `[1]`...) |
| `--template` | ✅ | Template name |

---

### 4. Phase 1 — Data Extraction

```bash
# Option A: Topic directly deke
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/my_job \
  --template bar_chart \
  --topic "Top 5 AI Companies by Revenue 2024"

# Option B: Pehle approve karo, phir topic mat do (approved.json se uthega)
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/my_job \
  --template bar_chart
```

**Kya karta hai:** Topic ke liye web se data nikalta hai (LangGraph + Gemini + Tavily), validate karta hai, aur `data/` folder mein ye files likhta hai:
- `data/<template>_data.csv` — renderer ke liye CSV
- `data/<template>_dataset.json` — structured JSON
- `data/sources_audit.json` — source URLs ka audit trail
- `data/data_manifest.json` — phase 2 ke liye pointer file

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--template` | ✅ | Template name |
| `--topic` | ❌ | Topic string. Agar nahi diya toh `discovery/approved.json` se padha jayega |

---

### 5. Phase 2 — Script Generation

```bash
python -m src.cli.autoshorts phase2 \
  --job jobs/auto/my_job \
  --persona savage_roast_master
```

**Kya karta hai:** Dataset padh ke Gemini LLM se complete video script generate karta hai. Har segment ke liye dialogue + timing estimate likhta hai. Output: `script/script.json`.

```bash
# Force re-generate (cached script ignore karo)
python -m src.cli.autoshorts phase2 \
  --job jobs/auto/my_job \
  --persona hyper_analyst \
  --force
```

**Available Personas:**
| Persona ID | Style |
|------------|-------|
| `savage_roast_master` | Aggressive, roast-style commentary |
| `hyper_analyst` | Data-driven, analytical breakdown |
| `witty_strategist` | Smart, witty business insights |

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--persona` | ✅ | Persona ID (upar table dekho) |
| `--force` | ❌ | Cached `script.json` delete karke fresh generate karo |

---

### 6. Phase 3 — Audio Synthesis (TTS)

```bash
# Online mode (ElevenLabs API — real audio generate karta hai)
python -m src.cli.autoshorts phase3 \
  --job jobs/auto/my_job \
  --voice-id JBFqnCBsd6RMkjVDRZzb \
  --model-id eleven_multilingual_v2

# Offline mode (dummy audio — API key nahi chahiye, testing ke liye)
python -m src.cli.autoshorts phase3 \
  --job jobs/auto/my_job \
  --offline
```

**Kya karta hai:** `script/script.json` ke har segment ke liye `.mp3` audio file generate karta hai. Silence trim karta hai. Duration validate karta hai MND floor ke against. Output: `audio/hook.mp3`, `audio/item_1.mp3`, etc.

```bash
# Custom concurrency + format
python -m src.cli.autoshorts phase3 \
  --job jobs/auto/my_job \
  --voice-id <voice_id> \
  --model-id eleven_multilingual_v2 \
  --output-format mp3_44100_192 \
  --concurrency 5

# Underrun error bypass karo (strict timing check skip)
python -m src.cli.autoshorts phase3 \
  --job jobs/auto/my_job \
  --voice-id <voice_id> \
  --model-id eleven_multilingual_v2 \
  --skip-underrun
```

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--voice-id` | Online mein ✅ | ElevenLabs Voice ID |
| `--model-id` | Online mein ✅ | ElevenLabs Model ID |
| `--offline` | ❌ | Dummy audio generate karo (no API needed) |
| `--output-format` | ❌ | TTS format, default: `mp3_44100_128` |
| `--concurrency` | ❌ | Parallel TTS requests, default: `3` |
| `--skip-underrun` | ❌ | MND timing violation pe crash mat karo |

---

### 7. Repair Loop (Phase 2 + 3 Auto-Retry)

```bash
python -m src.cli.autoshorts repair \
  --job jobs/auto/my_job \
  --persona savage_roast_master \
  --template bar_chart \
  --max-tries 3
```

**Kya karta hai:** Agar Phase 3 mein `UnderRunError` aaye (audio too short for template timing), toh automatically Phase 2 ko force-rewrite karta hai aur Phase 3 retry karta hai. Max 2 tries default.

```bash
# Offline repair (testing ke liye)
python -m src.cli.autoshorts repair \
  --job jobs/auto/my_job \
  --persona hyper_analyst \
  --template bar_chart \
  --offline \
  --max-tries 2
```

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--persona` | ✅ | Persona ID for script rewrite |
| `--template` | ✅ | Template context |
| `--max-tries` | ❌ | Max retry attempts, default: `2` |
| `--offline` | ❌ | Offline TTS mode |
| `--skip-underrun` | ❌ | Underrun bypass |

---

### 8. Handoff (Pipeline → Renderer Bridge)

```bash
python -m src.cli.autoshorts handoff --job jobs/auto/my_job
```

**Kya karta hai:** Phase 3 ke outputs (`script/script.json` + `audio/`) ko read karke renderer-ready `job.json` banata hai. Segment names ko engine format mein map karta hai. Ye step Phase 3 aur Phase 4 ke beech ka bridge hai.

**Output:** `job.json` (renderer isko directly read karta hai)

---

### 9. Render Only (Phase 4 via Master CLI)

```bash
python -m src.cli.autoshorts render \
  --job jobs/auto/my_job \
  -q h

# Template override ke saath
python -m src.cli.autoshorts render \
  --job jobs/auto/my_job \
  --template bar_chart \
  -q l
```

**Kya karta hai:** `main.py` ko internally call karta hai. Sirf tab use karo jab `job.json` already ban chuka ho (handoff ho chuka ho).

**Quality flags:**
| Flag | Resolution | Speed |
|------|-----------|-------|
| `-q l` | Low (480p) | Sabse fast — preview ke liye |
| `-q m` | Medium (720p) | Balanced |
| `-q h` | High (1080p) | Production quality |
| `-q p` | 4K | Sabse slow |

---

### 10. Full Pipeline (Phase 2 → 3 → Handoff → Render)

```bash
# Online TTS ke saath
python -m src.cli.autoshorts run \
  --job jobs/auto/my_job \
  --template bar_chart \
  --persona savage_roast_master \
  --voice-id JBFqnCBsd6RMkjVDRZzb \
  --model-id eleven_multilingual_v2 \
  -q h

# Offline TTS ke saath (API key nahi chahiye)
python -m src.cli.autoshorts run \
  --job jobs/auto/my_job \
  --template bar_chart \
  --persona savage_roast_master \
  --offline \
  -q h
```

**Kya karta hai:** Phase 2 → Phase 3 → Handoff → Phase 4 ek hi command mein run karta hai.
**Note:** Phase 1 (discovery + extraction) pehle se ho chuka hona chahiye — `data/data_manifest.json` hona zaroori hai.

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--template` | ✅ | Template name |
| `--persona` | ✅ | Persona ID |
| `--voice-id` | Online ✅ | ElevenLabs Voice ID |
| `--model-id` | Online ✅ | ElevenLabs Model ID |
| `--offline` | ❌ | Offline TTS mode |
| `--skip-underrun` | ❌ | Timing check bypass |
| `--output-format` | ❌ | TTS format, default: `mp3_44100_128` |
| `--concurrency` | ❌ | Parallel TTS, default: `3` |
| `-q` | ❌ | Render quality, default: `h` |

---

## Phase 1 Granular CLI — `src/cli/phase1.py`

Jab tumhe Phase 1 pe zyada manual control chahiye.

### Discovery Only

```bash
python -m src.cli.phase1 discover --niche "AI Industry" --top-n 5
```

**Kya karta hai:** Sirf topic candidates dhundta hai, extraction nahi karta. Candidates `discovery/candidates.json` mein milenge.

**Flags:**
| Flag | Description |
|------|-------------|
| `--niche` | Domain hint (e.g., `"Tech Industry"`, `"Sports"`) |
| `--top-n` | Kitne candidates return karne hain |

---

### Auto Mode (Interactive — Discover + Operator Review + Extract)

```bash
python -m src.cli.phase1 auto --niche "Finance" --top-n 3
```

**Kya karta hai:** Discovery run karta hai, candidates dikhata hai, operator se input leta hai (approve/reject/queue), phir selected topic extract karta hai. Fully interactive flow.

---

### Candidate Approve Karo

```bash
python -m src.cli.phase1 approve \
  --job-id <job_id> \
  --index 1 \
  --template bar_chart
```

**Note:** Yahan `--index` **1-based** hai (phase1 CLI mein), jabki `autoshorts.py` ke `phase1-approve` mein 0-based hai.

---

### Candidate Reject Karo

```bash
# Multiple candidates ek saath reject karo
python -m src.cli.phase1 reject \
  --job-id <job_id> \
  --indices "2,3,4"
```

**Kya karta hai:** Rejected topics ko archive mein mark karta hai — dobara discover nahi honge.

---

### Topic Queue Mein Daalo (Baad ke liye save karo)

```bash
python -m src.cli.phase1 queue --job-id <job_id> --indices "1,2"
```

---

### Direct Extraction (Discovery Skip karo)

```bash
python -m src.cli.phase1 extract \
  --topic "Top 5 Richest Countries by GDP 2024" \
  --template bar_chart
```

**Kya karta hai:** Discovery phase skip karke directly data extract karta hai. Jab tumhein topic pata ho tab use karo.

---

### Job Outputs Inspect Karo

```bash
python -m src.cli.phase1 inspect --job-id <job_id>
```

**Kya karta hai:** Job ke saare output paths print karta hai — kahan CSV hai, kahan dataset hai, kahan manifest hai.

---

### Topic Queue Dekho

```bash
python -m src.cli.phase1 queue-show
```

**Kya karta hai:** Saare queued (saved for later) topics dikhata hai.

---

## Phase 3 Offline Testing

```bash
# No TTS API, no Gemini — pure local test
python src/agents/phase3_audio/offline_e2e.py
```

**Kya karta hai:** Dummy audio files generate karta hai locally, TTS API call nahi karta. Phase 3 ka pura flow test karne ke liye API key ki zarurat nahi.

---

## Pipeline State — Rerun / Force Reset

Har job ka ek `.pipeline_state.json` hota hai jo track karta hai ki kaunse phases complete hain:

```bash
# State file dekho
type jobs\auto\my_job\.pipeline_state.json

# Ek specific step reset karo (force rerun ke liye)
# PowerShell mein manually key delete karo ya file edit karo
```

**Common scenario:** Phase 3 dobara run karna hai lekin state mein `phase3_complete: true` likha hai → file mein se woh key hato.

---

## Tests (API Keys ki Zarurat Nahi)

```bash
# Phase 1 tests (fake LLM use karta hai)
python -m pytest tests/phase1 -v

# Phase 2 scripting tests (fake LLM)
python -m pytest tests/phase2_scripting -v

# Phase 3 offline end-to-end
python src/agents/phase3_audio/offline_e2e.py

# Fixture schema validation (saare 7 templates)
python -m pytest tests/fixtures/test_job_fixtures.py -v

# Full pipeline tests
python tests/pipeline/run_all.py
```

---

## Complete Workflow — Step by Step

### Scenario A: Ek naya video banao (full pipeline)

```bash
# Step 1: Naya job folder banao
python -m src.cli.autoshorts new --template bar_chart
# >> Output: jobs/auto/20260529_120000_bar_chart  ← ye path note karo

# Step 2: Topic discover karo
python -m src.cli.autoshorts phase1-discover --template bar_chart

# Step 3: Topic extract karo (direct topic deke)
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/20260529_120000_bar_chart \
  --template bar_chart \
  --topic "Top 5 AI Companies by Revenue 2024"

# Step 4-7: Phase 2 → 3 → Handoff → Render ek saath
python -m src.cli.autoshorts run \
  --job jobs/auto/20260529_120000_bar_chart \
  --template bar_chart \
  --persona savage_roast_master \
  --voice-id JBFqnCBsd6RMkjVDRZzb \
  --model-id eleven_multilingual_v2 \
  -q h
```

### Scenario B: API key nahi hai — offline testing

```bash
# Step 1
python -m src.cli.autoshorts new --template bar_chart

# Step 2 + 3: Discovery + Extraction (Gemini + Tavily keys chahiye)
python -m src.cli.autoshorts phase1-discover --template bar_chart
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/<your_job> \
  --template bar_chart \
  --topic "Top 5 Tech Companies"

# Step 4-7: Offline mode (ElevenLabs key nahi chahiye)
python -m src.cli.autoshorts run \
  --job jobs/auto/<your_job> \
  --template bar_chart \
  --persona hyper_analyst \
  --offline \
  -q l
```

---

## When Things Break — Agentic Pipeline

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ValidationError on import` | `.env` mein API key missing | `TAVILY_API_KEY` ya `GEMINI_API_KEY` add karo |
| `Phase rerun does nothing` | `.pipeline_state.json` mein step `true` hai | Us key ko manually delete karo |
| `UnderRunError` in Phase 3 | Script ke kuch segments bahut short hain | `repair` command use karo ya `--skip-underrun` |
| `Missing data_manifest.json` | Phase 1 extract nahi hua | `phase1-extract` pehle run karo |
| `No approved.json found` | Extract mein `--topic` nahi diya aur approve nahi kiya | Ya `--topic` do ya pehle `phase1-approve` run karo |
| Phase 3 audio truncated | TTS slow tha, timeout hua | `--concurrency 1` se retry karo |
| `approved.json` wrong topic | Wrong candidate index approve kiya | Sahi index deke `phase1-approve` dobara run karo |

---

## Job Directory Structure (Agentic Pipeline ke baad)

```
jobs/auto/<job_id>/
├── .pipeline_state.json       # Kaunse phases complete hain
├── discovery/
│   ├── raw_candidates.json    # Phase 1A: Discovered topics
│   ├── candidates.json        # Scored + ranked candidates
│   ├── decisions.json         # Operator ke approve/reject decisions
│   └── approved.json          # Approved topic (phase1-approve se)
├── data/
│   ├── bar_chart_data.csv     # Phase 1B: Renderer ke liye CSV
│   ├── bar_chart_dataset.json # Phase 1B: Structured data
│   ├── sources_audit.json     # Phase 1B: Source URLs
│   └── data_manifest.json     # Phase 2 ke liye pointer
├── script/
│   └── script.json            # Phase 2: LLM-written segments
├── audio/
│   ├── hook.mp3               # Phase 3: TTS audio per segment
│   ├── setup.mp3
│   ├── item_1.mp3
│   └── ...
├── job.json                   # Handoff: Renderer config (final output)
└── output/                    # Phase 4: Video files (main.py likhta hai)
    ├── final.mp4
    ├── subtitles.ass
    └── final_captioned.mp4
```
