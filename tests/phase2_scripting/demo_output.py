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
    parse_monologue
)
from src.agents.core.config import APP_CONFIG
from src.agents.core.llm_client import call_llm_raw

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

        # Demo uses the draft route — the same one the writer's first pass uses.
        #
        # This used to build the URL by hand with the API key in the QUERY STRING,
        # which leaks the key into every traceback and error log this script writes.
        # Going through the shared client keeps the key in an Authorization header
        # and means the demo exercises the real code path.
        draft_model = APP_CONFIG.llm.scripting_draft

        timeout = aiohttp.ClientTimeout(total=APP_CONFIG.llm_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            log = logging.getLogger("demo")
            out.append(
                f"\nSingle-shot call via {draft_model.provider}:{draft_model.model} "
                "(no rewrite loop, no doctor).\n"
            )

            result = await call_llm_raw(
                system_prompt, user_prompt_full, session, log,
                draft_model, "demo_draft",
            )
            raw_output = result.text

            out.append("="*50)
            out.append(f"RAW MODEL OUTPUT (XML Monologue) — usage: {result.usage}")
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
