import asyncio
import logging
import aiohttp
import os

from src.agents.phase2_scripting.timing import build_segment_plan
from src.agents.phase2_scripting.llm_writer import write_script
from tests.phase2_scripting.dummy_phase1_outputs import get_dummy_dataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_integration_test():
    logger.info("--- Testing Real Gemini LLM Integration ---")
    
    if "GEMINI_API_KEY" not in os.environ and "GEMINI_MODEL" not in os.environ:
        # Fallback to internal settings resolution if environments aren't cleanly loaded in bash scope
        pass 
        
    dataset = get_dummy_dataset(num_rows=2, template="vs_card") # Encompass fewer rows to safeguard LLM speed limit budgets
    
    plan = build_segment_plan("job_integration_gemini_123", "vs_card", "witty_strategist", dataset)
    
    timeout = aiohttp.ClientTimeout(total=45) # Long enough for an expansive prompt
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            final_segments, raw_history = await write_script(plan, dataset, session, logger)
            logger.info("PASS: Gemini successfully returned a native, fully verified exact-parsed XML monologue natively adhering to specific limits.")
            logger.info(f"Number of generated and verified segments: {len(final_segments)}")
            logger.info(f"Raw history length (with revisions if any): {len(raw_history)} characters")
            for seg in final_segments:
                 logger.info(f" -> TAG: {seg.tag} | Validated Chars: {seg.char_count} (Bounds: {seg.target_min_chars}-{seg.target_max_chars})")
            print("\n=== INTEGRATION TEST: PASS ===")
        except Exception as e:
            logger.error("Failed integration test.", exc_info=True)
            print(f"Exception Message: {e}")
            if hasattr(e, "status"):
                print(f"HTTP Status: {e.status}")
            print("\n=== INTEGRATION TEST: FAIL ===")
            raise

if __name__ == "__main__":
    asyncio.run(run_integration_test())
