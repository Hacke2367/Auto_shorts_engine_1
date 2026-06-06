import asyncio
import json
import logging
import aiohttp
import traceback

from tests.phase2_scripting.dummy_phase1_outputs import get_dummy_dataset
from src.agents.phase2_scripting.timing import build_segment_plan

from src.agents.phase2_scripting.llm_writer import (
    _build_system_prompt,
    _build_user_prompt,
    _load_text,
    VISUAL_RULES_PATH,
    _call_gemini,
    parse_monologue
)
from src.agents.core.config import settings, APP_CONFIG

logging.basicConfig(level=logging.WARNING)

async def main():
    out = []
    out.append("=== AUTO-SHORTS PHASE 2 SINGLE-SHOT DEMO ===")
    
    try:
        dataset = get_dummy_dataset(num_rows=3, template="vs_card")
        persona_id = "savage_roast_master"
        plan = build_segment_plan("demo_job", "vs_card", persona_id, dataset)
        out.append(f"Template: vs_card | Persona: {persona_id} | Segments: {len(plan.segments)}")
        
        system_prompt = _build_system_prompt(plan.persona_id)
        user_prompt_full = _build_user_prompt(dataset, plan)

        # Demo uses the draft model (Flash) — same route the writer's first pass uses.
        model_name = APP_CONFIG.llm.scripting_draft.model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.gemini_api_key.get_secret_value()}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt_full}]}],
            "generationConfig": {"temperature": APP_CONFIG.llm.scripting_draft.temperature},
        }

        timeout = aiohttp.ClientTimeout(total=45)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            log = logging.getLogger("demo")
            out.append("\nCalling Gemini directly bypassing all Tenacity retries to force 1 execution...\n")
            
            async with session.post(url, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
                raw_output = data["candidates"][0]["content"]["parts"][0]["text"]
            
            out.append("="*50)
            out.append("RAW GEMINI OUTPUT (XML Monologue)")
            out.append("="*50)
            out.append(raw_output.strip())
            
            try:
                parsed_segments = parse_monologue(raw_output, plan)
                
                out.append("\n" + "="*50)
                out.append("FINAL PARSED JSON (script.json equivalency)")
                out.append("="*50)
                
                output_dict = {
                    "job_id": "demo_job",
                    "template_name": "vs_card",
                    "persona_id": persona_id,
                    "voice_cps": plan.voice_cps,
                    "segments": [seg.model_dump() for seg in parsed_segments]
                }
                out.append(json.dumps(output_dict, indent=2, ensure_ascii=False))
            except Exception as e:
                out.append("\n[!] Structural Parsing Failure on Output:")
                out.append(str(e))
                
    except Exception as e:
        out.append("\nERROR EXPERIENCED:")
        out.append(str(e))

    with open("demo_output_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))

if __name__ == "__main__":
    asyncio.run(main())
