# RUNBOOK — Agentic Pipeline
**Project:** AutoShorts | **Updated:** 2026-06-05

Ye runbook **sirf data pipeline** ke liye hai (Phases 1–3 + Handoff).
Video rendering ke liye `RUNBOOK.md` dekho.

---

## Pehle Samjho — Pipeline Kya Hai?

```
Phase 1A: Topic Discovery     →  Gemini + Tavily se ideas + evidence
Phase 1B: Data Extraction     →  LangGraph + Gemini se structured CSV/JSON
Phase 2:  Script Generation   →  Gemini LLM se voiceover script
Phase 3:  Audio TTS           →  ElevenLabs se .mp3 files (+ auto-trim)
Handoff:  job.json banana     →  renderer ke liye final config file
Phase 4:  Video Render        →  main.py (Manim + FFmpeg)
```

**Do CLIs hain:**
| CLI | Kab use karo |
|-----|-------------|
| `src/cli/autoshorts.py` | Zyada tar use yahi karo — Phase 2 se Phase 4 tak + full pipeline |
| `src/cli/phase1.py` | Sirf jab Phase 1 pe zyada manual control chahiye |

---

## Setup (Ek baar karo)

```powershell
# Virtual env activate karo
.venv\Scripts\activate

# .env file mein sirf ye teen keys chahiye
TAVILY_API_KEY=tvly-...        # Phase 1 web search
GEMINI_API_KEY=AIza...         # Phase 1 + Phase 2 LLM
ELEVENLABS_API_KEY=sk_...      # Phase 3 TTS (offline mode mein nahi chahiye)
```

> **Model, temperature, RPM, timeout — ye sab `.env` mein nahi, `src/agents/core/config.py` mein hain.**
> Change karna ho toh wahan `LLMConfig` / `TTSConfig` edit karo.

---

## PART 1 — Master CLI Commands (`autoshorts.py`)

---

### CMD-1: Naya Job Folder Banao

```powershell
python -m src.cli.autoshorts new --template bar_chart
```

**Scenario:** Jab bhi naya video banana start karo, sabse pehle yahi command chalao. Ye ek khali job directory banata hai jahan poora pipeline ka output save hoga.

**Kya karta hai:**
- `jobs/auto/<timestamp>_bar_chart/` folder banata hai
- Andar `.pipeline_state.json` banta hai jo track karta hai kaunsa phase complete hua

**Output kahan:** Terminal mein exact path print hota hai — **wo path note kar lo**, aage saari commands mein kaam aayega.

```
>> jobs/auto/20260605_143000_bar_chart   ← ye note karo
```

**Flags:**
| Flag | Required | Values |
|------|----------|--------|
| `--template` | ✅ | `bar_chart`, `butterfly_chart`, `vs_card`, `sort_card`, `donut_breakdown`, `geo_universal`, `scan_race` |

---

### CMD-2: Phase 1A — Topic Discover Karo

```powershell
python -m src.cli.autoshorts phase1-discover --template bar_chart
```

**Scenario:** Jab tumhe khud topic decide nahi karna — AI se ideas chahiye. Ye command Gemini se topic ideas generate karega, Tavily se web pe evidence dhundega, aur sab candidates rank karke dikhayega.

**Kya karta hai:**
1. Gemini se 10-15 topic hypotheses generate karta hai
2. Tavily se har topic ka web evidence collect karta hai
3. Gemini se score/rank karta hai (hook potential, data feasibility, viral angle)
4. Top candidates save karta hai

**Output kahan:** `discovery/raw_candidates.json` (job folder ke andar nahi, shared discovery folder mein)

```powershell
# Agar output specific job folder mein bhi chahiye
python -m src.cli.autoshorts phase1-discover --template bar_chart --job jobs/auto/my_job
```

---

### CMD-3: Phase 1A — Candidate Approve Karo

```powershell
python -m src.cli.autoshorts phase1-approve \
  --job jobs/auto/my_job \
  --index 2 \
  --template bar_chart
```

**Scenario:** Discovery ke baad `raw_candidates.json` mein multiple topics aaye hain. Tum unhe dekho, aur jo topic best lage uska index deke approve karo. Iske baad extraction automatically usi topic pe chalega.

**Kya karta hai:** Index 2 wale candidate ko `discovery/approved.json` mein save karta hai.

**Output kahan:** `jobs/auto/my_job/discovery/approved.json`

> **Note:** `--index` yahan **0-based** hai (pehla candidate = 0).

---

### CMD-4: Phase 1B — Data Extract Karo

```powershell
# Option A: Topic seedha do
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/my_job \
  --template bar_chart \
  --topic "Top 5 AI Companies by Revenue 2024"

# Option B: Pehle approve karo (CMD-3), phir topic mat do
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/my_job \
  --template bar_chart
```

**Scenario A:** Jab tumhe topic pata hai — directly deke data extract karo. Discovery phase skip karo.
**Scenario B:** Jab CMD-3 se approve kar chuke ho — ye automatically `approved.json` se topic uthayega.

**Kya karta hai:**
1. Topic ke baare mein web se data dhundta hai (Tavily)
2. Gemini se unstructured text ko structured rows mein convert karta hai
3. Template ke hisaab se CSV banata hai (renderer isko directly read karta hai)

**Output kahan:**
```
jobs/auto/my_job/data/
  ├── bar_chart_data.csv        ← renderer ke liye (Phase 4 isko padhega)
  ├── bar_chart_dataset.json    ← structured data
  ├── sources_audit.json        ← kahan se data aaya
  └── data_manifest.json        ← Phase 2 isko pointer ki tarah read karta hai
```

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--template` | ✅ | Template name |
| `--topic` | ❌ | Topic string. Nahi diya toh `approved.json` se padha jayega |

---

### CMD-5: Phase 2 — Script Generate Karo

```powershell
python -m src.cli.autoshorts phase2 \
  --job jobs/auto/my_job \
  --persona savage_roast_master
```

**Scenario:** Data extract ho gaya (`data_manifest.json` ban gaya). Ab Gemini se video ka voiceover script likhwao. Persona decide karta hai ki script ka tone kaisa hoga.

**Kya karta hai:**
1. `data/data_manifest.json` padh ke dataset load karta hai
2. Persona ke system prompt + visual rules ke saath Gemini ko call karta hai
3. Har segment ke liye dialogue text generate karta hai (HOOK, SETUP, ITEM_1, ITEM_2... WINNER, OUTRO)
4. Timing estimate bhi likhta hai

**Output kahan:** `jobs/auto/my_job/script/script.json`

**Available Personas:**
| Persona ID | Style |
|------------|-------|
| `savage_roast_master` | Aggressive, dramatic, roast-style |
| `hyper_analyst` | Data-driven, analytical |
| `witty_strategist` | Smart, witty business tone |

```powershell
# Agar script phir se likhwana ho (cached version ignore karo)
python -m src.cli.autoshorts phase2 \
  --job jobs/auto/my_job \
  --persona hyper_analyst \
  --force
```

---

### CMD-6: Phase 3 — Audio Generate Karo (TTS)

```powershell
# Online mode — real audio (ElevenLabs API)
python -m src.cli.autoshorts phase3 \
  --job jobs/auto/my_job \
  --voice-id JBFqnCBsd6RMkjVDRZzb \
  --model-id eleven_multilingual_v2

# Offline mode — dummy audio (API key nahi chahiye, sirf testing ke liye)
python -m src.cli.autoshorts phase3 \
  --job jobs/auto/my_job \
  --offline
```

**Scenario (Online):** Script ban gayi. Ab ElevenLabs se real voice generate karo — yahi final audio video mein jayega.
**Scenario (Offline):** API key nahi hai ya sirf pipeline test karna hai — dummy beep audio generate hoga, real voice nahi.

**Kya karta hai:**
1. `script/script.json` ka har segment padhta hai
2. ElevenLabs API se `.mp3` generate karta hai (parallel, 3 requests ek saath by default)
3. **Pydub se silence trim karta hai** (leading/trailing dead air hata deta hai)
4. Duration validate karta hai — agar audio template ke minimum time se chhota ho toh `UnderRunError` deta hai
5. Atomically disk pe save karta hai

**Output kahan:**
```
jobs/auto/my_job/audio/
  ├── HOOK.mp3
  ├── SETUP.mp3
  ├── ITEM_1.mp3
  ├── ITEM_2.mp3
  └── ... (har segment ke liye ek file)
```

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--voice-id` | Online ✅ | ElevenLabs Voice ID |
| `--model-id` | Online ✅ | ElevenLabs Model ID (default config: `eleven_multilingual_v2`) |
| `--offline` | ❌ | Dummy audio — no API needed |
| `--output-format` | ❌ | Default: `mp3_44100_128` |
| `--concurrency` | ❌ | Parallel TTS requests, default: `3` |
| `--skip-underrun` | ❌ | Timing error pe crash mat karo (jab testing ho) |

> **Default voice/model config mein set karna:** `src/agents/core/config.py` → `TTSConfig.model_id` / `TTSConfig.voice_id`

---

### CMD-7: Repair Loop (Phase 2 + 3 Auto-Retry)

```powershell
python -m src.cli.autoshorts repair \
  --job jobs/auto/my_job \
  --persona savage_roast_master \
  --template bar_chart \
  --max-tries 3
```

**Scenario:** Phase 3 mein `UnderRunError` aaya — matlab kisi segment ki generated audio template ke minimum duration se chhoti hai. Manually `--force` karke Phase 2 dobara nahi chalana — ye command automatically Phase 2 ko force-rewrite karta hai aur Phase 3 retry karta hai jab tak error na jaye ya max tries khatam ho.

**Kya karta hai:**
1. Phase 2 force-rerun karta hai (longer script ke liye)
2. Phase 3 dobara chalata hai
3. Agar phir error aaya toh ek baar aur — `max-tries` tak

**Output kahan:** Same — `script/script.json` update hota hai, `audio/` files overwrite hoti hain.

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job path |
| `--persona` | ✅ | Persona for script rewrite |
| `--template` | ✅ | Template context |
| `--max-tries` | ❌ | Default: `2` |
| `--offline` | ❌ | Offline TTS mode |
| `--skip-underrun` | ❌ | Underrun bypass |

---

### CMD-8: Handoff — Pipeline Output ko Renderer ke liye Ready Karo

```powershell
python -m src.cli.autoshorts handoff --job jobs/auto/my_job
```

**Scenario:** Phase 3 complete ho gaya — `audio/` mein files hain, `script/script.json` updated hai. Ab `main.py` (video renderer) ko ek `job.json` chahiye jo bataye ki segments kaunse hain, order kya hai, timelines kya hain. Ye command wo `job.json` banata hai.

**Kya karta hai:**
1. `script/script.json` aur `audio/` folder padhta hai
2. Segment names ko renderer ke engine format mein map karta hai (`HOOK` → `hook`, `ITEM_1` → `item1` etc.)
3. `job.json` likhta hai — jo `main.py` directly read karta hai

**Output kahan:** `jobs/auto/my_job/job.json`

> Ye step Phase 3 aur Phase 4 ke beech ka bridge hai. Bina iske `main.py` kaam nahi karega.

---

### CMD-9: Sirf Render Karo (Phase 4)

```powershell
python -m src.cli.autoshorts render \
  --job jobs/auto/my_job \
  -q h
```

**Scenario:** `job.json` already ban chuka hai (handoff ho chuka hai). Bas video render karna hai — Manim + FFmpeg se final output chahiye.

**Kya karta hai:** Internally `main.py` call karta hai — Manim scene render, audio concat, SFX mix, final mux.

**Output kahan:** `jobs/auto/my_job/output/final.mp4`

**Quality flags:**
| Flag | Quality | Speed |
|------|---------|-------|
| `-q l` | Low 480p | Sabse fast — preview ke liye |
| `-q m` | Medium 720p | Balanced |
| `-q h` | High 1080p | Production quality |
| `-q p` | 4K | Sabse slow |

---

### CMD-10: Full Pipeline — Phase 2 se Phase 4 Ek Saath

```powershell
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

**Scenario:** Phase 1 (data extraction) already ho chuka hai — `data/data_manifest.json` exist karta hai. Ab script likhna, audio banana, handoff aur render — sab ek hi command mein karna hai.

**Kya karta hai:** Phase 2 → Phase 3 → Handoff → Phase 4 ek ke baad ek chalta hai.

> **Important:** Ye Phase 1 nahi chalata. `data/data_manifest.json` pehle se hona zaroori hai.

**Flags:**
| Flag | Required | Description |
|------|----------|-------------|
| `--job` | ✅ | Job directory path |
| `--template` | ✅ | Template name |
| `--persona` | ✅ | Persona ID |
| `--voice-id` | Online ✅ | ElevenLabs Voice ID |
| `--model-id` | Online ✅ | ElevenLabs Model ID |
| `--offline` | ❌ | Offline TTS |
| `--skip-underrun` | ❌ | Timing check bypass |
| `--output-format` | ❌ | TTS format, default: `mp3_44100_128` |
| `--concurrency` | ❌ | Parallel TTS, default: `3` |
| `-q` | ❌ | Render quality, default: `h` |

---

## PART 2 — Phase 1 Granular CLI (`phase1.py`)

Ye tab use karo jab Phase 1 pe zyada control chahiye — topics manually review karne ho, ek ek step alag chalaana ho.

---

### CMD-11: Sirf Discovery Chalao

```powershell
python -m src.cli.phase1 discover --niche "AI Industry" --top-n 5
```

**Scenario:** Sirf topic ideas dhundne hain — data extract nahi karna. Ek list chahiye ki is niche mein kaunse viral topics ban sakte hain.

**Output kahan:** `discovery/candidates.json`

---

### CMD-12: Interactive Auto Mode

```powershell
python -m src.cli.phase1 auto --niche "Finance" --top-n 3
```

**Scenario:** Discovery + manual review + extraction ek interactive session mein karna hai. Ye candidates dikhayega, tum approve/reject/queue karoge, phir selected topic extract karega.

**Output kahan:** Discovery + data files dono ban jaate hain.

---

### CMD-13: Candidate Approve Karo (Phase 1 CLI)

```powershell
python -m src.cli.phase1 approve \
  --job-id <job_id> \
  --index 1 \
  --template bar_chart
```

**Scenario:** Discovery ke baad manually ek specific candidate approve karna hai.

> **Note:** Yahan `--index` **1-based** hai — pehla candidate = 1 (autoshorts.py mein 0-based tha, confuse mat hona).

---

### CMD-14: Candidate Reject Karo

```powershell
python -m src.cli.phase1 reject \
  --job-id <job_id> \
  --indices "2,3,4"
```

**Scenario:** Kuch topics boring ya repeat hain — permanently reject karo taaki future discovery mein dobara na aayein.

**Kya karta hai:** Rejected topics archive mein mark ho jaate hain.

---

### CMD-15: Topic Queue Mein Daalo

```powershell
python -m src.cli.phase1 queue --job-id <job_id> --indices "1,2"
```

**Scenario:** Topic interesting hai lekin abhi extract nahi karna — baad ke liye save karo.

---

### CMD-16: Direct Extraction (Discovery Skip Karo)

```powershell
python -m src.cli.phase1 extract \
  --topic "Top 5 Richest Countries by GDP 2024" \
  --template bar_chart
```

**Scenario:** Topic already decide hai, directly data chahiye — discovery bilkul skip karo. Yahi sabse common Phase 1 use case hai jab tum khud topic decide karte ho.

**Output kahan:** `data/` folder (CSV + JSON + manifest)

---

### CMD-17: Job Outputs Inspect Karo

```powershell
python -m src.cli.phase1 inspect --job-id <job_id>
```

**Scenario:** Job ke andar kya kya files bani hain, kahan hain — ye sab check karna hai bina manually folders explore kiye.

---

### CMD-18: Queue Dekho

```powershell
python -m src.cli.phase1 queue-show
```

**Scenario:** Kaun kaun se topics queue mein hain (baad ke liye save kiye gaye) — list dekhna hai.

---

## PART 3 — Testing (Bina API Key Ke)

```powershell
# Phase 1 tests (fake LLM)
python -m pytest tests/phase1 -v

# Phase 2 scripting tests (fake LLM)
python -m pytest tests/phase2_scripting -v

# Phase 3 offline end-to-end (no TTS API)
python src/agents/phase3_audio/offline_e2e.py

# All 7 template fixture schema tests
python -m pytest tests/fixtures/test_job_fixtures.py -v
```

---

## PART 4 — Complete Workflows

### Workflow A: Pura Video Banao (Full Pipeline)

```powershell
# Step 1: Naya job folder banao
python -m src.cli.autoshorts new --template bar_chart
# Terminal output: jobs/auto/20260605_143000_bar_chart  ← NOTE KARO

# Step 2: Data extract karo (topic seedha deke)
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/20260605_143000_bar_chart \
  --template bar_chart \
  --topic "Top 5 AI Companies by Revenue 2024"

# Step 3: Phase 2 → 3 → Handoff → Render ek saath
python -m src.cli.autoshorts run \
  --job jobs/auto/20260605_143000_bar_chart \
  --template bar_chart \
  --persona savage_roast_master \
  --voice-id JBFqnCBsd6RMkjVDRZzb \
  --model-id eleven_multilingual_v2 \
  -q h
```

**Final output:** `jobs/auto/20260605_143000_bar_chart/output/final.mp4`

---

### Workflow B: AI Se Topic Discover Karo, Phir Video Banao

```powershell
# Step 1: Naya job banao
python -m src.cli.autoshorts new --template vs_card

# Step 2: AI se topics discover karo
python -m src.cli.autoshorts phase1-discover --template vs_card \
  --job jobs/auto/my_job

# Step 3: raw_candidates.json dekho, ek approve karo (index 0-based)
python -m src.cli.autoshorts phase1-approve \
  --job jobs/auto/my_job \
  --index 1 \
  --template vs_card

# Step 4: Approved topic ka data extract karo
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/my_job \
  --template vs_card

# Step 5: Full pipeline
python -m src.cli.autoshorts run \
  --job jobs/auto/my_job \
  --template vs_card \
  --persona savage_roast_master \
  --voice-id <your_voice_id> \
  --model-id eleven_multilingual_v2 \
  -q h
```

---

### Workflow C: API Key Nahi Hai — Offline Testing

```powershell
# Step 1 + 2
python -m src.cli.autoshorts new --template bar_chart
python -m src.cli.autoshorts phase1-extract \
  --job jobs/auto/my_job \
  --template bar_chart \
  --topic "Top 5 Tech Companies"

# Step 3: Offline mode (ElevenLabs key nahi chahiye)
python -m src.cli.autoshorts run \
  --job jobs/auto/my_job \
  --template bar_chart \
  --persona hyper_analyst \
  --offline \
  -q l
```

---

## PART 5 — Jab Cheezein Toot Jaayein

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ValidationError on import` | `.env` mein API key missing hai | `TAVILY_API_KEY` ya `GEMINI_API_KEY` add karo |
| Phase rerun kuch nahi karta | `.pipeline_state.json` mein step `true` marked hai | Us key ko manually file se delete karo |
| `UnderRunError` in Phase 3 | Koi segment bahut chhota bola | `repair` command use karo ya `--skip-underrun` |
| `Missing data_manifest.json` | Phase 1 extract nahi hua | Pehle `phase1-extract` chalao |
| `No approved.json found` | `--topic` nahi diya aur approve bhi nahi kiya | Ya `--topic` do ya pehle `phase1-approve` chalao |
| Phase 3 audio truncated / timeout | TTS slow tha, concurrency zyada thi | `--concurrency 1` se dobara chalao |
| Dobara phase 3 chahiye par kuch nahi hota | Cache hit ho raha hai (hash match) | `audio/` folder delete karo ya script change karo |

---

## PART 6 — Job Folder Structure (Pipeline Ke Baad)

```
jobs/auto/<job_id>/
├── .pipeline_state.json           # Kaunse phases complete hain (idempotency)
│
├── discovery/
│   ├── raw_candidates.json        # Phase 1A: AI se discovered topics
│   ├── candidates.json            # Scored + ranked list
│   ├── decisions.json             # Tumhare approve/reject decisions
│   └── approved.json              # Jo approve kiya (phase1-approve se)
│
├── data/
│   ├── bar_chart_data.csv         # Phase 1B: Renderer ke liye CSV
│   ├── bar_chart_dataset.json     # Structured JSON
│   ├── sources_audit.json         # Source URLs trail
│   └── data_manifest.json         # Phase 2 isko pointer ki tarah read karta hai
│
├── script/
│   └── script.json                # Phase 2: LLM-written segments (HOOK, SETUP, ITEM_1...)
│
├── audio/
│   ├── HOOK.mp3                   # Phase 3: TTS generated + pydub trimmed
│   ├── SETUP.mp3
│   ├── ITEM_1.mp3
│   └── ...
│
├── job.json                       # Handoff: Renderer ka final config
│
└── output/                        # Phase 4: main.py yahan likhta hai
    ├── final.mp4
    ├── subtitles.ass
    ├── final_captioned.mp4
    └── renders/                   # Timestamped archive copies
```
